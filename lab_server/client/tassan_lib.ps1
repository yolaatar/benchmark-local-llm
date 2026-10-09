# Shared by the Windows client scripts (claude-tassan.ps1, opencode-tassan.ps1, check-tassan.ps1).
# Dot-source it after setting $Backend: sets $base, $token, $model and $window, through the ports of
# tassan-tunnel.ps1.
#   key:   $env:TASSAN_VLLM_KEY, else the file ~\.tassan_vllm_key
#   model: $env:TASSAN_MODEL, else whatever the server serves (a model change on tassan needs no client change)

if ($Backend -eq 'ollama') {
    $base = 'http://127.0.0.1:11435'; $token = 'ollama'; $window = 65536
} else {
    $base = 'http://127.0.0.1:8001'; $window = 131072   # = MAX_MODEL_LEN in lab_server/cluster/vllm.env
    $keyFile = Join-Path $HOME '.tassan_vllm_key'
    $token = if ($env:TASSAN_VLLM_KEY) { $env:TASSAN_VLLM_KEY } elseif (Test-Path $keyFile) { (Get-Content $keyFile -Raw).Trim() }
    if (-not $token) { throw "No lab key: save it once with  Set-Content -NoNewline $keyFile '<key>'" }
}
try { $served = Invoke-RestMethod "$base/v1/models" -Headers @{ Authorization = "Bearer $token" } -TimeoutSec 10 }
catch { throw "No answer on $base. Is tassan-tunnel.ps1 running (and the VPN on)? Is the server up on tassan? ($($_.Exception.Message))" }
$model = if ($env:TASSAN_MODEL) { $env:TASSAN_MODEL } else { $served.data[0].id }
