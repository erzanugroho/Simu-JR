param(
    [string]$InstallDir = (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)),
    [string]$DataRoot = (Join-Path $env:ProgramData "SimuJR")
)

$ErrorActionPreference = "Stop"

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
        if (-not $updated) {
            $next += $line
        }
        Set-Content -LiteralPath $Path -Value $next -Encoding UTF8
    } else {
        Set-Content -LiteralPath $Path -Value @($line) -Encoding UTF8
    }
}

New-Item -ItemType Directory -Force -Path $DataRoot | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $DataRoot "results") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $DataRoot "temp_uploads") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $DataRoot "logs") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $DataRoot "rag") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $DataRoot "rag_backup") | Out-Null

$envPath = Join-Path $DataRoot ".env"
$templatePath = Join-Path $InstallDir ".env.example"
if (-not (Test-Path $envPath)) {
    if (Test-Path $templatePath) {
        Copy-Item -LiteralPath $templatePath -Destination $envPath
    } else {
        Set-Content -LiteralPath $envPath -Encoding UTF8 -Value @(
            "LLM_BASE_URL=http://127.0.0.1:1234/v1",
            "LLM_API_KEY=not-needed-for-local",
            "LLM_MODEL_NAME=local-model"
        )
    }
}

Set-EnvValue -Path $envPath -Key "CHROMA_DB_PATH" -Value (Join-Path $DataRoot "rag\chroma_db")
Set-EnvValue -Path $envPath -Key "RAG_DATA_MANIFEST_PATH" -Value (Join-Path $DataRoot "rag\rag_data_manifest.json")
Set-EnvValue -Path $envPath -Key "SIMUJR_DATA_ROOT" -Value $DataRoot

Write-Host "Simu JR configured."
Write-Host "InstallDir: $InstallDir"
Write-Host "DataRoot:   $DataRoot"
Write-Host "Env file:   $envPath"

