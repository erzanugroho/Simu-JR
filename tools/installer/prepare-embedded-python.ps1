param(
    [string]$PythonVersion = "3.11.9",
    [string]$TargetDir,
    [string]$RequirementsPath
)

$ErrorActionPreference = "Stop"

if (-not $TargetDir) {
    throw "TargetDir wajib diisi."
}
if (-not $RequirementsPath) {
    throw "RequirementsPath wajib diisi."
}

$targetItem = New-Item -ItemType Directory -Force -Path $TargetDir
$target = Resolve-Path -LiteralPath $targetItem.FullName
$requirements = Resolve-Path -LiteralPath $RequirementsPath
$work = Join-Path $env:TEMP ("simujr-python-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $work | Out-Null

try {
    $zipName = "python-$PythonVersion-embed-amd64.zip"
    $zipPath = Join-Path $work $zipName
    $url = "https://www.python.org/ftp/python/$PythonVersion/$zipName"

    Write-Host "Downloading embedded Python $PythonVersion..."
    Invoke-WebRequest -Uri $url -OutFile $zipPath

    Write-Host "Extracting embedded Python..."
    Expand-Archive -LiteralPath $zipPath -DestinationPath $target.Path -Force

    $pth = Get-ChildItem -LiteralPath $target.Path -Filter "python*._pth" | Select-Object -First 1
    if ($pth) {
        $content = Get-Content -LiteralPath $pth.FullName
        $content = $content | ForEach-Object {
            if ($_ -eq "#import site") { "import site" } else { $_ }
        }
        if ($content -notcontains "Lib\site-packages") {
            $content += "Lib\site-packages"
        }
        Set-Content -LiteralPath $pth.FullName -Value $content -Encoding ASCII
    }

    $getPip = Join-Path $work "get-pip.py"
    Invoke-WebRequest -Uri "https://bootstrap.pypa.io/get-pip.py" -OutFile $getPip

    $python = Join-Path $target.Path "python.exe"
    & $python $getPip --no-warn-script-location
    if ($LASTEXITCODE -ne 0) { throw "get-pip failed with code $LASTEXITCODE." }

    & $python -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed with code $LASTEXITCODE." }

    & $python -m pip install --no-warn-script-location -r $requirements.Path
    if ($LASTEXITCODE -ne 0) { throw "pip install runtime dependencies failed with code $LASTEXITCODE." }

    Write-Host "Embedded Python prepared at $($target.Path)"
} finally {
    if (Test-Path $work) {
        Remove-Item -LiteralPath $work -Recurse -Force -ErrorAction SilentlyContinue
    }
}
