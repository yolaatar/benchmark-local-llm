<#
.SYNOPSIS
  Launch Claude Code on the lab model served by tassan (through tassan-tunnel.ps1).

.DESCRIPTION
  Same idea as ..\..\claude-local.ps1: the variables only live for this Claude Code session,
  plain `claude` stays on the normal Anthropic backend. vLLM and Ollama both speak the Anthropic API.

.EXAMPLE
  .\claude-tassan.ps1                       # vLLM, needs $env:TASSAN_VLLM_KEY
  .\claude-tassan.ps1 -Backend ollama
  .\claude-tassan.ps1 -- -p "explain this repo"   # put -- before any dash option meant for claude
#>
[CmdletBinding(PositionalBinding = $false)]
param(
    [ValidateSet('vllm', 'ollama')]
    [string]$Backend = 'vllm',
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ClaudeArgs
)

$ErrorActionPreference = 'Stop'
if ($Backend -eq 'vllm') {
    if (-not $env:TASSAN_VLLM_KEY) { throw 'Set $env:TASSAN_VLLM_KEY first (content of ~/llm-bench/vllm.key on tassan).' }
    $base = 'http://127.0.0.1:8001'; $token = $env:TASSAN_VLLM_KEY; $model = 'qwen3-coder-next'
} else {
    $base = 'http://127.0.0.1:11435'; $token = 'ollama'; $model = 'qwen3-coder-next-cc'
}

$vars = [ordered]@{
    ANTHROPIC_BASE_URL                       = $base
    ANTHROPIC_AUTH_TOKEN                     = $token
    ANTHROPIC_API_KEY                        = ''   # empty = unset in PowerShell
    ANTHROPIC_MODEL                          = $model
    ANTHROPIC_DEFAULT_OPUS_MODEL             = $model
    ANTHROPIC_DEFAULT_SONNET_MODEL           = $model
    ANTHROPIC_DEFAULT_HAIKU_MODEL            = $model  # background/small-model calls
    CLAUDE_CODE_SUBAGENT_MODEL               = $model
    CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC = '1'
    CLAUDE_CODE_ATTRIBUTION_HEADER           = '0'     # keeps vLLM prefix caching effective
}

$saved = @{}
foreach ($name in $vars.Keys) {
    $saved[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
    [Environment]::SetEnvironmentVariable($name, $(if ($vars[$name]) { $vars[$name] } else { $null }), 'Process')
}

Write-Host "Claude Code -> tassan $Backend ($model) at $base" -ForegroundColor Cyan
try {
    # claude prints a benign stderr warning with a custom auth token; with 'Stop' it would be fatal.
    $ErrorActionPreference = 'Continue'
    & claude --model $model @ClaudeArgs
}
finally {
    foreach ($name in $vars.Keys) {
        [Environment]::SetEnvironmentVariable($name, $saved[$name], 'Process')
    }
    Write-Host 'Environment restored: plain `claude` uses the normal Anthropic backend again.' -ForegroundColor Cyan
}
