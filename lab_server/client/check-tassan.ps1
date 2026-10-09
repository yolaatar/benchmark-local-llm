<#
.SYNOPSIS
  Through the open tunnel: check which tassan server answers, and that the model makes a real tool call.

.EXAMPLE
  .\check-tassan.ps1                  # vLLM (key in ~\.tassan_vllm_key or $env:TASSAN_VLLM_KEY)
  .\check-tassan.ps1 -Backend ollama
#>
param(
    [ValidateSet('vllm', 'ollama')]
    [string]$Backend = 'vllm'
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'tassan_lib.ps1')
$headers = @{ Authorization = "Bearer $token" }
Write-Host "Server answers, model: $model" -ForegroundColor Green

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
    max_tokens = 2000   # room for a thinking model to reason before the call
} | ConvertTo-Json -Depth 10
$sw = [Diagnostics.Stopwatch]::StartNew()
$r = Invoke-RestMethod "$base/v1/chat/completions" -Method Post -Headers $headers -ContentType 'application/json' -Body $body -TimeoutSec 600
$call = $r.choices[0].message.tool_calls
if ($call) {
    Write-Host ("Tool call OK in {0:N1} s: {1}({2})" -f $sw.Elapsed.TotalSeconds, $call[0].function.name, $call[0].function.arguments) -ForegroundColor Green
} else {
    Write-Host "No tool call. The model answered: $($r.choices[0].message.content)" -ForegroundColor Yellow
    Write-Host 'On vLLM, check --enable-auto-tool-choice and TOOL_PARSER in vllm.env.'
}
