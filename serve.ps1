# Serve the book shelf locally, with a Claude session behind it.
# index.html reads the JSON files with fetch(), which is blocked on file:// — so it
# needs a real HTTP origin, not a double-click. serve.py adds the assistant panel and
# binds loopback only: the agent behind it can write files, so nothing off this
# machine may reach it.
param([int]$Port = 8777)

$root = $PSScriptRoot
$api  = "http://127.0.0.1:$Port/api/state"

function Test-Api {
    try { (Invoke-WebRequest $api -TimeoutSec 2 -UseBasicParsing).StatusCode -eq 200 }
    catch { $false }
}

# A leftover `python -m http.server` binds 0.0.0.0 while serve.py binds 127.0.0.1,
# and Windows lets both hold the port. The stale one serves the page with no API
# behind it, so check before starting rather than after.
if (Test-Api) {
    Write-Host "serve.py is already running on port $Port." -ForegroundColor Yellow
    Start-Process "http://localhost:$Port/"
    return
}

Write-Host "Starting serve.py on port $Port…" -ForegroundColor Cyan
$server = Start-Process python -ArgumentList "`"$root\serve.py`"", "--port", $Port -NoNewWindow -PassThru

for ($i = 0; $i -lt 60; $i++) {
    if ($server.HasExited) {
        Write-Host "serve.py exited (code $($server.ExitCode)). Nothing was opened." -ForegroundColor Red
        return
    }
    if (Test-Api) {
        Write-Host "Book shelf → http://localhost:$Port/  (Ctrl+C to stop)" -ForegroundColor Cyan
        Start-Process "http://localhost:$Port/"
        Wait-Process -Id $server.Id
        return
    }
    Start-Sleep -Milliseconds 250
}

Write-Host "serve.py did not answer on $api within 15 s." -ForegroundColor Red
Write-Host "If an old 'python -m http.server' still holds port $Port, stop it with:" -ForegroundColor Red
Write-Host "  Get-NetTCPConnection -LocalPort $Port -State Listen | ForEach-Object { Stop-Process -Id `$_.OwningProcess -Force }"
