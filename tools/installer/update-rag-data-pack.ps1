param(
    [string]$ArchivePath = "",
    [string]$DataRoot = (Join-Path $env:ProgramData "SimuJR"),
    [string]$InstallDir = (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
)

$ErrorActionPreference = "Stop"

if (-not $ArchivePath) {
    Add-Type -AssemblyName System.Windows.Forms
    $dialog = New-Object System.Windows.Forms.OpenFileDialog
    $dialog.Title = "Pilih Simu JR RAG Data Pack"
    $dialog.Filter = "RAG data pack (*.7z;*.001)|*.7z;*.001|All files (*.*)|*.*"
    if ($dialog.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) {
        Write-Host "Update dibatalkan."
        exit 0
    }
    $ArchivePath = $dialog.FileName
}

function Find-7Zip {
    $candidates = @(
        (Join-Path $InstallDir "tools\7zip\7z.exe"),
        "C:\Program Files\7-Zip\7z.exe",
        "C:\Program Files (x86)\7-Zip\7z.exe"
    )
    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) { return $candidate }
    }
    $cmd = Get-Command 7z.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    throw "7-Zip tidak ditemukan. Install 7-Zip atau bundel 7z.exe di tools\7zip\."
}

function Set-EnvValue {
    param(
        [Parameter(Mandatory=$true)][string]$Path,
        [Parameter(Mandatory=$true)][string]$Key,
        [Parameter(Mandatory=$true)][string]$Value
    )

    $line = "$Key=$Value"
    if (Test-Path $Path) {
        $content = Get-Content -LiteralPath $Path
        $updated = $false
        $next = foreach ($item in $content) {
            if ($item -match "^\s*$([regex]::Escape($Key))=") {
                $updated = $true
                $line
            } else {
                $item
            }
        }
        if (-not $updated) { $next += $line }
        Set-Content -LiteralPath $Path -Value $next -Encoding UTF8
    } else {
        Set-Content -LiteralPath $Path -Value @($line) -Encoding UTF8
    }
}

function Resolve-ExtractedRagRoot {
    param([Parameter(Mandatory=$true)][string]$TempDir)

    $directManifest = Join-Path $TempDir "rag_data_manifest.json"
    $directChroma = Join-Path $TempDir "chroma_db\chroma.sqlite3"
    if ((Test-Path $directManifest) -and (Test-Path $directChroma)) {
        return $TempDir
    }

    $ragDir = Join-Path $TempDir "rag"
    $ragManifest = Join-Path $ragDir "rag_data_manifest.json"
    $ragChroma = Join-Path $ragDir "chroma_db\chroma.sqlite3"
    if ((Test-Path $ragManifest) -and (Test-Path $ragChroma)) {
        return $ragDir
    }

    $manifest = Get-ChildItem -LiteralPath $TempDir -Recurse -Filter "rag_data_manifest.json" | Select-Object -First 1
    if ($manifest) {
        $candidate = $manifest.Directory.FullName
        if (Test-Path (Join-Path $candidate "chroma_db\chroma.sqlite3")) {
            return $candidate
        }
    }

    throw "Arsip RAG tidak valid: rag_data_manifest.json atau chroma_db\chroma.sqlite3 tidak ditemukan."
}

$archive = Resolve-Path -LiteralPath $ArchivePath
$sevenZip = Find-7Zip

New-Item -ItemType Directory -Force -Path $DataRoot | Out-Null
$ragRoot = Join-Path $DataRoot "rag"
$backupRoot = Join-Path $DataRoot "rag_backup"
$envPath = Join-Path $DataRoot ".env"
New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null

$temp = Join-Path $env:TEMP ("simujr-rag-update-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $temp | Out-Null

$backupPath = $null
$oldVersion = "unknown"
try {
    Write-Host "Extracting RAG data pack..."
    & $sevenZip x "-o$temp" -y $archive.Path | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "7-Zip extraction failed with code $LASTEXITCODE." }

    $newRagRoot = Resolve-ExtractedRagRoot -TempDir $temp
    $manifestPath = Join-Path $newRagRoot "rag_data_manifest.json"
    $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    if (-not $manifest.data_version) {
        throw "Manifest tidak memiliki data_version."
    }

    if (Test-Path (Join-Path $ragRoot "rag_data_manifest.json")) {
        try {
            $oldManifest = Get-Content -LiteralPath (Join-Path $ragRoot "rag_data_manifest.json") -Raw | ConvertFrom-Json
            if ($oldManifest.data_version) { $oldVersion = $oldManifest.data_version }
        } catch {
            $oldVersion = "unknown"
        }
    }

    if (Test-Path $ragRoot) {
        $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
        $safeOldVersion = ($oldVersion -replace '[^\w\-.]', '_')
        $backupPath = Join-Path $backupRoot "$safeOldVersion-$stamp"
        Write-Host "Backing up current RAG data to $backupPath"
        Move-Item -LiteralPath $ragRoot -Destination $backupPath
    }

    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $ragRoot) | Out-Null
    Move-Item -LiteralPath $newRagRoot -Destination $ragRoot

    Set-EnvValue -Path $envPath -Key "CHROMA_DB_PATH" -Value (Join-Path $ragRoot "chroma_db")
    Set-EnvValue -Path $envPath -Key "RAG_DATA_MANIFEST_PATH" -Value (Join-Path $ragRoot "rag_data_manifest.json")
    Set-EnvValue -Path $envPath -Key "SIMUJR_DATA_ROOT" -Value $DataRoot

    Write-Host "RAG data updated successfully."
    Write-Host "New version: $($manifest.data_version)"
    Write-Host "Data root:   $ragRoot"
} catch {
    Write-Host "[ERROR] $($_.Exception.Message)" -ForegroundColor Red
    if ((-not (Test-Path $ragRoot)) -and $backupPath -and (Test-Path $backupPath)) {
        Write-Host "Restoring previous RAG data..."
        Move-Item -LiteralPath $backupPath -Destination $ragRoot
    }
    throw
} finally {
    if (Test-Path $temp) {
        Remove-Item -LiteralPath $temp -Recurse -Force -ErrorAction SilentlyContinue
    }
}
