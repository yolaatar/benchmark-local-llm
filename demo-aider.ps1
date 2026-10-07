<#
.SYNOPSIS
  Open an interactive aider session on one ADS task, with a local model.

.DESCRIPTION
  Does the setup: fresh clone at the task's pinned commit, the right files in the chat,
  ask mode for the explain task, model preloaded in Ollama, prompt copied to the clipboard.
  Then hands the session over to you: paste the prompt and watch.

.EXAMPLE
  .\demo-aider.ps1                          # bug task, 35B  (fastest meaningful demo)
  .\demo-aider.ps1 -Task feature -Model 7b
  .\demo-aider.ps1 -Task explain
#>
param(
    [ValidateSet('feature', 'test', 'explain', 'bug', 'refactor')]
    [string]$Task = 'bug',
    [ValidateSet('7b', '14b', '35b')]
    [string]$Model = '35b',
    [string]$Label = 'demo'
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$py = Join-Path $root '.venv\Scripts\python.exe'
$aider = Join-Path $root '.venv\Scripts\aider.exe'

$taskIds = @{
    feature = 'task_01_add_feature'; test = 'task_02_write_test'; explain = 'task_03_explain_module'
    bug = 'task_04_find_bug'; refactor = 'task_05_refactor'
}
$models = @{
    '7b' = 'qwen2.5-coder:7b'; '14b' = 'qwen2.5-coder:14b'; '35b' = 'qwen3.6:35b-a3b-coding'
}
$taskId = $taskIds[$Task]
$tag = $models[$Model]

Write-Host "`nPreparing $taskId with $tag ..." -ForegroundColor Cyan
& $py (Join-Path $root 'run_custom_tasks.py') --prepare-manual $Label --tasks $taskId | Out-Null

# task spec: files to put in the chat, and whether it is a read-only (ask) task
$spec = & $py -c @"
import sys, yaml, json
spec = yaml.safe_load(open(r'$root\custom_tasks\$taskId\task.yaml', encoding='utf-8'))
print(json.dumps({'files': spec.get('files') or [], 'mode': spec['mode'],
                  'ctx': 65536 if 'qwen3.6' in '$tag' else 32768}))
"@ | ConvertFrom-Json

# preload the model so the first answer is not slowed down by the load
Write-Host "Loading $tag into Ollama (num_ctx $($spec.ctx)) ..." -ForegroundColor Cyan
$body = @{ model = $tag; prompt = ''; keep_alive = '30m'; options = @{ num_ctx = $spec.ctx } } | ConvertTo-Json
Invoke-RestMethod http://127.0.0.1:11434/api/generate -Method Post -Body $body -ContentType 'application/json' | Out-Null
$ps = (Invoke-RestMethod http://127.0.0.1:11434/api/ps).models | Where-Object name -eq $tag
Write-Host ("   {0:N1} of {1:N1} GB on the GPU" -f ($ps.size_vram / 1e9), ($ps.size / 1e9))

$repo = Join-Path $root "work\$taskId\$Label\repo"
$prompt = Get-Content (Join-Path $root "work\$taskId\$Label\prompt.md") -Raw
try { Set-Clipboard -Value $prompt; $clip = ' (already copied to your clipboard)' } catch { $clip = '' }

Write-Host "`n---------------- the task$clip ----------------" -ForegroundColor Yellow
Write-Host $prompt
Write-Host "-----------------------------------------------`n" -ForegroundColor Yellow
Write-Host "Files in the chat: $($spec.files -join ', ')" -ForegroundColor DarkGray
Write-Host "Paste the task at the aider prompt. /diff to see the changes, /exit to quit.`n" -ForegroundColor DarkGray

$env:OLLAMA_API_BASE = 'http://127.0.0.1:11434'
$aiderArgs = @(
    '--model', "ollama_chat/$tag",
    '--model-settings-file', (Join-Path $root 'aider_model_settings_custom.yml'),
    '--chat-language', 'English',
    '--no-auto-commits', '--no-dirty-commits', '--no-gitignore',
    '--no-suggest-shell-commands', '--no-analytics', '--no-check-update'
)
if ($spec.mode -eq 'ask') { $aiderArgs += @('--chat-mode', 'ask') }
$aiderArgs += $spec.files

Push-Location $repo
try { & $aider @aiderArgs } finally { Pop-Location }
