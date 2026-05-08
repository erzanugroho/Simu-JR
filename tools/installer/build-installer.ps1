param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
    [string]$Version = "1.0.0",
    [string]$OutputDir = (Join-Path (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path "dist-installer")
)

$ErrorActionPreference = "Stop"

function Find-InnoSetup {
    $candidates = @(
        "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        "C:\Program Files\Inno Setup 6\ISCC.exe"
    )
    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) { return $candidate }
    }
    $cmd = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    throw "Inno Setup 6 tidak ditemukan. Install Inno Setup lalu jalankan ulang."
}

$simDir = Join-Path $ProjectRoot "simulasi"
$frontendDir = Join-Path $simDir "frontend"
$payloadDir = Join-Path $OutputDir "payload"
$appPayload = Join-Path $payloadDir "app"

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
if (Test-Path $payloadDir) {
    Remove-Item -LiteralPath $payloadDir -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $appPayload | Out-Null

Write-Host "Building frontend..."
Push-Location $frontendDir
try {
    npm run build
    if ($LASTEXITCODE -ne 0) { throw "npm run build failed." }
} finally {
    Pop-Location
}

Write-Host "Copying runtime payload..."
$items = @(
    "server.py",
    "main.py",
    "config.yaml",
    ".env.example",
    "requirements-runtime.txt",
    "MULAI_SIMULASI.bat",
    "core",
    "ocr_tessdata",
    "frontend\dist",
    "static",
    "docs"
)
foreach ($item in $items) {
    $src = Join-Path $simDir $item
    if (Test-Path $src) {
        $dst = Join-Path $appPayload $item
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $dst) | Out-Null
        Copy-Item -LiteralPath $src -Destination $dst -Recurse -Force
    }
}

New-Item -ItemType Directory -Force -Path (Join-Path $appPayload "rag") | Out-Null
Copy-Item -LiteralPath (Join-Path $simDir "rag\*.py") -Destination (Join-Path $appPayload "rag") -Force
Copy-Item -LiteralPath (Join-Path $simDir "rag\prompts") -Destination (Join-Path $appPayload "rag\prompts") -Recurse -Force
if (Test-Path (Join-Path $simDir "rag\uud_1945.json")) {
    Copy-Item -LiteralPath (Join-Path $simDir "rag\uud_1945.json") -Destination (Join-Path $appPayload "rag\uud_1945.json") -Force
}

Write-Host "Removing generated/large files from payload..."
$removePatterns = @(
    "frontend\dist\.vite",
    "__pycache__"
)
foreach ($pattern in $removePatterns) {
    $target = Join-Path $appPayload $pattern
    if (Test-Path $target) {
        Remove-Item -LiteralPath $target -Recurse -Force
    }
}
Get-ChildItem -LiteralPath $appPayload -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force
Get-ChildItem -LiteralPath $appPayload -Recurse -File -Include "*.pyc","*.log","*.err.log","*.out.log" | Remove-Item -Force

New-Item -ItemType Directory -Force -Path (Join-Path $appPayload "tools\installer") | Out-Null
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "configure-simujr.ps1") -Destination (Join-Path $appPayload "tools\installer\configure-simujr.ps1") -Force
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "update-rag-data-pack.ps1") -Destination (Join-Path $appPayload "tools\installer\update-rag-data-pack.ps1") -Force
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "run-simujr.bat") -Destination (Join-Path $appPayload "run-simujr.bat") -Force

$sevenZipCandidates = @(
    "C:\Program Files\7-Zip\7z.exe",
    "C:\Program Files (x86)\7-Zip\7z.exe"
)
foreach ($candidate in $sevenZipCandidates) {
    if (Test-Path $candidate) {
        New-Item -ItemType Directory -Force -Path (Join-Path $appPayload "tools\7zip") | Out-Null
        Copy-Item -LiteralPath $candidate -Destination (Join-Path $appPayload "tools\7zip\7z.exe") -Force
        break
    }
}

Write-Host "Preparing embedded Python..."
powershell -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "prepare-embedded-python.ps1") `
    -TargetDir (Join-Path $appPayload "python") `
    -RequirementsPath (Join-Path $appPayload "requirements-runtime.txt")

$iscc = Find-InnoSetup
$iss = Join-Path $PSScriptRoot "SimuJR.iss"
& $iscc "/DMyAppVersion=$Version" "/DProjectRoot=$ProjectRoot" "/DOutputDir=$OutputDir" $iss
if ($LASTEXITCODE -ne 0) {
    throw "Inno Setup failed with code $LASTEXITCODE."
}

Write-Host "Installer built in $OutputDir"
