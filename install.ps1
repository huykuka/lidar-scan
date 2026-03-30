# ============================================================
#  LiDAR Studio - Windows Installer
#  Supports: Windows 10 & 11, Run as Administrator
# ============================================================

param(
    [switch]$SkipWSL,
    [switch]$SkipDocker
)

$ErrorActionPreference = "Stop"

# ── Colours ─────────────────────────────────────────────────
function Write-Step { param($msg) Write-Host "`n[>>] $msg" -ForegroundColor Cyan }
function Write-Ok   { param($msg) Write-Host "[OK] $msg"  -ForegroundColor Green }
function Write-Warn { param($msg) Write-Host "[!!] $msg"  -ForegroundColor Yellow }
function Write-Err  { param($msg) Write-Host "[XX] $msg"  -ForegroundColor Red }


# ── Run a command inside WSL as root ────────────────────────
function Invoke-Wsl {
    param($Command)
    wsl -u root -- bash -c $Command
    if ($LASTEXITCODE -ne 0) {
        Write-Err "WSL command failed: $Command"
        exit 1
    }
}

# ── Run a command inside WSL as root, allow failure ─────────
function Invoke-WslSafe {
    param($Command)
    wsl -u root -- bash -c $Command
}

# ── Admin check ─────────────────────────────────────────────
function Assert-Admin {
    $current = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
    if (-not $current.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        Write-Err "Please re-run this script as Administrator (right-click -> Run as administrator)"
        exit 1
    }
}

# ── Windows version check ────────────────────────────────────
$script:IsWin11 = $false
function Assert-WindowsVersion {
    Write-Step "Checking Windows version..."
    $build   = [System.Environment]::OSVersion.Version.Build
    $edition = (Get-WmiObject Win32_OperatingSystem).Caption
    Write-Host "  $edition (Build $build)"
    if ($build -lt 22621) {
        Write-Warn "Windows 10 detected - WSL mirrored networking not supported, using NAT."
        Write-Warn "App will work on localhost. A port proxy will be set up for LAN access."
        $script:IsWin11 = $false
    } else {
        Write-Ok "Windows 11 - mirrored networking supported"
        $script:IsWin11 = $true
    }
}

# ── WSL ──────────────────────────────────────────────────────
function Install-WSL {
    Write-Step "Checking WSL..."
    $wslInstalled = Get-Command wsl -ErrorAction SilentlyContinue
    if ($wslInstalled) {
        Write-Ok "WSL is already installed"
    } else {
        Write-Host "  Installing WSL with Ubuntu..."
        wsl --install -d Ubuntu
        Write-Warn "A reboot is required. Reboot and re-run this script to continue."
        $reboot = Read-Host "  Reboot now? (y/N)"
        if ($reboot -eq 'y') { Restart-Computer -Force }
        exit 0
    }
    Write-Host "  Updating WSL kernel..."
    wsl --update | Out-Null
    Write-Ok "WSL kernel up to date"
}

# ── WSL mirrored networking (Win11 only) ─────────────────────
function Set-WSLMirroredNetworking {
    if (-not $script:IsWin11) {
        Write-Step "Skipping mirrored networking (Windows 10 not supported)"
        return
    }
    Write-Step "Configuring WSL mirrored networking..."
    $wslConfig = "$env:USERPROFILE\.wslconfig"
    if (Test-Path $wslConfig) {
        $content = Get-Content $wslConfig -Raw
        if ($content -match "networkingMode\s*=\s*mirrored") {
            Write-Ok "Mirrored networking already configured"
            return
        }
        if ($content -match "\[wsl2\]") {
            $content = $content -replace "(\[wsl2\][^\[]*)", "`$1networkingMode=mirrored`n"
        } else {
            $content += "`n[wsl2]`nnetworkingMode=mirrored"
        }
    } else {
        $content = "[wsl2]`nnetworkingMode=mirrored"
    }
    [System.IO.File]::WriteAllText($wslConfig, $content, [System.Text.UTF8Encoding]::new($false))
    Write-Ok "Mirrored networking enabled"
    Write-Host "  Restarting WSL..."
    wsl --shutdown
    Start-Sleep -Seconds 3
    Write-Ok "WSL restarted"
}

