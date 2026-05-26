import os
import sys
import socket
import smtplib
import json
import time
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import xml.etree.ElementTree as ET
import requests
from requests.auth import HTTPDigestAuth
from concurrent.futures import ThreadPoolExecutor

# ==================== CONFIGURATION ====================
# Email SMTP Configuration
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = "poppatompong@gmail.com"
SMTP_PASSWORD = "yqkmfuoonilelecm"
SENDER_EMAIL = "poppatompong@gmail.com"
RECIPIENT_EMAIL = "poppatompong@gmail.com"

# NVR 1 Camera List (11 Cameras)
NVR1_IPS = [
    "10.0.3.147", "10.0.3.154", "10.0.3.158", "10.0.3.161", "10.0.3.164", 
    "10.0.3.167", "10.0.3.170", "10.0.3.173", "10.0.3.176", "10.0.3.179", "10.0.3.180"
]

# NVR 2 Camera List (22 Cameras - skipping Gateway/Switch .254)
NVR2_IPS = [
    "10.0.3.148", "10.0.3.149", "10.0.3.150", "10.0.3.152", "10.0.3.153", 
    "10.0.3.155", "10.0.3.156", "10.0.3.157", "10.0.3.159", "10.0.3.160", 
    "10.0.3.162", "10.0.3.163", "10.0.3.165", "10.0.3.166", "10.0.3.168", 
    "10.0.3.169", "10.0.3.171", "10.0.3.172", "10.0.3.174", "10.0.3.175", 
    "10.0.3.177", "10.0.3.178"
]

BASE_DIR = r"D:\avigilon_ntp_tools"
REPORTS_DIR = os.path.join(BASE_DIR, "logs")
DATA_DIR = os.path.join(BASE_DIR, "data")
DOWNTIME_FILE = os.path.join(DATA_DIR, "downtime_events.json")

# =======================================================

if not os.path.exists(REPORTS_DIR):
    os.makedirs(REPORTS_DIR)
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

headers = {'Content-Type': 'application/soap+xml; charset=utf-8'}

def get_camera_creds(ip):
    """Dynamic credentials lookup for cameras across both NVRs."""
    if ip in NVR1_IPS:
        return "administrator", "Admin1234"
    admin_123_ips = ["10.0.3.148", "10.0.3.156", "10.0.3.160", "10.0.3.171", "10.0.3.174", "10.0.3.175"]
    if ip in admin_123_ips:
        return "admin", "Admin@123"
    else:
        return "Admin", "1234"

def check_nvr_internet():
    try:
        socket.setdefaulttimeout(3)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(("8.8.8.8", 53))
        return True
    except Exception:
        return False

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
    raise Exception(f"HTTP Error {r.status_code}")

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

def scan_single_camera(ip, nvr_time):
    cam_result = {
        "ip": ip,
        "online": False,
        "status": "OFFLINE",
        "time_str": "-",
        "offset": "-",
        "action": "None"
    }
    
    if check_camera_online(ip):
        cam_result["online"] = True
        try:
            cam_time = get_camera_time(ip)
            cam_result["time_str"] = cam_time.strftime("%Y-%m-%d %H:%M:%S")
            
            offset = (nvr_time - cam_time).total_seconds()
            cam_result["offset"] = f"{offset:+.1f}s"
            
            if abs(offset) > 2.0:
                try:
                    force_camera_sync(ip)
                    cam_result["action"] = "AUTO-SYNC (Forced)"
                    cam_result["status"] = "SYNCED"
                    
                    verified_time = get_camera_time(ip)
                    new_offset = (nvr_time - verified_time).total_seconds()
                    cam_result["offset"] = f"{new_offset:+.1f}s (Synced)"
                except Exception as sync_err:
                    cam_result["action"] = f"SYNC_ERR: {sync_err}"
                    cam_result["status"] = "SKEWED"
            else:
                cam_result["status"] = "OK"
                cam_result["action"] = "None"
        
        except Exception as e:
            cam_result["status"] = "QUERY_ERR"
            cam_result["action"] = f"Error: {e}"
    else:
        cam_result["status"] = "OFFLINE"
        cam_result["action"] = "Port 80 unreachable"
        
    return cam_result

def scan_nvr_cameras_parallel(nvr_ips, nvr_time):
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(scan_single_camera, ip, nvr_time) for ip in nvr_ips]
        return [f.result() for f in futures]

