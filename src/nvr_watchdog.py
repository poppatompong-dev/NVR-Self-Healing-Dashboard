import os
import sys
import socket
import json
import time
import smtplib
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import xml.etree.ElementTree as ET
import requests
from requests.auth import HTTPDigestAuth
from concurrent.futures import ThreadPoolExecutor

# ==================== CONFIGURATION ====================
# Email SMTP Configuration for Urgent Alerts
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = "poppatompong@gmail.com"
SMTP_PASSWORD = "yqkmfuoonilelecm"
SENDER_EMAIL = "poppatompong@gmail.com"
RECIPIENT_EMAIL = "poppatompong@gmail.com"

# NVR 1 (10.0.3.137) Camera List (22 Cameras - skipping Gateway/Switch .254)
NVR1_IPS = [
    "10.0.3.148", "10.0.3.149", "10.0.3.150", "10.0.3.152", "10.0.3.153", 
    "10.0.3.155", "10.0.3.156", "10.0.3.157", "10.0.3.159", "10.0.3.160", 
    "10.0.3.162", "10.0.3.163", "10.0.3.165", "10.0.3.166", "10.0.3.168", 
    "10.0.3.169", "10.0.3.171", "10.0.3.172", "10.0.3.174", "10.0.3.175", 
    "10.0.3.177", "10.0.3.178"
]

# NVR 2 (10.0.3.138) Camera List (11 Cameras)
NVR2_IPS = [
    "10.0.3.147", "10.0.3.154", "10.0.3.158", "10.0.3.161", "10.0.3.164", 
    "10.0.3.167", "10.0.3.170", "10.0.3.173", "10.0.3.176", "10.0.3.179", "10.0.3.180"
]

ALL_CAMERAS = NVR1_IPS + NVR2_IPS

# File Paths
BASE_DIR = r"D:\avigilon_ntp_tools"
DATA_DIR = os.path.join(BASE_DIR, "data")
STATUS_FILE = os.path.join(DATA_DIR, "last_status.json")
DOWNTIME_FILE = os.path.join(DATA_DIR, "downtime_events.json")
ZONES_FILE = os.path.join(DATA_DIR, "zones.json")
CRITICAL_STATE_FILE = os.path.join(DATA_DIR, "last_critical_state.json")

if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

headers = {'Content-Type': 'application/soap+xml; charset=utf-8'}
# =======================================================

def get_camera_creds(ip):
    """Dynamic credentials lookup for cameras across both NVRs."""
    if ip in NVR2_IPS:
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
    
    r1 = requests.post(url, data=manual_time_payload, headers=headers, auth=HTTPDigestAuth(user, password), timeout=15)
    if r1.status_code != 200:
        raise Exception(f"Manual Sync Failed (HTTP {r1.status_code})")
        
    time.sleep(1.0)
        
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
            
    events.append({
        "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "ip": ip,
        "event": f"{old_status} -> {new_status}"
    })
    
    if len(events) > 500:
        events = events[-500:]
        
    try:
        with open(DOWNTIME_FILE, "w") as f:
            json.dump(events, f, indent=4)
    except Exception as e:
        print(f"[-] Failed saving downtime event: {e}")

def send_instant_critical_email(subject, message_body):
    """Sends an instant critical system alert email."""
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = SENDER_EMAIL
        msg['To'] = RECIPIENT_EMAIL
        
        html = f"""<!DOCTYPE html>
        <html>
        <head><meta charset="utf-8"></head>
        <body style="background-color: #0c1017; font-family: 'Consolas', monospace; color: #ff3333; padding: 20px;">
            <div style="max-width: 600px; margin: 0 auto; background-color: #080c12; border: 2px solid #ff3333; border-radius: 6px; padding: 20px; box-shadow: 0 0 20px rgba(255, 51, 51, 0.15);">
                <pre style="margin: 0; padding: 0; color: #ff3333; font-weight: bold; font-size: 14px; text-align: center;">
 _  _ _  _ ____ ____ _  _ ___    ____ _    ____ ____ ___ 
 |  | |__/  | __ |___ |\\ |  |  ── |__| |    |___ |__/  |  
  \\/  |  \\  |__] |___ | \\|  |     |  | |___ |___ |  \\  |  </pre>
                <div style="border-bottom: 1px dashed #ff3333; margin: 15px 0;"></div>
                <h3 style="color: #ff3333; margin-top: 0; text-align: center;">[CRITICAL RESILIENCE SYSTEM NOTIFICATION]</h3>
                <pre style="white-space: pre-wrap; font-family: inherit; color: #e5e9f0; line-height: 1.5; font-size: 13px;">
{message_body}</pre>
                <div style="border-bottom: 1px dashed #ff3333; margin: 15px 0;"></div>
                <pre style="margin: 0; color: #5f6a80; font-size: 11px; text-align: center;">
Milestone NVR Consolidated Watchdog Systems -- D:/avigilon_ntp_tools/</pre>
            </div>
        </body>
        </html>
        """
        
        msg.attach(MIMEText(html, 'html', 'utf-8'))
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=20)
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.sendmail(SENDER_EMAIL, RECIPIENT_EMAIL, msg.as_string())
        server.quit()
        print(f"[+] Critical alert email sent: {subject}")
        return True
    except Exception as e:
        print(f"[-] Failed sending critical alert email: {e}")
        return False

