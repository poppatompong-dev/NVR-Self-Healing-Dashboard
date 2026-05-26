# Camera Credentials Reference

For security reasons, actual passwords are not stored in this repository. 
When deploying this repository, you must edit the `get_camera_creds(ip)` function in `src/nvr_watchdog.py` and `src/unified_report.py` to include the correct credentials.

## NVR 1 Cameras (10.0.3.147 - 10.0.3.180)
* **Username:** `administrator`
* **Password:** `<YOUR_NVR1_PASSWORD>` (e.g. `Admin1234`)

## NVR 2 Cameras (10.0.3.148 - 10.0.3.178)
These cameras have fragmented credentials due to different OEM batches (Dahua/Hikvision rebrands).

### Batch A (Specific IPs)
IPs: `.148`, `.156`, `.160`, `.171`, `.174`, `.175`
* **Username:** `admin`
* **Password:** `<YOUR_NVR2_BATCH_A_PASSWORD>` (e.g. `Admin@123`)

### Batch B (All other NVR 2 IPs)
* **Username:** `Admin`
* **Password:** `<YOUR_NVR2_BATCH_B_PASSWORD>` (e.g. `1234`)

## NVR Windows OS Accounts
* **Username:** `Administrator`
* **Password:** `<WINDOWS_PASSWORD>`

*Ensure that the Windows Scheduled Tasks run under the `NT AUTHORITY\SYSTEM` account to bypass user login requirements and ensure the scripts run 24/7.*
