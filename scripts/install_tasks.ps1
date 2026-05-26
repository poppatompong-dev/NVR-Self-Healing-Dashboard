# =====================================================================
# PowerShell Script to Install Avigilon Time Sync & Report Task on NVR
# =====================================================================
# Ensure this script is run as Administrator on the NVR machine.
# =====================================================================

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "Installing Avigilon Time Sync & Health Reporting Service" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Check for Administrator privileges
$currentPrincipal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Error "CRITICAL: This script must be run as ADMINISTRATOR. Please reopen PowerShell as Administrator."
    Exit
}

# 2. Check if Python is installed (with Smart Auto-Detection)
Write-Host "[*] Checking Python installation..." -ForegroundColor Yellow
$pythonPath = "python"
$pythonCheck = Get-Command python -ErrorAction SilentlyContinue

if (-not $pythonCheck) {
    Write-Host "[*] python.exe not found on system PATH. Searching standard directories..." -ForegroundColor Yellow
    # Common search patterns for Python in Windows User and Program Files paths
    $searchPaths = @(
        "$env:LOCALAPPDATA\Programs\Python\Python*\python.exe",
        "$env:USERPROFILE\AppData\Local\Programs\Python\Python*\python.exe",
        "C:\Users\Administrator\AppData\Local\Programs\Python\Python*\python.exe",
        "C:\Program Files\Python*\python.exe",
        "C:\Program Files (x86)\Python*\python.exe"
    )
    
    foreach ($pathPattern in $searchPaths) {
        $found = Resolve-Path $pathPattern -ErrorAction SilentlyContinue
        if ($found) {
            # Use the first found python executable path
            $pythonPath = $found[0].Path
            break
        }
    }
} else {
    $pythonPath = $pythonCheck.Source
}

if ($pythonPath -eq "python" -and -not $pythonCheck) {
    Write-Host "[!] WARNING: python.exe was not found on your system PATH or standard directories." -ForegroundColor Red
    Write-Host "    Please download and install Python 3.x on the NVR from https://www.python.org/downloads/" -ForegroundColor Red
    Write-Host "    Make sure to check the box 'Add python.exe to PATH' during installation!" -ForegroundColor Red
    Exit
} else {
    # Resolve to full path
    $pythonPath = (Get-Item $pythonPath).FullName
    Write-Host "[+] Python executable located: $pythonPath" -ForegroundColor Green
}

# 3. Install required Python packages (requests)
Write-Host "[*] Installing required Python packages (requests)..." -ForegroundColor Yellow
& $pythonPath -m pip install --upgrade pip
& $pythonPath -m pip install requests
if ($LASTEXITCODE -eq 0) {
    Write-Host "[+] Required Python libraries installed successfully!" -ForegroundColor Green
} else {
    Write-Host "[!] ERROR: Failed to install Python 'requests' library via pip. Please ensure the NVR has internet access." -ForegroundColor Red
    Exit
}

# 4. Create Folder Paths
$baseDir = "D:\avigilon_ntp_tools"
$syncScript = "$baseDir\src\nvr_watchdog.py"
$reportScript = "$baseDir\src\unified_report.py"

if (-not (Test-Path $baseDir)) {
    Write-Host "[!] Warning: Directory not found at $baseDir. Please make sure to copy files to D:\avigilon_ntp_tools" -ForegroundColor Yellow
}

# Define principal (Run under SYSTEM with Highest privileges so it runs 24/7 in background)
$principal = New-ScheduledTaskPrincipal -UserId "NT AUTHORITY\SYSTEM" -LogonType ServiceAccount -RunLevel Highest

# =====================================================================
# TASK 1: Silent high-frequency sync and alert (Every 15 minutes)
# =====================================================================
Write-Host "[*] Registering Task 1: 15-Minute Sync and Alert..." -ForegroundColor Yellow
$task1Name = "Avigilon Camera 15-Min Clock Sync and Alert"

# Trigger: Runs once at 12:00 AM and repeats every 15 minutes indefinitely
$syncTrigger = New-ScheduledTaskTrigger -Once -At "12:00 AM" -RepetitionInterval (New-TimeSpan -Minutes 15)
$syncAction = New-ScheduledTaskAction -Execute $pythonPath -Argument "`"$syncScript`""

Register-ScheduledTask -TaskName $task1Name -Trigger $syncTrigger -Action $syncAction -Principal $principal -Force | Out-Null

if ($?) {
    Write-Host "[+] SUCCESS: Task '$task1Name' registered (repeats every 15 minutes)." -ForegroundColor Green
} else {
    Write-Host "[!] ERROR: Failed to register 15-minute sync task." -ForegroundColor Red
}

# =====================================================================
# TASK 2: Twice-a-day full HTML and snapshot reporting (08:00 AM & 05:00 PM)
# =====================================================================
Write-Host "[*] Registering Task 2: Twice-Daily Email Report..." -ForegroundColor Yellow
$task2Name = "Avigilon Camera Twice-Daily Email Report"

# Triggers: 08:00 AM and 05:00 PM
$triggerA = New-ScheduledTaskTrigger -Daily -At "8:00 AM"
$triggerB = New-ScheduledTaskTrigger -Daily -At "5:00 PM"
$reportTriggers = @($triggerA, $triggerB)

$reportAction = New-ScheduledTaskAction -Execute $pythonPath -Argument "`"$reportScript`""

Register-ScheduledTask -TaskName $task2Name -Trigger $reportTriggers -Action $reportAction -Principal $principal -Force | Out-Null

if ($?) {
    Write-Host "[+] SUCCESS: Task '$task2Name' registered (runs at 08:00 AM and 05:00 PM)." -ForegroundColor Green
} else {
    Write-Host "[!] ERROR: Failed to register twice-daily reporting task." -ForegroundColor Red
}

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "Installation completed. Both tasks registered successfully!" -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Cyan
