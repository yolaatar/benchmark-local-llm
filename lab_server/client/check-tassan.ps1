<#
.SYNOPSIS
  Through the open tunnel: check which tassan server answers, and that the model makes a real tool call.

.EXAMPLE
  .\check-tassan.ps1                  # vLLM (needs $env:TASSAN_VLLM_KEY)
  .\check-tassan.ps1 -Backend ollama
#>
param(
    [ValidateSet('vllm', 'ollama')]
    [string]$Backend = 'vllm'
)

$ErrorActionPreference = 'Stop'
if ($Backend -eq 'vllm') {
    $base = 'http://127.0.0.1:8001/v1'; $model = 'qwen3-coder-next'; $key = $env:TASSAN_VLLM_KEY
    if (-not $key) { throw 'Set $env:TASSAN_VLLM_KEY first (content of ~/llm-bench/vllm.key on tassan).' }
} else {
    $base = 'http://127.0.0.1:11435/v1'; $model = 'qwen3-coder-next-cc'; $key = 'ollama'
}
$headers = @{ Authorization = "Bearer $key" }

try { $models = Invoke-RestMethod "$base/models" -Headers $headers -TimeoutSec 10 }
catch { throw "No answer from $base. Is the tunnel open and the $Backend server running on tassan? ($($_.Exception.Message))" }
Write-Host "Models: $(($models.data | ForEach-Object { $_.id }) -join ', ')" -ForegroundColor Green

# Tool-calling smoke test: a usable agent model answers with a structured call, not with prose.
$body = @{
    model      = $model
    messages   = @(@{ role = 'user'; content = 'What is in the file stats.py? Use the tool.' })
    tools      = @(@{
        type     = 'function'
        function = @{
            name        = 'read_file'
            description = 'Read a file from the project'
            parameters  = @{ type = 'object'; properties = @{ path = @{ type = 'string' } }; required = @('path') }
        }
    })
    max_tokens = 200
} | ConvertTo-Json -Depth 10
$sw = [Diagnostics.Stopwatch]::StartNew()
$r = Invoke-RestMethod "$base/chat/completions" -Method Post -Headers $headers -ContentType 'application/json' -Body $body -TimeoutSec 600
$call = $r.choices[0].message.tool_calls
if ($call) {
    Write-Host ("Tool call OK in {0:N1} s: {1}({2})" -f $sw.Elapsed.TotalSeconds, $call[0].function.name, $call[0].function.arguments) -ForegroundColor Green
} else {
    Write-Host "No tool call. The model answered: $($r.choices[0].message.content)" -ForegroundColor Yellow
    Write-Host 'On vLLM, check --enable-auto-tool-choice and TOOL_PARSER in vllm.env.'
}
