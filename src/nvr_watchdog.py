import os
import sys
import socket
import json
import time
from datetime import datetime, timedelta, timezone
import xml.etree.ElementTree as ET
import requests
from requests.auth import HTTPDigestAuth
from concurrent.futures import ThreadPoolExecutor

# ==================== CONFIGURATION ====================
NVR1_IPS = [
    "10.0.3.147", "10.0.3.154", "10.0.3.158", "10.0.3.161", "10.0.3.164", 
    "10.0.3.167", "10.0.3.170", "10.0.3.173", "10.0.3.176", "10.0.3.179", "10.0.3.180"
]

NVR2_IPS = [
    "10.0.3.148", "10.0.3.149", "10.0.3.150", "10.0.3.152", "10.0.3.153", 
    "10.0.3.155", "10.0.3.156", "10.0.3.157", "10.0.3.159", "10.0.3.160", 
    "10.0.3.162", "10.0.3.163", "10.0.3.165", "10.0.3.166", "10.0.3.168", 
    "10.0.3.169", "10.0.3.171", "10.0.3.172", "10.0.3.174", "10.0.3.175", 
    "10.0.3.177", "10.0.3.178"
]

ALL_CAMERAS = NVR1_IPS + NVR2_IPS

# File Paths
BASE_DIR = r"D:\avigilon_ntp_tools"
DATA_DIR = os.path.join(BASE_DIR, "data")
STATUS_FILE = os.path.join(DATA_DIR, "last_status.json")
DOWNTIME_FILE = os.path.join(DATA_DIR, "downtime_events.json")

if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

headers = {'Content-Type': 'application/soap+xml; charset=utf-8'}
# =======================================================

def get_camera_creds(ip):
    """Dynamic credentials lookup for cameras across both NVRs."""
    if ip in NVR1_IPS:
        return "administrator", "Admin1234"
    admin_123_ips = ["10.0.3.148", "10.0.3.156", "10.0.3.160", "10.0.3.171", "10.0.3.174", "10.0.3.175"]
    if ip in admin_123_ips:
        return "admin", "Admin@123"
    return "Admin", "1234"

def check_camera_online(ip, port=80, timeout=3.0):
    try:
        socket.setdefaulttimeout(timeout)
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((ip, port))
        s.close()
        return True
    except Exception:
        return False

def get_camera_time(ip):
    url = f"http://{ip}/onvif/device_service"
    get_time_payload = """<?xml version="1.0" encoding="utf-8"?>
    <s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope" xmlns:tds="http://www.onvif.org/ver10/device/wsdl">
      <s:Body><tds:GetSystemDateAndTime/></s:Body>
    </s:Envelope>"""
    user, password = get_camera_creds(ip)
    r = requests.post(url, data=get_time_payload, headers=headers, auth=HTTPDigestAuth(user, password), timeout=5)
    if r.status_code == 200:
        root = ET.fromstring(r.text)
        utc_dt = None
        for elem in root.iter():
            if elem.tag.endswith('UTCDateTime'):
                parts = {}
                for child in elem.iter():
                    tag_name = child.tag.split('}')[-1]
                    if child.text and child.text.strip().isdigit():
                        parts[tag_name] = int(child.text)
                if 'Year' in parts and 'Month' in parts and 'Day' in parts:
                    utc_dt = datetime(
                        parts.get('Year', 1970), parts.get('Month', 1), parts.get('Day', 1),
                        parts.get('Hour', 0), parts.get('Minute', 0), parts.get('Second', 0)
                    )
                    break
        if utc_dt:
            return utc_dt + timedelta(hours=7)
    raise Exception(f"HTTP {r.status_code}")