def check_nas_hardware(nas_ip="10.0.3.139"):
    try:
        response = os.system(f"ping -n 1 -w 1000 {nas_ip} > nul")
        return response == 0
    except:
        return False

def perform_resilience_diagnostics(current_status):
    """Parses data/zones.json, detects zone power outages, checks NAS status, and triggers critical alerts on state change."""
    print("[*] Performing smart logical resilience diagnostics...")
    
    # 1. Check NAS Hardware Status
    nas_ip = "10.0.3.139"
    nas_online = check_nas_hardware(nas_ip)
    
    # 2. Check Switch Zone Power Status Heuristics
    zones = {}
    if os.path.exists(ZONES_FILE):
        try:
            with open(ZONES_FILE, "r") as f:
                zones = json.load(f)
        except Exception as e:
            print(f"[-] Failed to load zones configuration: {e}")
            
    zone_outages = {}
    for zone_name, ip_list in zones.items():
        if not ip_list:
            continue
        total_in_zone = len(ip_list)
        offline_in_zone = sum(1 for ip in ip_list if current_status.get(ip) == "OFFLINE")
        offline_ratio = offline_in_zone / total_in_zone if total_in_zone > 0 else 0
        
        # Power Failure Heuristic: If 80% or more cameras in a zone are offline simultaneously
        if total_in_zone >= 3 and offline_ratio >= 0.8:
            zone_outages[zone_name] = f"CRITICAL: {offline_in_zone} / {total_in_zone} cameras OFFLINE ({int(offline_ratio*100)}%)"

    # 3. Load Previous Critical State
    prev_state = {"nas": "OK", "zones": {}}
    if os.path.exists(CRITICAL_STATE_FILE):
        try:
            with open(CRITICAL_STATE_FILE, "r") as f:
                prev_state = json.load(f)
        except:
            pass
            
    # Compile current state
    current_nas_state = "OK" if nas_online else "DOWN"
    current_state_dict = {
        "nas": current_nas_state,
        "zones": zone_outages
    }
    
    alerts_triggered = []
    resolutions_triggered = []
    
    # Check NAS status transition
    if prev_state.get("nas") == "OK" and current_nas_state == "DOWN":
        alerts_triggered.append(f"❌ [STORAGE DISCONNECTED] Mapped Cloud NAS ({nas_ip}) became UNREACHABLE on network!\n   -> Impact: Recording services will halt, live playback or video storage access is LOST.")
    elif prev_state.get("nas") == "DOWN" and current_nas_state == "OK":
        resolutions_triggered.append(f"✅ [STORAGE RESTORED] Mapped Cloud NAS ({nas_ip}) returned ONLINE on network.")
        
    # Check Zone status transitions
    prev_zones = prev_state.get("zones", {})
    for zone_name, details in zone_outages.items():
        if zone_name not in prev_zones:
            alerts_triggered.append(f"❌ [POTENTIAL POWER FAILURE] Cabinet/Zone Switch '{zone_name}' lost communication!\n   -> Status: {details}\n   -> Heuristic: Sudden simultaneous blackout indicates potential physical power outage.")
            
    for zone_name in prev_zones.keys():
        if zone_name not in zone_outages:
            resolutions_triggered.append(f"✅ [POWER RESTORED] Cabinet/Zone Switch '{zone_name}' re-established network connection.")

    # 4. Action Alerts / Resolutions
    if alerts_triggered:
        body = "THE SYSTEM HAS DETECTED CRITICAL NETWORK/POWER Resiliency EVENTS:\n\n"
        body += "\n".join(alerts_triggered)
        body += "\n\nImmediate actions recommended: Inspect local zone electrical cabinet, verify Smart UPS battery status, or check network patch cords."
        send_instant_critical_email("🚨 [CRITICAL ALERT] Consolidated NVR System Outage Detected!", body)
        
    if resolutions_triggered:
        body = "THE FOLLOWING SYSTEM ISSUES HAVE BEEN AUTO-RESOLVED:\n\n"
        body += "\n".join(resolutions_triggered)
        body += "\n\nAll services returned to standby/active status."
        send_instant_critical_email("💚 [RESOLVED] NVR System Outages Cleared", body)
        
    # Save current state for next iteration
    try:
        with open(CRITICAL_STATE_FILE, "w") as f:
            json.dump(current_state_dict, f, indent=4)
    except Exception as e:
        print(f"[-] Failed to save critical state file: {e}")

def sync_single_camera(ip, nvr_time, last_status):
    is_online = check_camera_online(ip)
    status_str = "ONLINE" if is_online else "OFFLINE"
    
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
    
    last_status = {}
    if os.path.exists(STATUS_FILE):
        try:
            with open(STATUS_FILE, "r") as f:
                last_status = json.load(f)
        except:
            pass
            
    current_status = {}
    
    with ThreadPoolExecutor(max_workers=12) as executor:
        futures = [executor.submit(sync_single_camera, ip, nvr_time, last_status) for ip in ALL_CAMERAS]
        for f in futures:
            ip, status_str = f.result()
            current_status[ip] = status_str
            
    try:
        with open(STATUS_FILE, "w") as f:
            json.dump(current_status, f)
    except Exception as e:
        print(f"[-] Failed saving status file: {e}")
        
    # Perform power outage and NAS resilience diagnostics
    perform_resilience_diagnostics(current_status)
    
    print("[*] Dual-NVR Clock sync & resilience diagnostics completed.")

if __name__ == "__main__":
    main()
