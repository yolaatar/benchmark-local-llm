<#
.SYNOPSIS
  Open an SSH tunnel from this laptop to the lab LLM servers on tassan. Leave this window open.

.DESCRIPTION
  Forwards (bound to 127.0.0.1 on both sides, nothing exposed on the network):
    127.0.0.1:8001   -> tassan vLLM   127.0.0.1:8000
    127.0.0.1:11435  -> tassan Ollama 127.0.0.1:11434   (11435 so a local Ollama on 11434 keeps working)
  Needs the Polytechnique VPN and your own tassan login.

.EXAMPLE
  .\tassan-tunnel.ps1 -User "you@ge.polymtl.ca"
  $env:TASSAN_USER = "you@ge.polymtl.ca"; .\tassan-tunnel.ps1
#>
param(
    [string]$User = $env:TASSAN_USER,
    [string]$HostName = 'tassan.neuro.polymtl.ca',
    [int]$VllmPort = 8001,
    [int]$OllamaPort = 11435
)

$ErrorActionPreference = 'Stop'
if (-not $User) { throw 'Give your tassan login: -User "you@ge.polymtl.ca" (or set $env:TASSAN_USER)' }

try { [void][Net.Dns]::GetHostAddresses($HostName) }
catch { throw "Cannot resolve $HostName. Is the Polytechnique VPN connected?" }

foreach ($p in $VllmPort, $OllamaPort) {
    if (Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue) {
        throw "Port $p is already in use on this laptop (another tunnel still open?)."
    }
}

Write-Host "Tunnel to $HostName as $User" -ForegroundColor Cyan
Write-Host "  vLLM   -> http://127.0.0.1:$VllmPort/v1"
Write-Host "  Ollama -> http://127.0.0.1:$OllamaPort"
Write-Host 'Leave this window open. Ctrl+C closes the tunnel.' -ForegroundColor Cyan
$sshArgs = @(
    '-N',
    '-o', 'ExitOnForwardFailure=yes',
    '-o', 'ServerAliveInterval=30',
    '-o', 'ServerAliveCountMax=3',
    '-L', "${VllmPort}:127.0.0.1:8000",
    '-L', "${OllamaPort}:127.0.0.1:11434",
    '-l', $User,
    $HostName
)
& ssh @sshArgs
