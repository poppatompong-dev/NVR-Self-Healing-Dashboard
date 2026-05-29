# Product Requirements Document (PRD)
## Project: NVR Self-Healing & Clock Resilience System
**Version:** 2.0.0  
**Target QA Agent:** TestSprite Autonomous Testing Agent  
**Context:** Consolidated Watchdog & Remote Management Dashboard for Dual-NVR Milestone XProtect Enterprise CCTV Networks.

---

## 1. Executive Summary & Product Vision
The **NVR Self-Healing & Clock Resilience System** is an autonomous, high-resilience utility suite designed to monitor, maintain, and auto-recover a critical CCTV infrastructure consisting of:
*   **2 Milestone XProtect NVRs** (NVR 1 at `10.0.3.137`, NVR 2 at `10.0.3.138`).
*   **33 IP Cameras** (22 on NVR 1, 11 on NVR 2).
*   **1 Central Synology SA3400 NAS** storing footage via iSCSI SAN.

The system consists of two primary operational components:
1.  **Local Self-Healing Daemon:** A low-footprint background Python process running on the NVRs, executing high-frequency network pings, ONVIF SOAPs, iSCSI targets auto-reconnections, and Milestone service health restorers.
2.  **Consolidated Cloud Web Dashboard:** A responsive, premium retro-styled glassmorphic frontend hosted on Vercel, reading telemetry and dispatching operations through Firebase Realtime Database.

---

## 2. System Architecture & Network Topology

### 2.1 Hardware and IP Reference List
*   **NVR 1 (Master):** `10.0.3.137`
*   **NVR 2 (Client):** `10.0.3.138`
*   **Synology SA3400 NAS:** `10.0.3.139` (Port `3260` for iSCSI target, Port `5000` for Synology Web API DSM)
*   **NVR 1 Cameras (22 Nodes):** `10.0.3.148` through `10.0.3.178` (Skipping Gateway/Switches)
*   **NVR 2 Cameras (11 Nodes):** `10.0.3.147` through `10.0.3.180` (Skipping Gateway/Switches)

### 2.2 Communication Architecture
```
                                +---------------------------+
                                |  Vercel Web Dashboard     |
                                |  (HTML5/JS ES6 Frontend)   |
                                +-------------+-------------+
                                              | Outbound HTTPS
                                              v
                                +-------------+-------------+
                                | Firebase Realtime Database|
                                |  (RTDB Cloud /status)     |
                                +-------------+-------------+
                                              ^
                                              | Outbound HTTPS Polling (5s)
                                +-------------+-------------+
                                | Local Background Cloud     |
                                | Agent (web_dashboard.py)  |
                                +------+------+-------------+
                                       |      |
                    Local ONVIF SOAP   |      | Local Subprocess Popen
                                       v      v
              +------------------------+      +---------------------------+
              | 33 IP Cameras (ONVIF)  |      | Windows System Services   |
              | Clock Sync (Port 80)   |      | - VideoOSRecordingServer  |
              +------------------------+      | - MSiSCSI (iSCSI Mount)   |
                                              +---------------------------+
```

---

## 3. Core Features & Functional Requirements

### 3.1 Feature 1: Multi-NVR Parallel Time Sync (ONVIF SOAP)
*   **Requirements:**
    *   Query all 33 cameras concurrently using a `ThreadPoolExecutor` (maximum 12 worker threads).
    *   Check HTTP port 80 online state. If offline, log immediately.
    *   Send ONVIF SOAP payload `GetSystemDateAndTime` using HTTP Digest Authentication.
    *   **Dynamic Credentials Mapping:**
        *   Group A (NVR 2 cameras + special NVR 1 cameras): User: `administrator` / `administrator`, Password: `Admin1234` or `Admin@123`.
        *   Group B (Standard NVR 1 OEM cameras): User: `Admin`, Password: `1234`.
    *   Compare camera time against the NVR Master Time.
    *   **Synchronization Trigger:** If the offset exceeds **2.0 seconds**, send `SetSystemDateAndTime` (Manual mode followed by NTP enable mode WIT-7) to sync the clock.
*   **TestSprite Assertions:**
    *   *Assert:* Concurrent time check takes less than **20 seconds** to complete scanning 33 nodes.
    *   *Assert:* Digest Authentication handles both standard and administrative security schemas without throwing unhandled HTTP 401 exceptions.

