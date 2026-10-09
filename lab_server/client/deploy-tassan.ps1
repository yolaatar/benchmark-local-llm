<#
.SYNOPSIS
  Copy the cluster scripts and the load-test tool to tassan, or fetch the results back.

.DESCRIPTION
  Push: lab_server\cluster\* -> tassan:~/llm-bench/lab_server/, concurrency_bench.py -> ~/llm-bench/.
  Line endings are forced to LF on the way (a CRLF bash script fails with "$'\r': command not found").
  Fetch: ~/llm-bench/results/conc_*.json -> ..\..\results\ on this laptop.
  Two SSH connections per call: set up an SSH key to avoid typing the password twice.

.EXAMPLE
  .\deploy-tassan.ps1 -User "you@ge.polymtl.ca"
  .\deploy-tassan.ps1 -Fetch
#>
param(
    [string]$User = $env:TASSAN_USER,
    [string]$HostName = 'tassan.neuro.polymtl.ca',
    [switch]$Fetch
)

$ErrorActionPreference = 'Stop'
if (-not $User) { throw 'Give your tassan login: -User "you@ge.polymtl.ca" (or set $env:TASSAN_USER)' }
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = (Resolve-Path (Join-Path $here '..\..')).Path
$ssh = @('-o', "User=$User")

if ($Fetch) {
    $dest = Join-Path $root 'results'
    & scp @ssh "${HostName}:llm-bench/results/conc_*.json" $dest
    if ($LASTEXITCODE) { throw 'scp failed (no results yet?)' }
    Get-ChildItem $dest -Filter 'conc_*.json' | Format-Table Name, Length, LastWriteTime
    return
}

$stage = Join-Path ([IO.Path]::GetTempPath()) "tassan-deploy-$PID"
New-Item -ItemType Directory -Force $stage | Out-Null
try {
    $files = @(Get-ChildItem (Join-Path $here '..\cluster') -File) + @(Get-Item (Join-Path $root 'concurrency_bench.py'))
    foreach ($f in $files) {
        $text = [IO.File]::ReadAllText($f.FullName) -replace "`r`n", "`n"
        [IO.File]::WriteAllText((Join-Path $stage $f.Name), $text, (New-Object Text.UTF8Encoding $false))
    }
    & ssh @ssh $HostName 'mkdir -p llm-bench/lab_server llm-bench/results llm-bench/logs'
    if ($LASTEXITCODE) { throw "ssh to $HostName failed (VPN on? login right?)" }
    $cluster = Get-ChildItem $stage -File | Where-Object Name -ne 'concurrency_bench.py' | ForEach-Object FullName
    & scp @ssh @cluster "${HostName}:llm-bench/lab_server/"
    if ($LASTEXITCODE) { throw 'scp of the cluster scripts failed' }
    & scp @ssh (Join-Path $stage 'concurrency_bench.py') "${HostName}:llm-bench/"
    if ($LASTEXITCODE) { throw 'scp of concurrency_bench.py failed' }
    Write-Host "Copied $($files.Count) files. On tassan: cd ~/llm-bench/lab_server && bash preflight.sh" -ForegroundColor Green
}
finally {
    Remove-Item -Recurse -Force $stage
}