def force_camera_sync(ip):
    url = f"http://{ip}/onvif/device_service"
    now_utc = datetime.now(timezone.utc)
    
    manual_time_payload = f"""<?xml version="1.0" encoding="utf-8"?>
    <s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope" xmlns:tt="http://www.onvif.org/ver10/schema" xmlns:tds="http://www.onvif.org/ver10/device/wsdl">
      <s:Body>
        <tds:SetSystemDateAndTime>
          <tds:DateTimeType>Manual</tds:DateTimeType>
          <tds:DaylightSavings>false</tds:DaylightSavings>
          <tds:TimeZone><tt:TZ>WIT-7</tt:TZ></tds:TimeZone>
          <tds:UTCDateTime>
            <tt:Time>
              <tt:Hour>{now_utc.hour}</tt:Hour>
              <tt:Minute>{now_utc.minute}</tt:Minute>
              <tt:Second>{now_utc.second}</tt:Second>
            </tt:Time>
            <tt:Date>
              <tt:Year>{now_utc.year}</tt:Year>
              <tt:Month>{now_utc.month}</tt:Month>
              <tt:Day>{now_utc.day}</tt:Day>
            </tt:Date>
          </tds:UTCDateTime>
        </tds:SetSystemDateAndTime>
      </s:Body>
    </s:Envelope>"""
    
    ntp_enable_payload = """<?xml version="1.0" encoding="utf-8"?>
    <s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope" xmlns:tt="http://www.onvif.org/ver10/schema" xmlns:tds="http://www.onvif.org/ver10/device/wsdl">
      <s:Body>
        <tds:SetSystemDateAndTime>
          <tds:DateTimeType>NTP</tds:DateTimeType>
          <tds:DaylightSavings>false</tds:DaylightSavings>
          <tds:TimeZone><tt:TZ>WIT-7</tt:TZ></tds:TimeZone>
        </tds:SetSystemDateAndTime>
      </s:Body>
    </s:Envelope>"""
    
    user, password = get_camera_creds(ip)
    
    # 1. Force manual time to match NVR
    r1 = requests.post(url, data=manual_time_payload, headers=headers, auth=HTTPDigestAuth(user, password), timeout=15)
    if r1.status_code != 200:
        raise Exception(f"Manual Sync Failed (HTTP {r1.status_code})")
        
    time.sleep(1.0)
        
    # 2. Re-enable NTP target syncing mode
    r2 = requests.post(url, data=ntp_enable_payload, headers=headers, auth=HTTPDigestAuth(user, password), timeout=15)
    if r2.status_code != 200:
        raise Exception(f"NTP Enable Failed (HTTP {r2.status_code})")

def log_downtime_event(ip, old_status, new_status):
    """Logs state changes to downtime_events.json for the evening report."""
    events = []
    if os.path.exists(DOWNTIME_FILE):
        try:
            with open(DOWNTIME_FILE, "r") as f:
                events = json.load(f)
        except:
            pass
            
    # Add new event
    events.append({
        "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "ip": ip,
        "event": f"{old_status} -> {new_status}"
    })
    
    # Keep only the last 500 events to prevent massive files
    if len(events) > 500:
        events = events[-500:]
        
    try:
        with open(DOWNTIME_FILE, "w") as f:
            json.dump(events, f, indent=4)
    except Exception as e:
        print(f"[-] Failed saving downtime event: {e}")

def sync_single_camera(ip, nvr_time, last_status):
    is_online = check_camera_online(ip)
    status_str = "ONLINE" if is_online else "OFFLINE"
    
    # Check for status changes (Flapping detection)
    if ip in last_status:
        if last_status[ip] != status_str:
            print(f"[!] STATE CHANGE: {ip} went from {last_status[ip]} to {status_str}! Logging event.")
            log_downtime_event(ip, last_status[ip], status_str)
            
    if is_online:
        try:
            cam_time = get_camera_time(ip)
            offset = (nvr_time - cam_time).total_seconds()
            if abs(offset) > 2.0:
                force_camera_sync(ip)
                print(f"[+] {ip}: Time difference was {offset:+.1f}s. Synchronized successfully!")
            else:
                print(f"[+] {ip}: Time in sync ({offset:+.1f}s difference).")
        except Exception as e:
            print(f"[-] {ip}: Online but failed to query/sync time: {e}")
    else:
        print(f"[-] {ip}: OFFLINE")
        
    return ip, status_str

def main():
    nvr_time = datetime.now()
    print(f"[*] Running Dual-NVR parallel silent clock sync job at {nvr_time.strftime('%Y-%m-%d %H:%M:%S')}...")
    
    # Load last states
    last_status = {}
    if os.path.exists(STATUS_FILE):
        try:
            with open(STATUS_FILE, "r") as f:
                last_status = json.load(f)
        except:
            pass
            
    current_status = {}
    
    # Process all 33 cameras in parallel (10 workers)
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(sync_single_camera, ip, nvr_time, last_status) for ip in ALL_CAMERAS]
        for f in futures:
            ip, status_str = f.result()
            current_status[ip] = status_str
            
    # Save current status as last status for next run
    try:
        with open(STATUS_FILE, "w") as f:
            json.dump(current_status, f)
    except Exception as e:
        print(f"[-] Failed saving status file: {e}")
        
    print("[*] Dual-NVR Clock sync job completed.")

if __name__ == "__main__":
    main()
