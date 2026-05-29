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
# COMPREHENSIVE CLEAN-UP OF ALL LEGACY TASKS (To prevent duplicate emails)
# =====================================================================
Write-Host "[*] Scanning for any legacy Avigilon / NVR / Camera scheduled tasks..." -ForegroundColor Yellow

$keepTasks = @(
    "Avigilon Camera 5-Min Silent Watchdog",
    "Avigilon Camera Daily Evening Email Report"
)

# Get all tasks that contain "Avigilon", "NVR", "Watchdog", or "Camera"
$allTasks = Get-ScheduledTask -ErrorAction SilentlyContinue | Where-Object {
    $_.TaskName -like "*Avigilon*" -or 
    $_.TaskName -like "*NVR*" -or 
    $_.TaskName -like "*Watchdog*" -or 
    ($_.TaskName -like "*Camera*" -and $_.TaskPath -eq "\")
}

foreach ($task in $allTasks) {
    if ($keepTasks -notcontains $task.TaskName) {
        Write-Host "[!] Found legacy task: '$($task.TaskName)' - Removing to stop spam emails..." -ForegroundColor Red
        Unregister-ScheduledTask -TaskName $task.TaskName -Confirm:$false -ErrorAction SilentlyContinue
    }
}

# =====================================================================
# TASK 1: Silent high-frequency sync and alert (Every 5 minutes)
# =====================================================================
$newTask1Name = "Avigilon Camera 5-Min Silent Watchdog"

Write-Host "[*] Registering Task 1: 5-Minute Silent Watchdog..." -ForegroundColor Yellow

# Trigger: Runs once at 12:00 AM and repeats every 5 minutes indefinitely
$syncTrigger = New-ScheduledTaskTrigger -Once -At "12:00 AM" -RepetitionInterval (New-TimeSpan -Minutes 5)
$syncAction = New-ScheduledTaskAction -Execute $pythonPath -Argument "`"$syncScript`""

Register-ScheduledTask -TaskName $newTask1Name -Trigger $syncTrigger -Action $syncAction -Principal $principal -Force | Out-Null

if ($?) {
    Write-Host "[+] SUCCESS: Task '$newTask1Name' registered (repeats every 5 minutes)." -ForegroundColor Green
} else {
    Write-Host "[!] ERROR: Failed to register 5-minute watchdog task." -ForegroundColor Red
}

# =====================================================================
# TASK 2: Daily Evening HTML and Time Sync Reporting (05:00 PM)
# =====================================================================
$newTask2Name = "Avigilon Camera Daily Evening Email Report"

Write-Host "[*] Registering Task 2: Daily Evening Email Report..." -ForegroundColor Yellow

# Trigger: Runs daily at 5:00 PM (17:00 น.)
$reportTrigger = New-ScheduledTaskTrigger -Daily -At "5:00 PM"
$reportAction = New-ScheduledTaskAction -Execute $pythonPath -Argument "`"$reportScript`""

Register-ScheduledTask -TaskName $newTask2Name -Trigger $reportTrigger -Action $reportAction -Principal $principal -Force | Out-Null

if ($?) {
    Write-Host "[+] SUCCESS: Task '$newTask2Name' registered (runs daily at 05:00 PM)." -ForegroundColor Green
} else {
    Write-Host "[!] ERROR: Failed to register daily evening reporting task." -ForegroundColor Red
}

# =====================================================================
# TASK 3: Persistent Web Dashboard & Cloud Agent (At Boot Startup)
# =====================================================================
$newTask3Name = "Avigilon NVR Web Dashboard Agent"
$dashboardScript = "$baseDir\src\web_dashboard.py"

Write-Host "[*] Registering Task 3: Persistent Web Dashboard Agent..." -ForegroundColor Yellow

# Trigger: Runs automatically when the NVR machine boots up
$dashboardTrigger = New-ScheduledTaskTrigger -AtStartup
$dashboardAction = New-ScheduledTaskAction -Execute $pythonPath -Argument "`"$dashboardScript`""

# Task Settings: Set ExecutionTimeLimit to 0 (Unlimited/Infinite execution) so the server never shuts down
$taskSettings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 99 -RestartInterval (New-TimeSpan -Minutes 2)

Register-ScheduledTask -TaskName $newTask3Name -Trigger $dashboardTrigger -Action $dashboardAction -Principal $principal -Settings $taskSettings -Force | Out-Null

if ($?) {
    Write-Host "[+] SUCCESS: Task '$newTask3Name' registered (starts automatically at system boot and runs 24/7)." -ForegroundColor Green
} else {
    Write-Host "[!] ERROR: Failed to register persistent web dashboard agent task." -ForegroundColor Red
}

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "Installation completed. All 3 tasks registered successfully!" -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Cyan

