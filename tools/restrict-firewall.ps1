param(
    [Parameter(Mandatory = $true)]
    [string]$PlatformIP,

    [switch]$KeepLanSubnet
)

$ErrorActionPreference = 'Stop'
$ruleName = 'Ollama LLM (RCC AI Gateway)'
$lanSubnet = '10.5.14.0/23'

function Test-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    (New-Object Security.Principal.WindowsPrincipal($identity)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-Administrator)) {
    Write-Host 'Butuh hak admin - meminta elevasi (UAC)...'
    $args = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $PSCommandPath, '-PlatformIP', $PlatformIP)
    if ($KeepLanSubnet) { $args += '-KeepLanSubnet' }
    Start-Process -FilePath 'powershell.exe' -ArgumentList $args -Verb RunAs -Wait
    exit 0
}

$remote = @($PlatformIP)
if ($KeepLanSubnet) { $remote += $lanSubnet }

try {
    netsh advfirewall firewall set rule name="$ruleName" new remoteip=($remote -join ',') | Out-Null
} catch {
    Write-Host "GAGAL: $($_.Exception.Message)"
    exit 1
}

$rule = Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue
if ($null -eq $rule) {
    Write-Host "Rule '$ruleName' tidak ditemukan - buat dulu rule dasarnya."
    exit 2
}

$addressFilter = Get-NetFirewallAddressFilter -AssociatedNetFirewallRule $rule
Write-Host "Rule '$ruleName' diperbarui:"
Write-Host "  Enabled      : $($rule.Enabled)"
Write-Host "  Action       : $($rule.Action)"
Write-Host "  Protocol/Port: TCP 11434"
Write-Host "  RemoteIP     : $($addressFilter.RemoteAddress -join ', ')"
if ($KeepLanSubnet) {
    Write-Host 'CATATAN: subnet LAN tetap diizinkan. Jalankan ulang TANPA -KeepLanSubnet untuk mengunci hanya IP platform.'
}
exit 0
