Write-Host "Configuring Windows as an NTP Server..."
Set-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Services\W32Time\TimeProviders\NtpServer" -Name "Enabled" -Value 1
Set-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Services\W32Time\Config" -Name "AnnounceFlags" -Value 5
Restart-Service w32time

Write-Host "Configuring Windows Firewall for NTP (UDP 123)..."
New-NetFirewallRule -Name "NTP Server" -DisplayName "NTP Server (UDP 123)" -Direction Inbound -Protocol UDP -LocalPort 123 -Action Allow

Write-Host "Verification: "
w32tm /query /configuration | findstr /i "Enabled AnnounceFlags"
Write-Host "Done! You can close this window."
Pause
