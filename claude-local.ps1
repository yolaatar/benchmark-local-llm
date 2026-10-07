<#
.SYNOPSIS
  Launch Claude Code on a local Ollama model (Anthropic API served natively by Ollama).

.DESCRIPTION
  Sets ANTHROPIC_BASE_URL and friends only for the lifetime of this Claude Code session,
  then restores the previous values. Plain `claude` in any terminal stays on the normal
  Anthropic backend.

.EXAMPLE
  .\claude-local.ps1                 # qwen3.6 35B MoE, 64k context
  .\claude-local.ps1 -Model 7b       # qwen2.5-coder 7B, 64k context
  .\claude-local.ps1 -Model 14b -- -p "explain this repo"   # extra args go to claude
#>
param(
    [ValidateSet('35b', '14b', '7b')]
    [string]$Model = '35b',
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ClaudeArgs
)

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$ollama = Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe'

$map = @{
    '35b' = 'qwen3.6-35b-cc'
    '14b' = 'qwen2.5-coder-14b-cc'
    '7b'  = 'qwen2.5-coder-7b-cc'
}
$localModel = $map[$Model]

# Create the large-context variant on first use (no download, it reuses the base model's weights)
& $ollama show $localModel *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Creating $localModel from claude_code_local\Modelfile.$localModel ..."
    & $ollama create $localModel -f (Join-Path $here "claude_code_local\Modelfile.$localModel")
    if ($LASTEXITCODE -ne 0) { throw "ollama create $localModel failed" }
}

$vars = [ordered]@{
    ANTHROPIC_BASE_URL                       = 'http://localhost:11434'
    ANTHROPIC_AUTH_TOKEN                     = 'ollama'
    ANTHROPIC_API_KEY                        = ''   # empty = unset in PowerShell
    ANTHROPIC_MODEL                          = $localModel
    ANTHROPIC_DEFAULT_OPUS_MODEL             = $localModel
    ANTHROPIC_DEFAULT_SONNET_MODEL           = $localModel
    ANTHROPIC_DEFAULT_HAIKU_MODEL            = $localModel  # background/small-model calls
    CLAUDE_CODE_SUBAGENT_MODEL               = $localModel
    CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC = '1'
}

$saved = @{}
foreach ($name in $vars.Keys) {
    $saved[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
    [Environment]::SetEnvironmentVariable($name, $(if ($vars[$name]) { $vars[$name] } else { $null }), 'Process')
}

Write-Host "Claude Code -> Ollama ($localModel) at $($vars.ANTHROPIC_BASE_URL)" -ForegroundColor Cyan
try {
    # claude prints a benign warning on stderr (claude.ai connectors disabled with a custom auth token);
    # with 'Stop', Windows PowerShell would turn it into a terminating error and kill the session.
    $ErrorActionPreference = 'Continue'
    & claude --model $localModel @ClaudeArgs
}
finally {
    foreach ($name in $vars.Keys) {
        [Environment]::SetEnvironmentVariable($name, $saved[$name], 'Process')
    }
    Write-Host 'Environment restored: plain `claude` uses the normal Anthropic backend again.' -ForegroundColor Cyan
}
