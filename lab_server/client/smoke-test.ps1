<#
.SYNOPSIS
  Checkpoints 1 and 2 of PLAN.md in one go: server check, then one real edit by each agent, then a
  test of the edited code.

.DESCRIPTION
  Through the open tunnel. Creates a scratch git repo with stats.py (mean only), asks OpenCode to add
  median() and Claude Code to add variance(), then imports the result and checks both functions.
  The agents run with edits auto-accepted, in the scratch repo only (opencode.bench.json, acceptEdits).

.EXAMPLE
  .\smoke-test.ps1 -Backend ollama      # Phase 1
  .\smoke-test.ps1                      # Phase 2, vLLM (needs $env:TASSAN_VLLM_KEY)
  .\smoke-test.ps1 -Only opencode
#>
param(
    [ValidateSet('vllm', 'ollama')]
    [string]$Backend = 'vllm',
    [ValidateSet('both', 'opencode', 'claude')]
    [string]$Only = 'both'
)

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = (Resolve-Path (Join-Path $here '..\..')).Path
$python = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) { $python = 'python' }

& (Join-Path $here 'check-tassan.ps1') -Backend $Backend

$repo = Join-Path ([IO.Path]::GetTempPath()) ("tassan-smoke-{0:yyyyMMdd-HHmmss}" -f (Get-Date))
New-Item -ItemType Directory $repo | Out-Null
Push-Location $repo
$results = [ordered]@{}
try {
    git init -q
    [IO.File]::WriteAllText("$repo\stats.py", "def mean(values):`n    return sum(values) / len(values)`n")
    git add stats.py; git -c user.name=smoke -c user.email=smoke@local commit -qm init

    if ($Only -in 'both', 'opencode') {
        $model = if ($Backend -eq 'vllm') { 'tassan/qwen3-coder-next' } else { 'tassan-ollama/qwen3-coder-next-cc' }
        $saved = $env:OPENCODE_CONFIG
        $env:OPENCODE_CONFIG = Join-Path $here 'opencode.bench.json'
        Write-Host "`n== OpenCode ($model): add median" -ForegroundColor Cyan
        $sw = [Diagnostics.Stopwatch]::StartNew()
        try { & opencode run 'Read stats.py, then add a median(values) function to it.' --model $model }
        finally { $env:OPENCODE_CONFIG = $saved }
        $results['opencode'] = $sw.Elapsed.TotalSeconds
    }
    if ($Only -in 'both', 'claude') {
        Write-Host "`n== Claude Code: add variance" -ForegroundColor Cyan
        $sw = [Diagnostics.Stopwatch]::StartNew()
        & (Join-Path $here 'claude-tassan.ps1') -Backend $Backend -- -p 'Add a variance(values) function to stats.py.' --permission-mode acceptEdits
        $results['claude'] = $sw.Elapsed.TotalSeconds
    }

    Write-Host "`n== stats.py after the agents" -ForegroundColor Cyan
    Get-Content stats.py
    # population or sample variance are both accepted
    $check = @'
import importlib, sys
sys.path.insert(0, ".")
s = importlib.import_module("stats")
ok = True
if "median" in sys.argv:
    m = getattr(s, "median", None)
    good = m is not None and m([3, 1, 2]) == 2 and m([4, 1, 3, 2]) == 2.5
    print("median  ", "PASS" if good else "FAIL"); ok &= good
if "variance" in sys.argv:
    v = getattr(s, "variance", None)
    good = v is not None and any(abs(v([1, 2, 3, 4]) - x) < 1e-9 for x in (1.25, 5 / 3))
    print("variance", "PASS" if good else "FAIL"); ok &= good
sys.exit(0 if ok else 1)
'@
    $want = @()
    if ($results.Contains('opencode')) { $want += 'median' }
    if ($results.Contains('claude')) { $want += 'variance' }
    # through a file: PowerShell 5.1 mangles quotes in arguments passed to native programs
    $checkFile = Join-Path ([IO.Path]::GetTempPath()) "tassan-smoke-check-$PID.py"
    [IO.File]::WriteAllText($checkFile, $check)
    & $python $checkFile @want
    Remove-Item $checkFile
    $passed = ($LASTEXITCODE -eq 0)
    foreach ($k in $results.Keys) { Write-Host ("{0,-9} {1,6:N0} s" -f $k, $results[$k]) }
    Write-Host ("Checkpoint {0} ({1}): {2}" -f $(if ($Backend -eq 'ollama') { 1 } else { 2 }), $Backend, $(if ($passed) { 'PASSED' } else { 'FAILED' })) `
        -ForegroundColor $(if ($passed) { 'Green' } else { 'Red' })
    Write-Host "Scratch repo kept for inspection: $repo"
}
finally {
    Pop-Location
}
