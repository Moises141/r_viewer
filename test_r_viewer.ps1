<#
.SYNOPSIS
    Testing script for the R_viewer Windows Event Log application.

.DESCRIPTION
    This script compiles the r_viewer application and tests its core functionalities:
    1. Ingestion of Windows Event Logs (System).
    2. Querying of ingested logs by Level (Error).
    Includes robust error handling and logging to a transcript file.

.EXAMPLE
    .\test_r_viewer.ps1
#>

$ErrorActionPreference = "Continue"
$LogFile = ".\r_viewer_test_log.txt"
$ExePath = ".\target\debug\r_viewer.exe"

# Start transcript for logging
Start-Transcript -Path $LogFile -Force

function Write-Log {
    param([string]$Message, [string]$Level = "INFO")
    $Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $LogMessage = "[$Timestamp] [$Level] $Message"
    Write-Host $LogMessage
}

try {
    Write-Log "Starting compilation of r_viewer..."
    $buildOutput = cargo build 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Compilation failed:`n$buildOutput"
    }
    Write-Log "Compilation successful."

    if (-Not (Test-Path $ExePath)) {
        throw "Executable not found at $ExePath after build."
    }

    Write-Log "Testing 'hello' command..."
    $helloOutput = & $ExePath hello 2>&1
    Write-Log "Hello Output:`n$helloOutput"

    Write-Log "Testing 'ingest' command (System channel, limit 50)..."
    $ingestOutput = & $ExePath ingest --channel system --limit 50 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Ingest command failed:`n$ingestOutput"
    }
    Write-Log "Ingest Output:`n$ingestOutput"

    Write-Log "Testing 'query' command (Error level, limit 10)..."
    $queryOutput = & $ExePath query --level error --limit 10 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Query command failed:`n$queryOutput"
    }
    Write-Log "Query Output (Error Level):`n$queryOutput"

    Write-Log "Testing 'ingest' command (Application channel, limit 20)..."
    $ingestAppOutput = & $ExePath ingest --channel application --limit 20 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Ingest Application command failed:`n$ingestAppOutput"
    }
    Write-Log "Ingest Application Output:`n$ingestAppOutput"

    Write-Log "Testing 'query' command (Application channel, Information level, limit 5)..."
    $queryAppOutput = & $ExePath query --channel application --level information --limit 5 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Query Application command failed:`n$queryAppOutput"
    }
    Write-Log "Query Application Output:`n$queryAppOutput"

    Write-Log "Testing invalid channel argument (Expected to fail gracefully)..."
    $invalidOutput = & $ExePath ingest --channel invalidchannel --limit 5 2>&1
    if ($LASTEXITCODE -eq 0) {
        throw "Invalid channel test should have failed, but it succeeded!"
    }
    Write-Log "Invalid Channel Output (Expected Error):`n$invalidOutput"

    Write-Log "All tests completed successfully." -Level "SUCCESS"
}
catch {
    Write-Log "An error occurred during testing: $_" -Level "ERROR"
    if ($_.Exception -and $_.Exception.InnerException) {
        Write-Log "Inner Exception: $($_.Exception.InnerException.Message)" -Level "ERROR"
    }
    exit 1
}
finally {
    Stop-Transcript
    Write-Log "Testing finished. Check $LogFile for details."
}