### 3.2 Feature 2: High-Frequency Resiliency Watchdog (Logical Drive & Service Auditing)
*   **Requirements:**
    *   Audit logical drive `E:\` (LUN-1 on NVR 1, LUN-2 on NVR 2).
    *   Determine space utilization. Since Milestone buffers footage, expected utilization is high (e.g. **99.9%**). If size is full, display **"Filled LUN-1"** status safely.
    *   Check for database recording activity under `E:\` by scanning files recursively (depth limit 2) to find the most recent file modification timestamp (`mtime`).
    *   **Alert Trigger:** If no writes are detected within the last **15 minutes (900 seconds)**, flag database writes as `INACTIVE` or `WARNING`.

### 3.3 Feature 3: Automated Self-Healing Engine (Auto-Recovery)
*   **Requirements:**
    *   **iSCSI Target Recovery:** If drive `E:\` is missing, log a critical event, restart the Windows iSCSI Initiator service (`MSiSCSI`), update the target portal (`10.0.3.139`), and trigger `Connect-IscsiTarget` to re-mount LUNs.
    *   **Milestone Recording Service Recovery:** Check the status of `VideoOSRecordingServer` Windows Service using `sc query`. If found `STOPPED`, execute elevated PowerShell command to restart the service (`Start-Service`).
    *   **Notification Engine:** Dispatch instant, visually distinct HTML alert emails via SMTP (Gmail TLS, port 587) upon successful recovery actions.
*   **TestSprite Assertions:**
    *   *Assert:* Missing drive triggers the SAN reconnection pipeline.
    *   *Assert:* Windows service recovery resolves stopped service states to `RUNNING` within 10 seconds.

### 3.4 Feature 4: Interactive Glassmorphic Cloud Dashboard (Web Interface)
*   **Requirements:**
    *   Must load a responsive, sleek, dark-themed layout using Google Font "Outfit" and "Noto Sans Thai" for language localization.
    *   Read telemetry dynamically from `/status.json` on Firebase Realtime Database.
    *   **Visual Elements:**
        *   Online/Offline/Skewed statistics cards and charts.
        *   NAS port badges (Hardware Ping, iSCSI SAN port 3260, Synology DSM API port 5000).
        *   Master and Client local storage space utilization bars.
        *   Downtime event logs table and network flapping analyzer.
    *   **Firebase Integration:** Replace IP address keys (e.g., `10.0.3.148`) with safe keys (e.g., `10_0_3_148`) replacing periods with underscores to bypass Firebase key limitations.
*   **TestSprite Assertions:**
    *   *Assert:* Web dashboard loads with zero console errors or uncaught JSON parse failures.
    *   *Assert:* Camera status parses both period-based and underscore-based IP key formats securely.

### 3.5 Feature 5: Outbound Command Queue & Real-Time Terminal Console
*   **Requirements:**
    *   Establish a secure, firewall-friendly command pipeline by pushing JSON tasks under `/commands/{cmd_id}.json` in Firebase.
    *   Local background NVR Agent polls this path every **3-5 seconds** via outbound HTTPS GET.
    *   **Supported Actions:** `force_sync` (Manual sync), `trigger_report` (Daily report dispatch), `restart_milestone` (Service recovery), `reconnect_iscsi` (iSCSI target mount).
    *   **Progressive Logging:**
        *   When starting, NVR updates command to `"status": "running"` and `"progress": 0`.
        *   Stream NVR process stdout *line-by-line* into `"logs"` string.
        *   Dynamically compute progress percentage (`progress`) and text description (`progress_text`). For `force_sync`, count cameras processed (e.g. `completed / 33 * 100`).
        *   On success, set `"status": "completed"`, `"progress": 100`, and push final result.
    *   **Frontend Terminal Modal:**
        *   Show an overlay console displaying the live-streamed logs in real-time.
        *   Animate progress bars from 0% to 100% based on Firebase updates.
        *   Scroll to bottom automatically. Enable close button only upon termination (completed/failed/timeout).
*   **TestSprite Assertions:**
    *   *Assert:* Pushing a command triggers execution within 5 seconds on NVR.
    *   *Assert:* Log streaming appends lines concurrently and triggers terminal console updates without UI freezes.
    *   *Assert:* Completed commands transition the frontend button and modal states correctly.

---

## 4. Test Scenarios and Test Cases (For Automation Setup)

### 4.1 Test Case ID: TS-001 (Camera Synchronization Engine)
*   **Prerequisites:** Target IP camera is online and simulated time is offset by +10 seconds.
*   **Action:** Execute `force_sync` command.
*   **Expected Result:**
    1.  Command shifts status to `running`.
    2.  NVR identifies +10.0s time offset.
    3.  ONVIF payload sets correct NVR master time.
    4.  Command transitions to `completed` and logs list time adjustment success.

### 4.2 Test Case ID: TS-002 (Milestone Service Self-Healing)
*   **Prerequisites:** Stop the `VideoOSRecordingServer` service on NVR.
*   **Action:** Run the watchdog task (`nvr_watchdog.py`).
*   **Expected Result:**
    1.  Watchdog queries and catches `STOPPED` state.
    2.  PowerShell `Start-Service` is triggered.
    3.  Service transitions back to `RUNNING` state.
    4.  Gmail SMTP dispatches critical recovery notification.

### 4.3 Test Case ID: TS-003 (iSCSI Target Mount Auto-Healing)
*   **Prerequisites:** Drive `E:\` is unmounted/disconnected.
*   **Action:** Trigger `reconnect_iscsi` command.
*   **Expected Result:**
    1.  Daemon restarts `MSiSCSI` service.
    2.  `Update-IscsiTargetPortal` executes successfully.
    3.  `Connect-IscsiTarget` remounts the LUN.
    4.  Drive `E:\` becomes visible in logical drive mapping.

---

## 5. Security & Non-Functional Requirements
*   **Zero Inbound Open Ports:** The NVR must not open any firewall ports to the public internet. All telemetry uploads and command queue listening must be outbound HTTPS.
*   **Credential Security:** Camera usernames/passwords must never be stored in Firebase or GitHub. They must remain local inside the NVR's memory and scripts.
*   **Fault Tolerance:** If Firebase is offline, the local NVR agent must fallback safely to local cached reports without causing memory leaks or infinite retry loops.
