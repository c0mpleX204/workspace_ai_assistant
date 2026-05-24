[CmdletBinding()]
param(
  [string]$Version = "",
  [string]$OutputDir = "",
  [switch]$SkipNpmInstall,
  [switch]$SkipBackendBuild,
  [switch]$SkipPyInstallerInstall
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Write-Step {
  param([string]$Message)
  Write-Host "[build-zip] $Message" -ForegroundColor Cyan
}

function Invoke-Step {
  param(
    [string]$FilePath,
    [string[]]$Arguments,
    [string]$WorkingDirectory
  )

  Write-Host "> $FilePath $($Arguments -join ' ')" -ForegroundColor DarkGray
  Push-Location $WorkingDirectory
  try {
    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
      throw "Command failed with exit code $LASTEXITCODE"
    }
  } finally {
    Pop-Location
  }
}

function Assert-Command {
  param([string]$Name)
  if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
    throw "Required command not found: $Name"
  }
}

function New-CleanDirectory {
  param([string]$Path)
  if (Test-Path -LiteralPath $Path) {
    Remove-Item -LiteralPath $Path -Recurse -Force
  }
  New-Item -ItemType Directory -Path $Path -Force | Out-Null
}

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = (Resolve-Path (Join-Path $ScriptDir "..")).Path
$ClientDir = Join-Path $RootDir "client"
$BuildDir = Join-Path $RootDir "build"
$ReleaseDir = if ([string]::IsNullOrWhiteSpace($OutputDir)) {
  Join-Path $RootDir "release"
} else {
  $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($OutputDir)
}

if (-not (Test-Path -LiteralPath $ClientDir)) {
  throw "Client directory not found: $ClientDir"
}

Assert-Command "npm"
Assert-Command "npx"

$ClientPackage = Get-Content -Raw -LiteralPath (Join-Path $ClientDir "package.json") | ConvertFrom-Json
if ([string]::IsNullOrWhiteSpace($Version)) {
  $Version = "$($ClientPackage.version)-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
}

$SafeVersion = $Version -replace "[^a-zA-Z0-9._-]+", "-"
$PackageName = "workspace-ai-assistant-$SafeVersion-win-x64"
$StageDir = Join-Path $BuildDir "zip\$PackageName"
$ElectronOutDir = Join-Path $BuildDir "electron"
$BackendOutDir = Join-Path $BuildDir "backend"
$PyInstallerWorkDir = Join-Path $BuildDir "pyinstaller-work"
$PyInstallerSpecDir = Join-Path $BuildDir "pyinstaller-spec"
$ZipPath = Join-Path $ReleaseDir "$PackageName.zip"

Write-Step "root: $RootDir"
Write-Step "version: $SafeVersion"

New-Item -ItemType Directory -Path $BuildDir -Force | Out-Null
New-Item -ItemType Directory -Path $ReleaseDir -Force | Out-Null

if (-not $SkipNpmInstall -and -not (Test-Path -LiteralPath (Join-Path $ClientDir "node_modules"))) {
  Write-Step "installing frontend dependencies"
  Invoke-Step "npm" @("ci") $ClientDir
}

Write-Step "building frontend"
Invoke-Step "npm" @("run", "build") $ClientDir

if (-not $SkipBackendBuild) {
  $PythonExe = Join-Path $RootDir ".venv\Scripts\python.exe"
  if (-not (Test-Path -LiteralPath $PythonExe)) {
    $PythonCommand = Get-Command "python" -ErrorAction SilentlyContinue
    if (-not $PythonCommand) {
      throw "Python not found. Create .venv first or put python on PATH."
    }
    $PythonExe = $PythonCommand.Source
  }

  if (-not $SkipPyInstallerInstall) {
    Write-Step "checking PyInstaller"
    Push-Location $RootDir
    try {
      & $PythonExe -m pip show pyinstaller *> $null
      if ($LASTEXITCODE -ne 0) {
        Write-Step "installing PyInstaller into current Python environment"
        Invoke-Step $PythonExe @("-m", "pip", "install", "pyinstaller") $RootDir
      }
    } finally {
      Pop-Location
    }
  }

  New-CleanDirectory $BackendOutDir
  New-CleanDirectory $PyInstallerWorkDir
  New-CleanDirectory $PyInstallerSpecDir

  $DataSeparator = if ($env:OS -eq "Windows_NT") { ";" } else { ":" }
  $PyInstallerArgs = @(
    "-m", "PyInstaller",
    "--noconfirm",
    "--clean",
    "--onedir",
    "--name", "workspace-backend",
    "--paths", $RootDir,
    "--distpath", $BackendOutDir,
    "--workpath", $PyInstallerWorkDir,
    "--specpath", $PyInstallerSpecDir,
    "--collect-submodules", "uvicorn",
    "--collect-submodules", "fastapi",
    "--hidden-import=uvicorn.loops.auto",
    "--hidden-import=uvicorn.protocols.http.auto",
    "--hidden-import=uvicorn.protocols.websockets.auto",
    "--hidden-import=uvicorn.lifespan.on"
  )
  if (Test-Path -LiteralPath (Join-Path $RootDir "server")) {
    $PyInstallerArgs += @("--add-data", "server${DataSeparator}server")
  }
  if (Test-Path -LiteralPath (Join-Path $RootDir "skills")) {
    $PyInstallerArgs += @("--add-data", "skills${DataSeparator}skills")
  }
  $PyInstallerArgs += @("server.py")

  Write-Step "building backend executable"
  Invoke-Step $PythonExe $PyInstallerArgs $RootDir
}