# ── Docker Engine inside WSL ─────────────────────────────────
function Install-DockerInWSL {
    Write-Step "Checking Docker Engine in WSL..."

    # Check if real native Docker is installed (not Docker Desktop stub)
    # Real docker binary lives at /usr/bin/docker - Desktop stub is a shim with no daemon
    $dockerBin = wsl -u root -- bash -c "test -f /usr/bin/docker && /usr/bin/docker version --format '{{.Server.Version}}' 2>/dev/null || echo 'NOT_FOUND'"
    if ($dockerBin -and $dockerBin -notmatch "NOT_FOUND" -and $dockerBin -notmatch "could not be found") {
        Write-Ok "Docker Engine already installed: v$dockerBin"
        Invoke-WslSafe "service docker start"
        return
    }

    Write-Step "Installing Docker Engine inside WSL..."
    Write-Host "  (Removing Docker Desktop WSL integration if present...)"
    Invoke-WslSafe "rm -f /usr/local/bin/docker /usr/local/bin/docker-compose"

    # 1. Remove old/conflicting packages
    Write-Host "  Removing old Docker packages..."
    Invoke-WslSafe "apt-get remove -y docker docker-engine docker.io containerd runc 2>/dev/null"

    # 2. Install prerequisites
    Write-Host "  Installing prerequisites..."
    Invoke-Wsl "apt-get update -qq && apt-get install -y -qq ca-certificates curl gnupg lsb-release"

    # 3. Add Docker GPG key
    Write-Host "  Adding Docker GPG key..."
    Invoke-Wsl "install -m 0755 -d /etc/apt/keyrings"
    Invoke-Wsl "curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --yes --dearmor -o /etc/apt/keyrings/docker.gpg && chmod a+r /etc/apt/keyrings/docker.gpg"

    # 4. Add Docker repo
    Write-Host "  Adding Docker repository..."
    # Get arch and codename from WSL, build the repo line in PowerShell, write it directly
    $arch     = (wsl -u root -- bash -c "dpkg --print-architecture").Trim()
    $codename = (wsl -u root -- bash -c "lsb_release -cs").Trim()
    $repoLine = "deb [arch=$arch signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $codename stable"
    $repoLine | wsl -u root -- bash -c "cat > /etc/apt/sources.list.d/docker.list"
    Write-Host "  Repo: $repoLine"

    # 5. Install Docker
    Write-Host "  Installing Docker CE..."
    Invoke-Wsl "apt-get update -qq && apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin"

    # 6. Start daemon
    Write-Host "  Starting Docker daemon..."
    Invoke-Wsl "service docker start"

    # 7. Add default WSL user to docker group
    $wslUser = wsl -u root -- bash -c "awk -F: '`$3==1000{print `$1}' /etc/passwd"
    if ($wslUser) {
        Invoke-Wsl "usermod -aG docker $wslUser"
    }

    # 8. Auto-start on WSL launch
    Write-Host "  Setting up Docker auto-start..."
    $autostart = @'
if [ "$(service docker status 2>&1 | grep -c 'not running')" -eq 1 ]; then
    service docker start > /dev/null 2>&1
fi
'@
    $marker = "# [lidar-studio] auto-start docker"
    Invoke-WslSafe "grep -q '$marker' /etc/profile.d/docker-autostart.sh 2>/dev/null || printf '$marker\n$autostart\n' > /etc/profile.d/docker-autostart.sh"

    Write-Ok "Docker Engine installed"
    $version = wsl -u root -- bash -c "docker --version"
    Write-Ok $version
}