def make_ascii_bar(ratio, width=30):
    filled = int(round(ratio * width))
    return "█" * filled + "░" * (width - filled)

def build_table_html(results):
    table_content = ""
    for r in results:
        ip = r["ip"].ljust(15)
        status_raw = r["status"]
        
        status_styled = status_raw
        if status_raw == "OK":
            status_styled = '<span style="color: #00ff66;">OK</span>'
        elif status_raw == "SYNCED":
            status_styled = '<span style="color: #00ffff;">SYNCED</span>'
        elif status_raw == "OFFLINE":
            status_styled = '<span style="color: #ff3333;">OFFLINE</span>'
        else:
            status_styled = f'<span style="color: #ffaa00;">{status_raw}</span>'
            
        online_str = "ONLINE".ljust(8) if r["online"] else "OFFLINE".ljust(8)
        online_styled = f'<span style="color: #00ff66;">{online_str}</span>' if r["online"] else f'<span style="color: #ff3333;">{online_str}</span>'
        
        time_str = r["time_str"].ljust(19)
        offset = r["offset"].ljust(16)
        action = r["action"]
        
        table_content += f"{ip} | {online_styled} | {time_str} | {offset} | {status_styled} | {action}\n"
    return table_content

def process_downtime_events():
    """Reads and formats downtime events for the report, then clears the file."""
    events = []
    if os.path.exists(DOWNTIME_FILE):
        try:
            with open(DOWNTIME_FILE, "r") as f:
                events = json.load(f)
            # Clear file after reading
            with open(DOWNTIME_FILE, "w") as f:
                json.dump([], f)
        except Exception as e:
            print(f"Error reading downtime events: {e}")
            
    if not events:
        return "NO DOWNTIME EVENTS OR FLAPPING DETECTED SINCE LAST REPORT."
        
    log_content = ""
    for ev in events:
        timestamp = ev.get('timestamp', '').ljust(20)
        ip = ev.get('ip', '').ljust(16)
        event_desc = ev.get('event', '')
        
        # Colorize event based on OFFLINE vs ONLINE
        if "OFFLINE" in event_desc and "ONLINE" not in event_desc.split("->")[1]:
            event_styled = f'<span style="color: #ff3333;">{event_desc}</span>'
        elif "ONLINE" in event_desc.split("->")[1]:
            event_styled = f'<span style="color: #00ff66;">{event_desc}</span>'
        else:
            event_styled = f'<span style="color: #ffaa00;">{event_desc}</span>'
            
        log_content += f"{timestamp}| {ip}| {event_styled}\n"
        
    return log_content

