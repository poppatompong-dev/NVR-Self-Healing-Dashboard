# =====================================================================
# PowerShell Script to Clean Up Legacy Avigilon Scheduled Tasks
# =====================================================================
# Ensure this script is run as Administrator on the NVR machines.
# =====================================================================

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "Legacy Avigilon Task Scheduler Clean-Up Utility" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Check for Administrator privileges
$currentPrincipal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Error "CRITICAL: This script must be run as ADMINISTRATOR. Please reopen PowerShell as Administrator."
    Exit
}

# Define the tasks we want to KEEP (the new ones)
$keepTasks = @(
    "Avigilon Camera 5-Min Silent Watchdog",
    "Avigilon Camera Daily Evening Email Report"
)

Write-Host "[*] Searching for legacy Avigilon / NVR / Camera scheduled tasks..." -ForegroundColor Yellow

# Get all tasks that contain "Avigilon", "NVR", "Watchdog", or "Camera"
$allTasks = Get-ScheduledTask -ErrorAction SilentlyContinue | Where-Object {
    $_.TaskName -like "*Avigilon*" -or 
    $_.TaskName -like "*NVR*" -or 
    $_.TaskName -like "*Watchdog*" -or 
    ($_.TaskName -like "*Camera*" -and $_.TaskPath -eq "\")
}

$legacyTasks = @()

foreach ($task in $allTasks) {
    if ($keepTasks -notcontains $task.TaskName) {
        $legacyTasks += $task
    }
}

if ($legacyTasks.Count -eq 0) {
    Write-Host "[+] No legacy tasks found. System is clean!" -ForegroundColor Green
} else {
    Write-Host "[!] Found $($legacyTasks.Count) legacy scheduled task(s):" -ForegroundColor Red
    foreach ($task in $legacyTasks) {
        Write-Host "    -> '$($task.TaskName)' [State: $($task.State)]" -ForegroundColor Yellow
    }
    
    Write-Host "[*] Starting unregistration of legacy tasks..." -ForegroundColor Yellow
    foreach ($task in $legacyTasks) {
        try {
            Unregister-ScheduledTask -TaskName $task.TaskName -Confirm:$false -ErrorAction Stop
            Write-Host "[+] Successfully removed legacy task: '$($task.TaskName)'" -ForegroundColor Green
        } catch {
            Write-Host "[-] Failed to remove task '$($task.TaskName)': $($_.Exception.Message)" -ForegroundColor Red
        }
    }
}

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "Clean-up complete. Only the active consolidated tasks remain." -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Cyan
