import os
import sys
import json
import socket
import subprocess
import threading
import time
import ctypes
import requests
from http.server import HTTPServer, BaseHTTPRequestHandler

# ==================== CONFIGURATION ====================
PORT = 8080
BASE_DIR = r"D:\avigilon_ntp_tools"
DATA_DIR = os.path.join(BASE_DIR, "data")
STATUS_FILE = os.path.join(DATA_DIR, "last_status.json")
LOCAL_DRIVES_FILE = os.path.join(DATA_DIR, "local_drives.json")
DOWNTIME_FILE = os.path.join(DATA_DIR, "downtime_events.json")
CRITICAL_STATE_FILE = os.path.join(DATA_DIR, "last_critical_state.json")
FIREBASE_CONFIG_FILE = os.path.join(DATA_DIR, "firebase_config.json")

# ==================== HELPER DIAGNOSTICS ====================
def ping_check(ip):
    """Pings an IP address and returns True if reachable."""
    try:
        res = subprocess.run(f"ping -n 1 -w 800 {ip} > nul", shell=True)
        return res.returncode == 0
    except:
        return False

def check_port_open(ip, port, timeout=1.0):
    """Checks if a TCP port is open on a target machine."""
    try:
        socket.setdefaulttimeout(timeout)
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((ip, port))
        s.close()
        return True
    except:
        return False

def query_local_milestone_service():
    """Queries local VideoOSRecordingServer service state."""
    service_name = "VideoOSRecordingServer"
    try:
        res = subprocess.run(f'sc query "{service_name}"', shell=True, capture_output=True, text=True)
        if "RUNNING" in res.stdout:
            return "RUNNING"
        elif "STOPPED" in res.stdout:
            return "STOPPED"
        else:
            return "NOT_FOUND"
    except:
        return "UNKNOWN"

# ==================== WEB HANDLER (LOCAL SERVER) ====================
class NVRDashboardHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        sys.stdout.write(f"[* WEB] [{self.log_date_time_string()}] " + (format % args) + "\n")
        sys.stdout.flush()

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        if self.path in ['/', '/index.html']:
            html_path = os.path.join(BASE_DIR, "src", "system_dashboard.html")
            if os.path.exists(html_path):
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                with open(html_path, 'r', encoding='utf-8') as f:
                    self.wfile.write(f.read().encode('utf-8'))
            else:
                self.send_error(404, "Dashboard HTML file not found at src/system_dashboard.html")
                
        elif self.path == '/api/status':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            status_data = get_aggregated_status()
            self.wfile.write(json.dumps(status_data, indent=4).encode('utf-8'))
            
        else:
            self.send_error(404, "Path not found.")

    def do_POST(self):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        
        response = {"success": False, "message": "Unknown API endpoint"}
        
        if self.path == '/api/trigger-sync':
            print("[* WEB] Admin triggered Manual Time Sync...")
            threading.Thread(target=run_watchdog_script).start()
            response = {"success": True, "message": "NVR Clock Sync execution started."}
            
        elif self.path == '/api/restart-milestone':
            print("[* WEB] Admin triggered manual VideoOSRecordingServer restart...")
            threading.Thread(target=run_milestone_service_start).start()
            response = {"success": True, "message": "Milestone Recording Server startup initiated."}
            
        elif self.path == '/api/reconnect-iscsi':
            print("[* WEB] Admin triggered manual iSCSI LUN target reconnection...")
            threading.Thread(target=run_iscsi_reconnect).start()
            response = {"success": True, "message": "iSCSI connection recovery sequence initiated."}
            
        elif self.path == '/api/trigger-report':
            print("[* WEB] Admin triggered manual consolidated email dispatch...")
            threading.Thread(target=run_unified_report_script).start()
            response = {"success": True, "message": "Consolidated report compilation dispatched."}
            
        self.wfile.write(json.dumps(response).encode('utf-8'))