def generate_report_cli_html(nvr_time, nvr_internet, nvr1_results, nvr2_results):
    nvr1_total = len(nvr1_results)
    nvr1_online = sum(1 for r in nvr1_results if r["online"])
    nvr1_ratio = nvr1_online / nvr1_total if nvr1_total > 0 else 0
    
    nvr2_total = len(nvr2_results)
    nvr2_online = sum(1 for r in nvr2_results if r["online"])
    nvr2_ratio = nvr2_online / nvr2_total if nvr2_total > 0 else 0
    
    total_cameras = nvr1_total + nvr2_total
    total_online = nvr1_online + nvr2_online
    overall_online_ratio = total_online / total_cameras if total_cameras > 0 else 0
    
    nvr1_synced = sum(1 for r in nvr1_results if r["status"] in ["OK", "SYNCED"])
    nvr2_synced = sum(1 for r in nvr2_results if r["status"] in ["OK", "SYNCED"])
    total_synced = nvr1_synced + nvr2_synced
    overall_sync_ratio = total_synced / total_cameras if total_cameras > 0 else 0
    
    net_str = "ONLINE  (INTERNET ENABL)" if nvr_internet else "OFFLINE (LOCAL MODE)"
    
    nvr1_table = build_table_html(nvr1_results)
    nvr2_table = build_table_html(nvr2_results)
    downtime_log_html = process_downtime_events()
    
    html = f"""<!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Consolidated NVR Clock Sync Report</title>
    </head>
    <body style="margin: 0; padding: 0; background-color: #0c1017; font-family: 'Consolas', 'Courier New', Monaco, monospace; color: #88c0d0; font-size: 13px; line-height: 1.4;">
        <div style="max-width: 900px; margin: 20px auto; padding: 25px; background-color: #080c12; border: 1px solid #1f2d3d; border-radius: 6px; box-shadow: 0 0 30px rgba(0, 255, 102, 0.05);">
            
            <!-- Retro Terminal Header -->
            <pre style="margin: 0; padding: 0; font-family: inherit; color: #00ff66; font-weight: bold; line-height: 1.15; text-align: center;">
 _   _ _   _ ___ _____ ___ _____ ____     ____ ___  _   _ ____   ___  _     ___ ____    _  _____ _____ ____  
| | | | \\ | |_ _|  ___|_ _| ____|  _ \\   / ___/ _ \\| \\ | / ___| / _ \\| |   |_ _|  _ \\  / \\|_   _| ____|  _ \\ 
| | | |  \\| || || |_   | ||  _| | | | | | |  | | | |  \\| \\___ \\| | | | |    | || | | |/ _ \\ | | |  _| | | | |
| |_| | |\\  || ||  _|  | || |___| |_| | | |__| |_| | |\\  |___) | |_| | |___ | || |_| / ___ \\| | | |___| |_| |
 \\___/|_| \\_|___|_|   |___|_____|____/   \\____\\___/|_| \\_|____/ \\___/|_____|___|____/_/   \\_\\|_| |_____|____/ </pre>
            
            <div style="border-bottom: 1px dashed #1f2d3d; margin: 15px 0;"></div>
            
            <!-- System Stats -->
            <pre style="margin: 0 0 20px 0; padding: 0; font-family: inherit; color: #8892b0;">
[CONSOLIDATED DUAL-SERVER DIAGNOSTIC & TIME CONTROL REPORT]
----------------------------------------------------------------------------------------------------
SYSTEM LOCAL TIME   : <span style="color: #00f5ff; font-weight: bold;">{nvr_time.strftime("%Y-%m-%d %H:%M:%S")}</span>
NVR NETWORK STATUS  : <span style="color: {'#00ff66' if nvr_internet else '#ff3333'}; font-weight: bold;">{net_str}</span>
CORE ENGINE STATUS  : <span style="color: #00ff66; font-weight: bold;">STANDBY & ACTIVE (HIERARCHICAL NTP ENGINE)</span>
----------------------------------------------------------------------------------------------------</pre>

            <!-- Retro ASCII Summary Chart -->
            <pre style="margin: 0 0 25px 0; padding: 15px; font-family: inherit; color: #00ff66; background-color: #05080c; border: 1px solid #14251c; border-radius: 4px;">
<span style="color: #8892b0; font-weight: bold;">[================================ SYSTEM HEALTH STATUS CHARTS ================================]</span>

NVR 1 (10.0.3.138)  : <span style="color: #00ff66;">[{make_ascii_bar(nvr1_ratio)}] {nvr1_online:02d} / {nvr1_total:02d} Online ({int(nvr1_ratio*100)}%)</span>
NVR 2 (10.0.3.137)  : <span style="color: #00ff66;">[{make_ascii_bar(nvr2_ratio)}] {nvr2_online:02d} / {nvr2_total:02d} Online ({int(nvr2_ratio*100)}%)</span>

OVERALL CONNECTIVITY: <span style="color: #00ffff;">[{make_ascii_bar(overall_online_ratio)}] {total_online:02d} / {total_cameras:02d} Online ({int(overall_online_ratio*100)}%)</span>
CLOCK SYNCHRONY RATE: <span style="color: #00f5ff;">[{make_ascii_bar(overall_sync_ratio)}] {total_synced:02d} / {total_cameras:02d} Synced ({int(overall_sync_ratio*100)}%)</span></pre>

            <!-- SECTION: FLAPPING AND DOWNTIME LOG -->
            <pre style="margin: 0 0 10px 0; padding: 0; font-family: inherit; color: #ffaa00; font-weight: bold;">
[SECTION 0: CAMERA INSTABILITY & DOWNTIME EVENTS (SINCE LAST REPORT)]</pre>
            <pre style="margin: 0 0 25px 0; padding: 0; font-family: inherit; color: #e5e9f0; overflow-x: auto; white-space: pre;">
{downtime_log_html}</pre>

            <!-- SECTION 1: NVR 1 -->
            <pre style="margin: 0 0 10px 0; padding: 0; font-family: inherit; color: #00ffff; font-weight: bold;">
[SECTION 1: NVR 10.0.3.138 (MASTER NVR) -- {nvr1_online}/{nvr1_total} CAMERAS ONLINE]</pre>
            <pre style="margin: 0 0 25px 0; padding: 0; font-family: inherit; color: #e5e9f0; overflow-x: auto; white-space: pre;">
<span style="color: #8892b0; font-weight: bold;">CAMERA IP       | NET-STAT | CAMERA TIME (LOCAL) | OFFSET           | STATUS  | TASK ACTION</span>
------------------------------------------------------------------------------------------------------------
{nvr1_table}------------------------------------------------------------------------------------------------------------</pre>

            <!-- SECTION 2: NVR 2 -->
            <pre style="margin: 0 0 10px 0; padding: 0; font-family: inherit; color: #00ffff; font-weight: bold;">
[SECTION 2: NVR 10.0.3.137 (CLIENT NVR) -- {nvr2_online}/{nvr2_total} CAMERAS ONLINE]</pre>
            <pre style="margin: 0 0 20px 0; padding: 0; font-family: inherit; color: #e5e9f0; overflow-x: auto; white-space: pre;">
<span style="color: #8892b0; font-weight: bold;">CAMERA IP       | NET-STAT | CAMERA TIME (LOCAL) | OFFSET           | STATUS  | TASK ACTION</span>
------------------------------------------------------------------------------------------------------------
{nvr2_table}------------------------------------------------------------------------------------------------------------</pre>

            <pre style="margin: 20px 0 0 0; padding: 0; font-family: inherit; color: #5f6a80; font-size: 11px; text-align: center;">
====================================================================================================
[CONSOLE CONSOLIDATED REPORT COMPLETE] -- SCHEDULED & SECURED
Milestone NVR Consolidated Watchdog Systems -- D:\\avigilon_ntp_tools\\
====================================================================================================</pre>
        </div>
    </body>
    </html>
    """
    return html

