# Деплой FinFit бота на Timeweb VPS
# Запуск: powershell -ExecutionPolicy Bypass -File deploy_remote.ps1

$ErrorActionPreference = "Stop"
$HostIP = "147.45.150.25"
$User = "root"
$Password = $env:FINBOT_SSH_PASSWORD
if (-not $Password) {
    Write-Host "Set FINBOT_SSH_PASSWORD env var with server root password" -ForegroundColor Red
    exit 1
}
$LocalDir = $PSScriptRoot
$RemoteDir = "/opt/finbot"

# Deploy via PuTTY plink/scp
$ErrorActionPreference = "Stop"
$HostIP = "147.45.150.25"
$User = "root"
$Password = $env:FINBOT_SSH_PASSWORD
if (-not $Password) {
    Write-Host "Set FINBOT_SSH_PASSWORD env var with server root password" -ForegroundColor Red
    exit 1
}
$LocalDir = $PSScriptRoot
$RemoteDir = "/opt/finbot"
$ToolsDir = Join-Path $env:TEMP "putty_tools"
$Plink = Join-Path $ToolsDir "plink.exe"
$Pscp = Join-Path $ToolsDir "pscp.exe"

if (-not (Test-Path $Plink)) {
    New-Item -ItemType Directory -Force -Path $ToolsDir | Out-Null
    Invoke-WebRequest -Uri "https://the.earth.li/~sgtatham/putty/latest/w64/plink.exe" -OutFile $Plink
    Invoke-WebRequest -Uri "https://the.earth.li/~sgtatham/putty/latest/w64/pscp.exe" -OutFile $Pscp
}

$HostKey = "ssh-ed25519 255 SHA256:Y7V97HYLX971vADi1yVZuQIO9WMH0qVXg0L2Vnz3vLo"

function Invoke-Remote([string]$cmd) {
    Write-Host ">> $cmd"
    & $Plink -batch -hostkey $HostKey -ssh "${User}@${HostIP}" -pw $Password $cmd 2>&1
}

Write-Host "Connecting to $HostIP..."
Invoke-Remote "echo connected && whoami"

Invoke-Remote "mkdir -p $RemoteDir"

$files = @(
    "bot.py", "config.py", "database.py", "handlers.py", "keyboards.py",
    "payments.py", "scheduler.py", "access.py", "getcourse.py",
    "requirements.txt", "finbot.service", ".env"
)

foreach ($f in $files) {
    $local = Join-Path $LocalDir $f
    if (-not (Test-Path $local)) { continue }
    Write-Host "Upload: $f"
    & $Pscp -batch -hostkey $HostKey -pw $Password $local "${User}@${HostIP}:${RemoteDir}/$f" 2>&1
}
$setupScript = @'
set -e
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip nginx > /dev/null 2>&1 || true

cd /opt/finbot
python3 -m venv venv
./venv/bin/pip install -q -r requirements.txt

cat > /etc/systemd/system/finbot.service << 'SVCEOF'
[Unit]
Description=FinFit Telegram Bot
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/finbot
ExecStart=/opt/finbot/venv/bin/python bot.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SVCEOF

cat > /etc/nginx/sites-available/finbot << 'NGXEOF'
server {
    listen 80;
    server_name _;

    location /robokassa/ {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
NGXEOF
ln -sf /etc/nginx/sites-available/finbot /etc/nginx/sites-enabled/finbot
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx || true

systemctl daemon-reload
systemctl enable finbot
systemctl restart finbot
sleep 3
systemctl is-active finbot
journalctl -u finbot -n 5 --no-pager
'@

$setupFile = Join-Path $env:TEMP "finbot_setup.sh"
$setupScript | Out-File -FilePath $setupFile -Encoding utf8
& $Pscp -batch -hostkey $HostKey -pw $Password $setupFile "${User}@${HostIP}:/tmp/finbot_setup.sh" 2>&1
Invoke-Remote "bash /tmp/finbot_setup.sh"

Write-Host ""
Write-Host "=== DONE ===" -ForegroundColor Green
Write-Host "Robokassa ResultURL: http://147.45.150.25/robokassa/result"