New-CleanDirectory $ElectronOutDir
$BuilderConfigPath = Join-Path $BuildDir "electron-builder-zip.json"
$BuilderConfig = @{
  appId = "com.liminglong.workspace-ai-assistant"
  productName = "Workspace AI Assistant"
  asar = $false
  directories = @{
    output = $ElectronOutDir
  }
  files = @(
    "dist/**/*",
    "main.js",
    "preload.js",
    "package.json"
  )
  win = @{
    target = @("dir")
  }
}
$BuilderConfig | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $BuilderConfigPath -Encoding UTF8

Write-Step "packaging Electron app directory"
Invoke-Step "npx" @("--yes", "electron-builder@24.13.3", "--win", "dir", "--config", $BuilderConfigPath) $ClientDir

$UnpackedDir = Get-ChildItem -LiteralPath $ElectronOutDir -Directory -Filter "*win-unpacked" |
  Select-Object -First 1
if (-not $UnpackedDir) {
  throw "Electron unpacked directory not found under $ElectronOutDir"
}

New-CleanDirectory $StageDir
$AppDir = Join-Path $StageDir "app"
$PortableBackendDir = Join-Path $StageDir "backend"
New-Item -ItemType Directory -Path $AppDir -Force | Out-Null
Copy-Item -Path (Join-Path $UnpackedDir.FullName "*") -Destination $AppDir -Recurse -Force

if (-not $SkipBackendBuild) {
  $BuiltBackendDir = Join-Path $BackendOutDir "workspace-backend"
  if (-not (Test-Path -LiteralPath $BuiltBackendDir)) {
    throw "Backend build output not found: $BuiltBackendDir"
  }
  Copy-Item -LiteralPath $BuiltBackendDir -Destination $PortableBackendDir -Recurse -Force
}

New-Item -ItemType Directory -Path (Join-Path $StageDir "data\runtime") -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $StageDir "data\upload") -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $StageDir "logs") -Force | Out-Null

$StartPs1 = @'
$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendExe = Join-Path $RootDir "backend\workspace-backend.exe"
$AppExe = Join-Path $RootDir "app\Workspace AI Assistant.exe"
$BackendUrl = "http://127.0.0.1:8000"

if (-not (Test-Path -LiteralPath $AppExe)) {
  throw "Desktop app not found: $AppExe"
}

$env:HOST = "127.0.0.1"
$env:PORT = "8000"
$env:BACKEND_URL = $BackendUrl
$env:PROVIDER_CONFIG_PATH = Join-Path $RootDir "data\runtime\provider_config.json"

$backend = $null
if (Test-Path -LiteralPath $BackendExe) {
  $LogDir = Join-Path $RootDir "logs"
  New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
  $backend = Start-Process `
    -FilePath $BackendExe `
    -WorkingDirectory $RootDir `
    -PassThru `
    -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $LogDir "backend.out.log") `
    -RedirectStandardError (Join-Path $LogDir "backend.err.log")
  $deadline = (Get-Date).AddSeconds(25)
  do {
    try {
      Invoke-WebRequest -UseBasicParsing "$BackendUrl/health" -TimeoutSec 1 | Out-Null
      break
    } catch {
      Start-Sleep -Milliseconds 500
    }
  } while ((Get-Date) -lt $deadline)
}

$app = Start-Process -FilePath $AppExe -WorkingDirectory (Join-Path $RootDir "app") -PassThru
$app.WaitForExit()

if ($backend -and -not $backend.HasExited) {
  Stop-Process -Id $backend.Id -Force
}
'@
$StartPs1 | Set-Content -LiteralPath (Join-Path $StageDir "start-app.ps1") -Encoding UTF8

$StartBat = @'
@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-app.ps1"
endlocal
'@
$StartBat | Set-Content -LiteralPath (Join-Path $StageDir "start-app.bat") -Encoding ASCII

$Readme = @"
Workspace AI Assistant portable package

How to run:
1. Extract this zip to a normal writable folder.
2. Double-click start-app.bat.
3. Runtime data is written to the data and logs folders next to this file.

Notes:
- Do not run directly from inside the zip preview.
- The launcher starts the backend first, then opens the Electron desktop app.
- If port 8000 is already in use, close the other backend process first.
"@
$Readme | Set-Content -LiteralPath (Join-Path $StageDir "README.txt") -Encoding UTF8

if (Test-Path -LiteralPath $ZipPath) {
  Remove-Item -LiteralPath $ZipPath -Force
}

Write-Step "creating zip"
Compress-Archive -Path $StageDir -DestinationPath $ZipPath -Force

Write-Step "done: $ZipPath"
