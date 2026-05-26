# System Architecture & Technical Debt

## Network Topology
The system consists of two Avigilon Network Video Recorders (NVRs) and 33 IP Cameras.

* **NVR 1 (Master):** `10.0.3.138` (Hosts 11 cameras)
* **NVR 2 (Client):** `10.0.3.137` (Hosts 22 cameras)

Because this is a closed network, there is no access to `pool.ntp.org` or `time.windows.com`.

### The Hierarchical NTP Setup
To prevent the NVRs from drifting apart, we established a hierarchical NTP structure:
1. **NVR 1** runs `w32time` as a reliable time source (Stratum 1 for the local network).
2. **NVR 2** is configured via `w32time` to sync its clock from `10.0.3.138`.
3. **Cameras** are configured to use NTP, pointing to their respective NVRs.

## The "Time Jump" Problem
Despite having NTP enabled on all cameras, certain OEM cameras (primarily Hikvision and Dahua rebrands) experienced severe time drift or time zone miscalculations. 
* Avigilon's ONVIF implementation pushes UTC time, but some cameras apply a hardcoded `+7` offset *on top* of the pushed time.
* This caused cameras to jump 7 hours into the future.
* To combat this, some cameras had their TimeZone set manually to UTC, but then they drifted locally.

## The Watchdog Solution
Instead of fighting the proprietary firmware bugs, we built a Python Watchdog (`src/nvr_watchdog.py`) that acts as an aggressive ONVIF supervisor.

### Watchdog Logic Flow
1. **Poll:** Every 15 minutes, the script queries `GetSystemDateAndTime` via ONVIF SOAP.
2. **Evaluate:** It compares the camera's returned `UTCDateTime` against the NVR's local clock.
3. **Action:** If the delta is > 2 seconds:
   - The script sends a `SetSystemDateAndTime` command with `DateTimeType=Manual`, forcefully overriding the camera's clock to match the NVR exactly.
   - It pauses for 1 second to allow the camera's OS to settle.
   - It sends a second `SetSystemDateAndTime` command with `DateTimeType=NTP` to re-enable smooth tracking.
4. **Digest Authentication:** Because modern IP cameras reject basic auth, the script uses `requests.auth.HTTPDigestAuth` to securely negotiate with the web servers.

## Flapping Detection
A common issue in CCTV networks is physical cable degradation or switch overload, causing cameras to drop offline randomly ("Flapping").
If the Watchdog sent an email every time a camera dropped, it would create alert fatigue. Instead, the Watchdog saves state changes locally to `data/downtime_events.json`. The daily reporter (`src/unified_report.py`) parses this JSON and presents it as a clean summary list at 5:00 PM.
