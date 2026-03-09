<#
.SYNOPSIS
    Testing script for the R_viewer HTTP API.

.DESCRIPTION
    This script tests the core API endpoints of r_viewer:
    1. GET /api/health
    2. POST /api/ingest
    3. GET /api/events
#>

$BaseUrl = "http://localhost:8080"
$LogFile = ".\r_viewer_api_test_log.txt"

# Start transcript for logging
Start-Transcript -Path $LogFile -Force

function Write-Log {
    param([string]$Message, [string]$Level = "INFO")
    $Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $LogMessage = "[$Timestamp] [$Level] $Message"
    Write-Host $LogMessage
}

try {
    Write-Log "Starting API tests..."

    # 1. Test /api/health
    Write-Log "Testing GET /api/health..."
    $health = Invoke-RestMethod -Uri "$BaseUrl/api/health" -Method Get
    Write-Log "Health Check Response: $($health | ConvertTo-Json -Compress)"
    if ($health.success -ne $true) {
        throw "Health check failed!"
    }

    # 2. Test /api/ingest
    Write-Log "Testing POST /api/ingest (System channel)..."
    $ingestBody = @{
        channel = "System"
        limit   = 10
    } | ConvertTo-Json
    $ingest = Invoke-RestMethod -Uri "$BaseUrl/api/ingest" -Method Post -Body $ingestBody -ContentType "application/json"
    Write-Log "Ingest Response: $($ingest | ConvertTo-Json -Compress)"
    if ($ingest.success -ne $true) {
        throw "Ingest failed!"
    }
    Write-Log "Successfully ingested $($ingest.data) events."

    # 3. Test /api/events
    Write-Log "Testing GET /api/events (System channel)..."
    $events = Invoke-RestMethod -Uri "$BaseUrl/api/events?channel=System&limit=5" -Method Get
    Write-Log "Events Query Response: $($events | ConvertTo-Json -Compress)"
    if ($events.success -ne $true) {
        throw "Query failed!"
    }
    Write-Log "Successfully retrieved $($events.data.Count) events."

    Write-Log "All API tests completed successfully." -Level "SUCCESS"
}
catch {
    Write-Log "An error occurred during API testing: $_" -Level "ERROR"
    exit 1
}
finally {
    Stop-Transcript
    Write-Log "API testing finished. Check $LogFile for details."
}
