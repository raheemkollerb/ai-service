param(
    # IP server platform (BFF Express). Opsional pada mode -HpcGateway tahap 1
    # (belum tahu IP platform): rule 8100 sementara terbuka untuk subnet LAN.
    [string]$PlatformIP,

    # Pertahankan subnet LAN selain IP platform (mode transisi).
    [switch]$KeepLanSubnet,

    # Mode B (gateway Docker di HPC): atur 2 port sekaligus -
    #   11434 (Ollama)  -> dikunci ke subnet NAT Docker/WSL (tidak terlihat LAN)
    #   8100  (gateway) -> buat/perketat rule "RCC AI Gateway (:8100)"
    #                      ke IP platform + (opsional) subnet LAN.
    [switch]$HpcGateway,

    # Mode platform (dijalankan DI server platform): izinkan inbound TCP 8000
    # (analytics) HANYA dari IP HPC (+ IP tambahan opsional, mis. subnet admin)
    # — spec tahap-2-analytics-tools.md § 6.1.
    [switch]$AnalyticsPlatform,

    # IP HPC untuk mode -AnalyticsPlatform (contoh 10.5.15.60).
    [string]$HpcIP,

    # CSV IP tambahan untuk mode -AnalyticsPlatform (subnet admin, dsb).
    [string]$AlsoAllow
)

$ErrorActionPreference = 'Stop'
$ollamaRuleName = 'Ollama LLM (RCC AI Gateway)'
$gatewayRuleName = 'RCC AI Gateway (:8100)'
$lanSubnet = '10.5.14.0/23'

function Test-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    (New-Object Security.Principal.WindowsPrincipal($identity)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-Administrator)) {
    Write-Host 'Butuh hak admin - meminta elevasi (UAC)...'
    $args = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $PSCommandPath)
    if ($PlatformIP) { $args += @('-PlatformIP', $PlatformIP) }
    if ($KeepLanSubnet) { $args += '-KeepLanSubnet' }
    if ($HpcGateway) { $args += '-HpcGateway' }
    if ($AnalyticsPlatform) { $args += '-AnalyticsPlatform' }
    if ($HpcIP) { $args += @('-HpcIP', $HpcIP) }
    if ($AlsoAllow) { $args += @('-AlsoAllow', $AlsoAllow) }
    Start-Process -FilePath 'powershell.exe' -ArgumentList $args -Verb RunAs -Wait
    exit 0
}

# --- Subnet NAT Docker/WSL (untuk Mode B: kunci 11434) ---
function Get-DockerNatSubnets {
    $ips = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object {
            $_.InterfaceAlias -like '*WSL*' -or
            $_.InterfaceAlias -like '*Docker*'
        }
    @($ips | ForEach-Object { "$($_.IPAddress)/$($_.PrefixLength)" } | Sort-Object -Unique)
}

# --- Susun daftar remoteip umum ---
function Build-RemoteList([string]$Ip, [bool]$KeepLan) {
    $remote = @()
    if ($Ip) { $remote += $Ip }
    if ($KeepLan) { $remote += $lanSubnet }
    return $remote
}

function Set-FirewallRule {
    param(
        [string]$Name,
        [string[]]$RemoteIps,
        [int]$LocalPort
    )
    $existing = Get-NetFirewallRule -DisplayName $Name -ErrorAction SilentlyContinue
    if ($null -eq $existing) {
        New-NetFirewallRule -DisplayName $Name `
            -Direction Inbound -Action Allow -Protocol TCP `
            -LocalPort $LocalPort -RemoteAddress $RemoteIps | Out-Null
        Write-Host "Rule '$Name' dibuat baru (TCP $LocalPort)."
    }
    else {
        Set-NetFirewallRule -DisplayName $Name -Enabled True
        Set-NetFirewallAddressFilter -InputObject $existing -RemoteAddress $RemoteIps
        Write-Host "Rule '$Name' diperbarui."
    }

    $rule = Get-NetFirewallRule -DisplayName $Name
    if ($null -eq $rule) { return }
    $filter = Get-NetFirewallAddressFilter -AssociatedNetFirewallRule $rule
    Write-Host "  Protocol/Port: TCP $LocalPort"
    Write-Host "  RemoteIP     : $($filter.RemoteAddress -join ', ')"
}

