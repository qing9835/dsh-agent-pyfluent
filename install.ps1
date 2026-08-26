# install.ps1 - install the fluent-cfd DSH agent preset (Windows / PowerShell).
#
# Usage (from the repo checkout):
#   .\install.ps1 [-Target <presets\fluent-cfd>] [-Python <python.exe>] [-AnsysRoot <ANSYS dir>] [-Force]
#
# Auto-detection (override with env vars or the -Python / -AnsysRoot params):
#   PYTHON                         -> python interpreter (else `where python`, else `py`)
#   PYTHON_ANSYS_FLUENT_MCP        -> full path to ansys-fluent-mcp.exe (else python's ..\Scripts)
#   ANSYS_AWP_ROOT                 -> Ansys install dir, e.g. C:\Program Files\ANSYS Inc\v252
#
# It copies the preset into $HOME\.dsh\.agent-presets\fluent-cfd and fills the two
# machine-specific tokens (__PYTHON_ANSYS_FLUENT_MCP__ / __ANSYS_AWP_ROOT__) in
# agent.cordis.yml. Idempotent: backs up an existing install unless -Force.
param(
  [string]$Target = "$HOME\.dsh\.agent-presets\fluent-cfd",
  [string]$Python = "",
  [string]$AnsysRoot = "",
  [switch]$Force
)

$ErrorActionPreference = 'Stop'
$Bundle = Split-Path -Parent $MyInvocation.MyCommand.Path   # repo root containing fluent-cfd/
$Src    = Join-Path $Bundle 'fluent-cfd'
if (-not (Test-Path (Join-Path $Src 'agent.cordis.yml'))) { Write-Error "Bundle not found: $Src"; exit 1 }

Write-Host "== fluent-cfd DSH agent preset installer ==" -ForegroundColor Cyan

# --- locate python ---
if (-not $Python) { $Python = $env:PYTHON }
if (-not $Python) { $Python = (Get-Command python -ErrorAction SilentlyContinue).Source }
if (-not $Python) { $Python = (Get-Command py -ErrorAction SilentlyContinue).Source }
if (-not $Python) { Write-Error "Python not found. Set env PYTHON or pass -Python."; exit 1 }
Write-Host "python : $Python"

# --- locate ansys-fluent-mcp.exe ---
$mcpExe = $env:PYTHON_ANSYS_FLUENT_MCP
if (-not $mcpExe -and $Python -match '\.exe$') {
  $scripts = Join-Path (Split-Path -Parent $Python) 'Scripts'
  $cand = Join-Path $scripts 'ansys-fluent-mcp.exe'
  if (Test-Path $cand) { $mcpExe = $cand }
}
if (-not $mcpExe) {
  $cmd = Get-Command ansys-fluent-mcp.exe -ErrorAction SilentlyContinue
  if ($cmd) { $mcpExe = $cmd.Source }
}
if (-not $mcpExe) {
  Write-Warning "ansys-fluent-mcp.exe not detected. Install ansys-fluent-mcp and set env PYTHON_ANSYS_FLUENT_MCP, or edit command in agent.cordis.yml."
  $mcpExe = '__PYTHON_ANSYS_FLUENT_MCP__'
} else { Write-Host "mcp    : $mcpExe" }

# --- locate ANSYS AWP root ---
if (-not $AnsysRoot) { $AnsysRoot = $env:ANSYS_AWP_ROOT }
if (-not $AnsysRoot) {
  # Scan ALL fixed drives for `...\Program Files\ANSYS Inc\v#{n}` / `...\ANSYS Inc\v#{n}`,
  # take the HIGHEST version (supports ANSYS on any drive, e.g. D:\, and 24R2+).
  $bases = @()
  foreach ($drv in (Get-PSDrive -PSProvider FileSystem -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Root)) {
    $bases += (Join-Path $drv 'Program Files\ANSYS Inc')
    $bases += (Join-Path $drv 'ANSYS Inc')
  }
  $best = $null; $bestV = -1
  foreach ($b in ($bases | Select-Object -Unique)) {
    if (Test-Path $b) {
      foreach ($v in (Get-ChildItem $b -Directory -Filter 'v*' -ErrorAction SilentlyContinue)) {
        if ($v.Name -match '^v(\d+)$') {
          $vn = [int]$Matches[1]
          if ($vn -gt $bestV) { $bestV = $vn; $best = $v.FullName }
        }
      }
    }
  }
  if ($best) { $AnsysRoot = $best }
}
if (-not $AnsysRoot) {
  Write-Warning "ANSYS install not detected. Set env ANSYS_AWP_ROOT (e.g. C:\Program Files\ANSYS Inc\v252)."
  $AnsysRoot = '__ANSYS_AWP_ROOT__'
} else { Write-Host "ansys  : $AnsysRoot" }

# --- copy preset into place ---
if (Test-Path $Target) {
  if (-not $Force) {
    $bak = "$Target.bak-$(Get-Date -Format yyyyMMdd-HHmmss)"
    Write-Host "existing install -> backing up to $bak"
    Move-Item $Target $bak
  } else { Remove-Item $Target -Recurse -Force }
}
New-Item -ItemType Directory -Path (Split-Path $Target) -Force | Out-Null
Copy-Item -Path $Src -Destination $Target -Recurse -Force
Write-Host "copied preset -> $Target"

# --- derive the AWP_ROOT<version> env var name from the ansys dir (v241 -> AWP_ROOT241) ---
$awpVar = '__AWP_ROOT_VARNAME__'
if ($AnsysRoot -match 'v(\d+)\s*$') { $awpVar = "AWP_ROOT$($Matches[1])" }
elseif ($AnsysRoot -notmatch '__') {
  $leaf = Split-Path $AnsysRoot -Leaf
  if ($leaf -match 'v(\d+)') { $awpVar = "AWP_ROOT$($Matches[1])" }
}
Write-Host "awp var: $awpVar"

# --- substitute the three templates ---
$yml = Join-Path $Target 'agent.cordis.yml'
$content = Get-Content $yml -Raw
$content = $content -replace '__PYTHON_ANSYS_FLUENT_MCP__', $mcpExe
$content = $content -replace '__AWP_ROOT_VARNAME__', $awpVar
$content = $content -replace '__ANSYS_AWP_ROOT__', $AnsysRoot
Set-Content -Path $yml -Value $content -NoNewline -Encoding UTF8
Write-Host "filled machine paths in agent.cordis.yml"

# --- verify ---
$check = Get-Content $yml -Raw
if ($check -match '__PYTHON_ANSYS_FLUENT_MCP__' -or $check -match '__ANSYS_AWP_ROOT__' -or $check -match '__AWP_ROOT_VARNAME__') {
  Write-Warning "One or more tokens could not be resolved. Edit agent.cordis.yml manually."
} else {
  Write-Host "RESOLVED: no unresolved tokens." -ForegroundColor Green
}

Write-Host ""
Write-Host "Done. Start a DSH agent from the 'fluent-cfd' preset. Prereqs: ANSYS Fluent v25.2 + license, pyfluent-core, ansys-fluent-mcp." -ForegroundColor Cyan