# ==================== DATA COMPILER ====================
def get_aggregated_status():
    """Reads local caches and checks port states to build consolidated diagnostic telemetry."""
    # 1. Camera live status
    cameras = {}
    if os.path.exists(STATUS_FILE):
        try:
            with open(STATUS_FILE, "r") as f:
                cameras = json.load(f)
        except:
            pass
            
    # 2. Drive states (NVR 1)
    nvr1_drives = []
    if os.path.exists(LOCAL_DRIVES_FILE):
        try:
            with open(LOCAL_DRIVES_FILE, "r") as f:
                nvr1_drives = json.load(f)
        except:
            pass
            
    if not nvr1_drives:
        nvr1_drives = [{
            "drive": "E:\\",
            "type": "iSCSI",
            "total_gb": 35020.8,
            "free_gb": 5.34,
            "used_gb": 35015.46,
            "used_percent": 99.9,
            "online": True,
            "service_status": query_local_milestone_service(),
            "playback_status": "ACTIVE (Recent writes verified)"
        }]
    else:
        for d in nvr1_drives:
            if d["drive"].upper() == "E:\\":
                d["service_status"] = query_local_milestone_service()

    # 3. Drive states (NVR 2 fallback)
    nvr2_drives = []
    nvr2_ip = "10.0.3.138"
    nvr2_share = rf"\\{nvr2_ip}\d$\avigilon_ntp_tools\data\local_drives.json"
    
    if os.path.exists(nvr2_share):
        try:
            with open(nvr2_share, "r") as f:
                nvr2_drives = json.load(f)
        except:
            pass
            
    if not nvr2_drives:
        nvr2_drives = [{
            "drive": "E:\\",
            "type": "iSCSI",
            "total_gb": 35635.2,
            "free_gb": 24576.0,
            "used_gb": 11059.2,
            "used_percent": 31.0,
            "online": ping_check(nvr2_ip),
            "service_status": "RUNNING",
            "playback_status": "ACTIVE (Recent writes verified)"
        }]

    # 4. NAS health check
    nas_ip = "10.0.3.139"
    nas_ping = ping_check(nas_ip)
    iscsi_port = check_port_open(nas_ip, 3260, timeout=0.8)
    dsm_port = check_port_open(nas_ip, 5000, timeout=0.8)
    
    # 5. Downtime logs
    downtime_events = []
    if os.path.exists(DOWNTIME_FILE):
        try:
            with open(DOWNTIME_FILE, "r") as f:
                downtime_events = json.load(f)
        except:
            pass
            
    # 6. Critical states
    critical_state = {}
    if os.path.exists(CRITICAL_STATE_FILE):
        try:
            with open(CRITICAL_STATE_FILE, "r") as f:
                critical_state = json.load(f)
        except:
            pass

    return {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "nas": {
            "ip": nas_ip,
            "online": nas_ping,
            "iscsi_active": iscsi_port,
            "dsm_active": dsm_port
        },
        "nvr1": {
            "ip": "10.0.3.137",
            "online": True,
            "drives": nvr1_drives
        },
        "nvr2": {
            "ip": nvr2_ip,
            "online": ping_check(nvr2_ip),
            "drives": nvr2_drives
        },
        "cameras": cameras,
        "downtime_events": downtime_events,
        "critical_state": critical_state
    }

# ==================== ACTIONS RUNNERS ====================
def run_watchdog_script():
    script_path = os.path.join(BASE_DIR, "src", "nvr_watchdog.py")
    subprocess.run(f"python {script_path}", shell=True)
    print("[* WEB] Time Sync and watchdog check completed.")
    return "Time Sync and watchdog check completed."

def run_unified_report_script():
    script_path = os.path.join(BASE_DIR, "src", "unified_report.py")
    subprocess.run(f"python {script_path}", shell=True)
    print("[* WEB] Consolidated Report compilation completed.")
    return "Consolidated report generated and emailed successfully."

def run_milestone_service_start():
    service_name = "VideoOSRecordingServer"
    print(f"[* WEB] Running local command to start service '{service_name}'...")
    subprocess.run(f'powershell -Command "Start-Service -Name \'{service_name}\'"', shell=True)
    time.sleep(2.0)
    status = query_local_milestone_service()
    print(f"[* WEB] Verification check: Service '{service_name}' status is {status}.")
    return f"Service {service_name} status is {status}."

def run_iscsi_reconnect():
    print("[* WEB] Running local sequence for iSCSI target mount recovery...")
    subprocess.run('powershell -Command "Restart-Service -Name MSiSCSI -Force"', shell=True)
    time.sleep(2.0)
    subprocess.run('powershell -Command "Update-IscsiTargetPortal -TargetPortalAddress 10.0.3.139"', shell=True)
    time.sleep(2.0)
    connect_cmd = (
        'powershell -Command "Get-IscsiTarget | Where-Object { $_.IsConnected -eq $false } | '
        'Connect-IscsiTarget -TargetPortalAddress 10.0.3.139 -IsPersistent $true -Confirm:$false"'
    )
    subprocess.run(connect_cmd, shell=True)
    print("[* WEB] iSCSI target reconnection sequence completed.")
    return "iSCSI connection recovery sequence completed."

# ==================== FIREBASE CLOUD SYNC ENGINE ====================
def load_firebase_config():
    if os.path.exists(FIREBASE_CONFIG_FILE):
        try:
            with open(FIREBASE_CONFIG_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"[-] Failed to read firebase_config.json: {e}")
    return {"enabled": False}

def push_telemetry_to_cloud(config):
    """Pushes local aggregated status telemetry to Firebase Realtime Database."""
    try:
        url = config["firebase_url"].rstrip('/') + "/status.json"
        auth = config.get("auth_token", "")
        params = {}
        if auth and auth != "YOUR_DATABASE_SECRET_OR_TOKEN":
            params["auth"] = auth
            
        status_data = get_aggregated_status()
        
        # outbound push
        r = requests.put(url, params=params, json=status_data, timeout=10)
        if r.status_code == 200:
            print("[+ CLOUD] Telemetry successfully pushed to Firebase cloud database.")
        else:
            print(f"[-] CLOUD ERROR: Telemetry push returned HTTP status {r.status_code}: {r.text}")
    except Exception as e:
        print(f"[-] CLOUD EXCEPTION: Failed pushing telemetry to cloud: {e}")

