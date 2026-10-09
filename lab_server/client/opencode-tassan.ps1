<#
.SYNOPSIS
  Start OpenCode in the current folder, on the lab model served by tassan (through tassan-tunnel.ps1).

.DESCRIPTION
  Uses lab_server\client\opencode.json: session sharing disabled, only the tassan providers enabled.
  OPENCODE_CONFIG is set only for this session; your other OpenCode settings are untouched.

.EXAMPLE
  cd C:\path\to\repo; & "<...>\opencode-tassan.ps1"              # vLLM
  & "<...>\opencode-tassan.ps1" -Backend ollama                   # Ollama server instead
  & "<...>\opencode-tassan.ps1" run "explain this repo"           # extra args go to opencode
  & "<...>\opencode-tassan.ps1" -- --continue                     # put -- before any dash option
#>
[CmdletBinding(PositionalBinding = $false)]
param(
    [ValidateSet('vllm', 'ollama')]
    [string]$Backend = 'vllm',
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$OpenCodeArgs
)

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not (Get-Command opencode -ErrorAction SilentlyContinue)) { throw 'OpenCode is not installed: npm install -g opencode-ai' }
. (Join-Path $here 'tassan_lib.ps1')
$provider = if ($Backend -eq 'vllm') { 'tassan' } else { 'tassan-ollama' }
if (-not (Select-String -Quiet -SimpleMatch "`"$model`"" (Join-Path $here 'opencode.json'))) {
    Write-Warning "$model is not listed in opencode.json, add it there (copy an existing model entry)."
}
$model = "$provider/$model"
$env:TASSAN_VLLM_KEY = $token   # opencode.json reads it

$saved = $env:OPENCODE_CONFIG
$env:OPENCODE_CONFIG = Join-Path $here 'opencode.json'
try {
    & opencode @OpenCodeArgs --model $model
}
finally {
    $env:OPENCODE_CONFIG = $saved
}