if ($HpcGateway) {
    Write-Host '=== Mode B - firewall gateway HPC (8100) + kunci Ollama (11434) ==='

    # 1/2) Ollama 11434 -> hanya subnet NAT Docker/WSL
    $natSubnets = Get-DockerNatSubnets
    if ($natSubnets.Count -eq 0) {
        Write-Warning 'Subnet NAT Docker/WSL tidak terdeteksi (Docker belum jalan?). Rule 11434 TIDAK diubah.'
    }
    else {
        Write-Host "Subnet NAT Docker/WSL terdeteksi: $($natSubnets -join ', ')"
        Set-FirewallRule -Name $ollamaRuleName -RemoteIps $natSubnets -LocalPort 11434
        Write-Host 'CATATAN: Ollama kini hanya dapat dijangkau dari container Docker (gateway).'
        Write-Host 'Bila subnet NAT berubah (pasca restart/upgrade WSL), jalankan ulang script ini.'
    }

    # 2/2) Gateway 8100 -> IP platform (+ subnet LAN transisi) atau LAN (tahap 1)
    $remote = Build-RemoteList $PlatformIP ([bool]$KeepLanSubnet)
    if ($remote.Count -eq 0) {
        $remote = @($lanSubnet)
        Write-Host "PlatformIP belum diisi - tahap 1: 8100 sementara terbuka untuk $lanSubnet."
    }
    Set-FirewallRule -Name $gatewayRuleName -RemoteIps $remote -LocalPort 8100
    if ($KeepLanSubnet) {
        Write-Host 'CATATAN: subnet LAN tetap diizinkan. Jalankan ulang dengan -PlatformIP TANPA -KeepLanSubnet untuk produksi.'
    }
    elseif ($PlatformIP) {
        Write-Host 'CATATAN tahap 2: 8100 terkunci hanya untuk IP platform.'
    }
    exit 0
}

if ($AnalyticsPlatform) {
    if (-not $HpcIP) {
        Write-Host 'Perlu -HpcIP <IP-HPC> (contoh: -HpcIP 10.5.15.60).'
        exit 1
    }
    Write-Host '=== Mode platform - analytics :8000 hanya dari IP HPC ==='
    $remote = @($HpcIP)
    if ($AlsoAllow) {
        $extra = $AlsoAllow.Split(',') | ForEach-Object { $_.Trim() } | Where-Object { $_ }
        $remote += $extra
    }
    Set-FirewallRule -Name 'RCC Analytics (:8000) dari HPC' -RemoteIps $remote -LocalPort 8000
    Write-Host 'CATATAN: port 8000 sudah dipublikasikan compose (8000:8000); rule ini mempersempit sumber.'
    Write-Host 'Mesin LAN lain tidak boleh menembus langsung (spec tahap-2-analytics-tools.md § 6.1).'
    Write-Host 'CATATAN: IP HPC via DHCP - bila berubah, jalankan ulang dengan -HpcIP IP-baru.'
    exit 0
}

# --- Mode lama (Mode A): hanya atur rule Ollama 11434 ---
if (-not $PlatformIP) {
    Write-Host 'Perlu -PlatformIP (atau pakai -HpcGateway untuk Mode B).'
    exit 1
}

$remote = Build-RemoteList $PlatformIP ([bool]$KeepLanSubnet)
try {
    Set-FirewallRule -Name $ollamaRuleName -RemoteIps $remote -LocalPort 11434
} catch {
    Write-Host "GAGAL: $($_.Exception.Message)"
    exit 1
}
if ($KeepLanSubnet) {
    Write-Host 'CATATAN: subnet LAN tetap diizinkan. Jalankan ulang TANPA -KeepLanSubnet untuk mengunci hanya IP platform.'
}
exit 0