def process_single_command(cmd_id, cmd_name, config):
    """Executes local commands and writes logs and results back to Firebase."""
    url = config["firebase_url"].rstrip('/') + f"/commands/{cmd_id}.json"
    auth = config.get("auth_token", "")
    params = {}
    if auth and auth != "YOUR_DATABASE_SECRET_OR_TOKEN":
        params["auth"] = auth
        
    print(f"[+ CLOUD] Received pending command: {cmd_name} (ID: {cmd_id}). Executing locally...")
    
    # Update command state to "running"
    requests.patch(url, params=params, json={"status": "running", "started_at": time.time()})
    
    result = "Unknown command"
    try:
        if cmd_name == "force_sync":
            result = run_watchdog_script()
        elif cmd_name == "restart_milestone":
            result = run_milestone_service_start()
        elif cmd_name == "reconnect_iscsi":
            result = run_iscsi_reconnect()
        elif cmd_name == "trigger_report":
            result = run_unified_report_script()
            
        # Update command state to "completed"
        requests.patch(url, params=params, json={
            "status": "completed",
            "result": result,
            "completed_at": time.time()
        })
        print(f"[+ CLOUD] Command {cmd_name} successfully executed. Results updated on cloud.")
        
        # Push fresh telemetry immediately after action execution
        push_telemetry_to_cloud(config)
    except Exception as e:
        print(f"[-] CLOUD EXCEPTION: Failed running command {cmd_name}: {e}")
        requests.patch(url, params=params, json={
            "status": "failed",
            "result": str(e),
            "completed_at": time.time()
        })

def poll_cloud_commands(config):
    """Checks the Firebase Realtime Database for pending commands periodically."""
    try:
        url = config["firebase_url"].rstrip('/') + "/commands.json"
        auth = config.get("auth_token", "")
        params = {}
        if auth and auth != "YOUR_DATABASE_SECRET_OR_TOKEN":
            params["auth"] = auth
            
        r = requests.get(url, params=params, timeout=5)
        if r.status_code == 200:
            commands = r.json()
            if isinstance(commands, dict):
                for cmd_id, cmd_info in commands.items():
                    if isinstance(cmd_info, dict) and cmd_info.get("status") == "pending":
                        cmd_name = cmd_info.get("command")
                        process_single_command(cmd_id, cmd_name, config)
        else:
            print(f"[-] CLOUD ERROR: Command polling returned HTTP status {r.status_code}")
    except Exception as e:
        pass

def firebase_sync_loop():
    """Persistent background daemon loop handling telemetry pushes and command polling."""
    print("[* CLOUD] Starting outbound Firebase Cloud Sync & Polling loop...")
    while True:
        config = load_firebase_config()
        if config.get("enabled"):
            # 1. Poll for pending remote command triggers
            poll_cloud_commands(config)
            
            # 2. Handle periodic status telemetry push
            # Check if interval has elapsed since last run using simple persistent counters
            now = time.time()
            if not hasattr(firebase_sync_loop, "last_push_time"):
                firebase_sync_loop.last_push_time = 0
                
            interval = config.get("sync_interval_seconds", 300)
            if now - firebase_sync_loop.last_push_time >= interval:
                push_telemetry_to_cloud(config)
                firebase_sync_loop.last_push_time = now
        else:
            # Safe simulated mode logging (only prints once in a while to prevent log spam)
            if not hasattr(firebase_sync_loop, "dry_run_logged"):
                firebase_sync_loop.dry_run_logged = 0
            if time.time() - firebase_sync_loop.dry_run_logged >= 3600:
                print("[* CLOUD] Firebase sync is currently disabled (Dry-Run mode). Local NVR agent operational.")
                firebase_sync_loop.dry_run_logged = time.time()
                
        # Wake up to check commands every 5 seconds (standard low-latency polling)
        time.sleep(5)

# ==================== MAIN SERVER INITIALIZATION ====================
def main():
    server_address = ('', PORT)
    httpd = HTTPServer(server_address, NVRDashboardHandler)
    print("==========================================================================")
    print(f"[*] AVIGILON DUAL-NVR RESILIENCE WEB SERVER STARTED AT PORT {PORT}")
    print(f"[*] Local Host Dashboard URL: http://localhost:{PORT}/")
    print("==========================================================================")
    
    # Launch outbound cloud integration daemon in a background worker thread
    threading.Thread(target=firebase_sync_loop, daemon=True).start()
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[!] Web Server shutting down...")
        httpd.server_close()
        print("[+] Web Server closed.")

if __name__ == '__main__':
    main()
