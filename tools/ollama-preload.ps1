$ErrorActionPreference = 'Continue'
$logPath = Join-Path $env:LOCALAPPDATA 'Ollama\preload.log'
$deadline = (Get-Date).AddSeconds(60)
$ready = $false

while ((Get-Date) -lt $deadline) {
    $version = curl.exe -s --noproxy '*' -m 5 http://127.0.0.1:11434/api/version
    if ($LASTEXITCODE -eq 0 -and $version) {
        $ready = $true
        break
    }
    Start-Sleep -Seconds 5
}

$stamp = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
if (-not $ready) {
    "$stamp  SKIP: Ollama tidak up dalam 60 detik" | Add-Content -Path $logPath
    exit 1
}

$bodyPath = Join-Path $env:TEMP 'rcc-ollama-preload.json'
'{"model":"qwen3:30b-a3b","prompt":"warm","stream":false,"keep_alive":-1,"num_predict":1}' |
    Set-Content -Path $bodyPath -Encoding ASCII -NoNewline

$started = Get-Date
$response = curl.exe -s --noproxy '*' -m 600 -X POST http://127.0.0.1:11434/api/generate -H 'Content-Type: application/json' --data-binary "@$bodyPath"
$elapsed = [Math]::Round(((Get-Date) - $started).TotalSeconds, 1)
$ok = $false
try {
    $payload = $response | ConvertFrom-Json
    $ok = ($payload.done -eq $true)
} catch {
}

$verdict = if ($ok) { 'OK' } else { 'GAGAL' }
"$stamp  $verdict : preload qwen3:30b-a3b selesai dalam $elapsed dtk" | Add-Content -Path $logPath
if (-not $ok) {
    "$stamp  detail: $response" | Add-Content -Path $logPath
    exit 2
}
exit 0
