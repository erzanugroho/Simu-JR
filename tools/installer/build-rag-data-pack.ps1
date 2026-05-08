param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
    [string]$DataVersion = (Get-Date -Format "yyyy-MM"),
    [string]$SourceLabel = "MK PUU corpus",
    [string]$OutputDir = (Join-Path (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path "dist-installer"),
    [switch]$SplitVolumes
)

$ErrorActionPreference = "Stop"

function Find-7Zip {
    $candidates = @(
        "C:\Program Files\7-Zip\7z.exe",
        "C:\Program Files (x86)\7-Zip\7z.exe"
    )
    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) { return $candidate }
    }
    $cmd = Get-Command 7z.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    throw "7-Zip tidak ditemukan. Install 7-Zip terlebih dahulu."
}

function Get-CollectionCounts {
    param([string]$SqlitePath)
    $python = Get-Command python -ErrorAction Stop
    $script = @"
import json, sqlite3, sys
db = sys.argv[1]
uri = "file:" + db.replace("\\", "/") + "?mode=ro"
with sqlite3.connect(uri, uri=True, timeout=5.0) as conn:
    rows = conn.execute('''
        SELECT c.name, COUNT(e.id)
        FROM collections c
        JOIN segments s ON s.collection = c.id AND s.scope = 'METADATA'
        LEFT JOIN embeddings e ON e.segment_id = s.id
        GROUP BY c.name
    ''').fetchall()
print(json.dumps({name: count for name, count in rows}, ensure_ascii=False))
"@
    $json = $script | & $python.Source - $SqlitePath
    return $json | ConvertFrom-Json
}

$simDir = Join-Path $ProjectRoot "simulasi"
$ragDir = Join-Path $simDir "rag"
$chromaDir = Join-Path $ragDir "chroma_db"
$sqlitePath = Join-Path $chromaDir "chroma.sqlite3"
$compressedJsonl = Join-Path $ragDir "rag_chunks_compressed.jsonl"
$manifestPath = Join-Path $ragDir "rag_data_manifest.json"

if (-not (Test-Path $sqlitePath)) {
    throw "ChromaDB tidak ditemukan: $sqlitePath"
}

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

$counts = Get-CollectionCounts -SqlitePath $sqlitePath
$files = [ordered]@{}
$files["chroma.sqlite3"] = @{
    path = "chroma_db/chroma.sqlite3"
    bytes = (Get-Item -LiteralPath $sqlitePath).Length
    sha256 = (Get-FileHash -LiteralPath $sqlitePath -Algorithm SHA256).Hash.ToLowerInvariant()
}
if (Test-Path $compressedJsonl) {
    $files["rag_chunks_compressed.jsonl"] = @{
        path = "rag_chunks_compressed.jsonl"
        bytes = (Get-Item -LiteralPath $compressedJsonl).Length
        sha256 = (Get-FileHash -LiteralPath $compressedJsonl -Algorithm SHA256).Hash.ToLowerInvariant()
    }
}

$manifest = [ordered]@{
    schema_version = 1
    data_version = $DataVersion
    built_at = (Get-Date).ToString("s")
    source_label = $SourceLabel
    collection_counts = $counts
    files = $files
}
$manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $manifestPath -Encoding UTF8
Write-Host "Wrote manifest: $manifestPath"

$sevenZip = Find-7Zip
$archive = Join-Path $OutputDir "SimuJR-RAGData-$DataVersion.7z"
if (Test-Path $archive) { Remove-Item -LiteralPath $archive -Force }
Get-ChildItem -LiteralPath $OutputDir -Filter "SimuJR-RAGData-$DataVersion.7z.*" | Remove-Item -Force

$args = @("a", "-t7z", "-mx=9", $archive, "chroma_db", "rag_data_manifest.json")
if (Test-Path $compressedJsonl) {
    $args += "rag_chunks_compressed.jsonl"
}
if ($SplitVolumes) {
    $args += "-v3900m"
}

Push-Location $ragDir
try {
    & $sevenZip @args | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "7-Zip failed with code $LASTEXITCODE." }
} finally {
    Pop-Location
}

Write-Host "RAG data pack built in $OutputDir"