def save_report_locally(html_content, nvr_time):
    timestamp = nvr_time.strftime("%Y-%m-%d_%H%M")
    report_filename = f"consolidated_report_{timestamp}.html"
    report_path = os.path.join(REPORTS_DIR, report_filename)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    return report_path

def send_email_report(html_content, nvr_time, nvr_internet):
    if not nvr_internet:
        print("[-] Skipping email sending: NVR Wi-Fi has no internet access.")
        return False
        
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f"💻 [Console Consolidated NVR] System Diagnostic Report: {nvr_time.strftime('%Y-%m-%d %H:%M')}"
        msg['From'] = SENDER_EMAIL
        msg['To'] = RECIPIENT_EMAIL
        
        msg_text = MIMEText(html_content, 'html', 'utf-8')
        msg.attach(msg_text)
            
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=30)
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.sendmail(SENDER_EMAIL, RECIPIENT_EMAIL, msg.as_string())
        server.quit()
        print("[+] Consolidated Email successfully sent to poppatompong@gmail.com!")
        return True
    except Exception as email_err:
        print(f"[-] Failed to send email via SMTP: {email_err}")
        return False

def main():
    print("[*] Starting Consolidated Avigilon NVR Clock Sync and Health Diagnosis Job...")
    nvr_time = datetime.now()
    nvr_internet = check_nvr_internet()
    
    print(f"[*] Local Reference Time: {nvr_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"[*] NVR Internet Connected: {nvr_internet}")
    
    print("[*] Scanning NVR 1 Cameras (11 nodes) in Parallel...")
    nvr1_results = scan_nvr_cameras_parallel(NVR1_IPS, nvr_time)
    
    print("[*] Scanning NVR 2 Cameras (22 nodes) in Parallel...")
    nvr2_results = scan_nvr_cameras_parallel(NVR2_IPS, nvr_time)
    
    html_content = generate_report_cli_html(nvr_time, nvr_internet, nvr1_results, nvr2_results)
    
    local_path = save_report_locally(html_content, nvr_time)
    print(f"[+] Saved local consolidated report to: {local_path}")
    
    send_email_report(html_content, nvr_time, nvr_internet)
    print("[*] Finished execution successfully.")

if __name__ == "__main__":
    main()