# ── Deploy compose stack ─────────────────────────────────────
function Deploy-LidarStudio {
    Write-Step "Deploying LiDAR Studio..."

    # Ensure daemon is running
    Invoke-WslSafe "service docker start"

    # Create install dir
    Invoke-Wsl "mkdir -p /opt/lidar-studio"

    # Download compose file
    Write-Host "  Downloading docker-compose.yml from GitHub..."
    Invoke-Wsl "curl -fsSL https://raw.githubusercontent.com/huykuka/lidar-scan/main/docker-compose.yml -o /opt/lidar-studio/docker-compose.yml"

    # Pull image
    Write-Host "  Pulling latest image (this may take a while)..."
    Invoke-Wsl "docker compose -f /opt/lidar-studio/docker-compose.yml pull"

    # Start
    Write-Host "  Starting LiDAR Studio..."
    Invoke-Wsl "docker compose -f /opt/lidar-studio/docker-compose.yml up -d"

    Write-Ok "LiDAR Studio is running"
}

# ── Firewall ─────────────────────────────────────────────────
function Set-FirewallRule {
    Write-Step "Configuring Windows Firewall for port 8005..."
    $ruleName = "LiDAR Studio (8005)"
    if (Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue) {
        Write-Ok "Firewall rule already exists"
    } else {
        New-NetFirewallRule -DisplayName $ruleName -Direction Inbound -Protocol TCP -LocalPort 8005 -Action Allow | Out-Null
        Write-Ok "Firewall rule created for TCP 8005"
    }
}

# ── Port proxy for Windows 10 LAN access ────────────────────
function Set-Win10PortProxy {
    if ($script:IsWin11) { return }
    Write-Step "Setting up port proxy for LAN access (Windows 10)..."
    try {
        $wslIp = (wsl -u root -- hostname -I).Trim().Split(' ')[0]
        if ($wslIp) {
            netsh interface portproxy delete v4tov4 listenport=8005 listenaddress=0.0.0.0 2>$null | Out-Null
            netsh interface portproxy add v4tov4 listenport=8005 listenaddress=0.0.0.0 connectport=8005 connectaddress=$wslIp | Out-Null
            Write-Ok "Port proxy: 0.0.0.0:8005 -> WSL ($wslIp):8005"
            Write-Warn "WSL IP may change after reboot. Re-run script if LAN access stops working."
        }
    } catch {
        Write-Warn "Could not set port proxy. Run manually:"
        Write-Host "  netsh interface portproxy add v4tov4 listenport=8005 listenaddress=0.0.0.0 connectport=8005 connectaddress=<WSL_IP>"
    }
}

# ── Summary ──────────────────────────────────────────────────
function Write-Summary {
    $lanIP = (Get-NetIPAddress -AddressFamily IPv4 |
              Where-Object { $_.InterfaceAlias -notmatch 'Loopback|vEthernet' } |
              Select-Object -First 1).IPAddress

    Write-Host "`n============================================" -ForegroundColor Cyan
    Write-Host "  Installation complete!" -ForegroundColor Green
    Write-Host "============================================" -ForegroundColor Cyan
    Write-Host "  Local : http://localhost:8005"
    Write-Host "  LAN   : http://${lanIP}:8005"
    Write-Host ""
    Write-Host "  Manage (run in WSL or PowerShell):"
    Write-Host "    wsl -u root -- docker logs -f lidar-standalone"
    Write-Host "    wsl -u root -- docker compose -f /opt/lidar-studio/docker-compose.yml down"
    Write-Host "    wsl -u root -- docker compose -f /opt/lidar-studio/docker-compose.yml up -d"
    Write-Host "============================================`n" -ForegroundColor Cyan
}

# ── Main ─────────────────────────────────────────────────────
Assert-Admin
Assert-WindowsVersion

if (-not $SkipWSL)    { Install-WSL }
                        Set-WSLMirroredNetworking
if (-not $SkipDocker) { Install-DockerInWSL }
                        Deploy-LidarStudio
                        Set-FirewallRule
                        Set-Win10PortProxy
                        Write-Summary
