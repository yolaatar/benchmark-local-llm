<#
.SYNOPSIS
  Run the whole local benchmark: VRAM check, aider polyglot subset, custom tasks.

.EXAMPLE
  .\run_all.ps1                         # everything, all 3 models
  .\run_all.ps1 -Resume                 # continue an interrupted polyglot run
  .\run_all.ps1 -Models qwen2.5-coder:7b -SkipCustom
#>
param(
    [string[]]$Models,
    [switch]$Resume,
    [switch]$SkipVram,
    [switch]$SkipBenchmark,
    [switch]$SkipCustom
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root
$py = Join-Path $root '.venv\Scripts\python.exe'
$stamp = Get-Date -Format 'yyyy-MM-dd_HH-mm-ss'
New-Item -ItemType Directory -Force (Join-Path $root 'results\logs') | Out-Null
Start-Transcript -Path (Join-Path $root "results\logs\run_all_$stamp.txt") | Out-Null

try {
    try {
        $v = Invoke-RestMethod http://127.0.0.1:11434/api/version -TimeoutSec 5
        Write-Host "Ollama $($v.version) is up"
    }
    catch {
        throw 'Ollama is not running. Start the Ollama app (or `ollama serve`) and retry.'
    }

    $os = Get-CimInstance Win32_OperatingSystem
    $freeGb = [math]::Round($os.FreePhysicalMemory / 1MB, 1)
    Write-Host "Free RAM: $freeGb GB"
    if ($freeGb -lt 10) {
        Write-Warning 'Less than 10 GB of free RAM: the 35B MoE offloads ~9 GB to RAM. Close games/browsers for stable timings.'
    }

    $modelArgs = @()
    if ($Models) { $modelArgs = @('--models') + $Models }

    if (-not $SkipVram) {
        Write-Host "`n##### 1/3 VRAM and throughput" -ForegroundColor Cyan
        $vramArgs = @('--num-ctx', '16384')
        if ($Models) { $vramArgs += $Models }
        & $py measure_vram.py @vramArgs
        if ($LASTEXITCODE -ne 0) { throw 'measure_vram.py failed' }
    }

    if (-not $SkipBenchmark) {
        Write-Host "`n##### 2/3 Aider polyglot benchmark (Python subset)" -ForegroundColor Cyan
        $benchArgs = $modelArgs
        if ($Resume) { $benchArgs += '--resume' }
        & $py run_aider_benchmark.py @benchArgs
        if ($LASTEXITCODE -ne 0) { throw 'run_aider_benchmark.py failed' }
    }

    if (-not $SkipCustom) {
        Write-Host "`n##### 3/3 Custom tasks" -ForegroundColor Cyan
        & $py run_custom_tasks.py @modelArgs
        if ($LASTEXITCODE -ne 0) { throw 'run_custom_tasks.py failed' }
    }

    Write-Host "`nDone. Results in $root\results" -ForegroundColor Green
}
finally {
    Stop-Transcript | Out-Null
}
