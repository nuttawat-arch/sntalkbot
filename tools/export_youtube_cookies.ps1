param(
    [string]$BrowserSpec = "chrome",
    [string]$Output = "$env:USERPROFILE\Downloads\sntalkbot-youtube-cookies.txt",
    [switch]$ListProfiles
)

$ErrorActionPreference = "Stop"

function Get-BaseBrowser([string]$Spec) {
    if ([string]::IsNullOrWhiteSpace($Spec)) { return "chrome" }
    return (($Spec -split ':', 2)[0]).ToLowerInvariant()
}

function Get-ChromiumUserDataDir([string]$Browser) {
    switch ($Browser) {
        "chrome"   { return Join-Path $env:LOCALAPPDATA "Google\Chrome\User Data" }
        "edge"     { return Join-Path $env:LOCALAPPDATA "Microsoft\Edge\User Data" }
        "brave"    { return Join-Path $env:LOCALAPPDATA "BraveSoftware\Brave-Browser\User Data" }
        "chromium" { return Join-Path $env:LOCALAPPDATA "Chromium\User Data" }
        "vivaldi"  { return Join-Path $env:LOCALAPPDATA "Vivaldi\User Data" }
        default     { return $null }
    }
}

function Show-BrowserProfiles([string]$Spec) {
    $browser = Get-BaseBrowser $Spec
    Write-Host "Browser: $browser"

    if ($browser -eq "firefox") {
        $profilesRoot = Join-Path $env:APPDATA "Mozilla\Firefox\Profiles"
        if (-not (Test-Path -LiteralPath $profilesRoot)) {
            Write-Host "Firefox profiles folder was not found: $profilesRoot"
            return
        }
        $dirs = Get-ChildItem -LiteralPath $profilesRoot -Directory | Sort-Object Name
        if (-not $dirs) {
            Write-Host "No Firefox profile folders were found."
            return
        }
        foreach ($dir in $dirs) {
            Write-Host "Profile folder: $($dir.Name)"
            Write-Host ('  BrowserSpec: "firefox:{0}"' -f $dir.FullName)
        }
        Write-Host "Tip: Firefox about:profiles shows the Root Directory for each profile."
        return
    }

    $userData = Get-ChromiumUserDataDir $browser
    if (-not $userData) {
        Write-Host "Automatic profile listing is implemented for chrome, edge, brave, chromium, vivaldi, and firefox."
        Write-Host "yt-dlp also supports other browsers; pass the exact BrowserSpec manually."
        return
    }
    if (-not (Test-Path -LiteralPath $userData)) {
        Write-Host "Browser user-data folder was not found: $userData"
        return
    }

    $seen = @{}
    $localState = Join-Path $userData "Local State"
    if (Test-Path -LiteralPath $localState) {
        try {
            $state = Get-Content -LiteralPath $localState -Raw | ConvertFrom-Json
            $cache = $state.profile.info_cache
            if ($cache) {
                foreach ($prop in $cache.PSObject.Properties) {
                    $dirName = [string]$prop.Name
                    $displayName = [string]$prop.Value.name
                    $seen[$dirName] = $true
                    if ([string]::IsNullOrWhiteSpace($displayName)) { $displayName = $dirName }
                    Write-Host "Profile: $displayName"
                    Write-Host "  Folder: $dirName"
                    Write-Host ('  BrowserSpec: "{0}:{1}"' -f $browser, $dirName)
                }
            }
        } catch {
            Write-Host "Could not read browser Local State; falling back to folder names."
        }
    }

    Get-ChildItem -LiteralPath $userData -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -eq "Default" -or $_.Name -like "Profile *" } |
        Sort-Object Name |
        ForEach-Object {
            if (-not $seen.ContainsKey($_.Name)) {
                Write-Host "Profile folder: $($_.Name)"
                Write-Host ('  BrowserSpec: "{0}:{1}"' -f $browser, $_.Name)
            }
        }

    Write-Host "Tip: Chromium browsers show the exact Profile Path on chrome://version, edge://version, brave://version, etc."
    Write-Host "Use the last folder name (for example Default or Profile 2) after the colon in BrowserSpec."
}

function Invoke-YtDlp([string[]]$Args) {
    $exe = Get-Command yt-dlp -ErrorAction SilentlyContinue
    if ($exe) {
        & $exe.Source @Args
        if ($LASTEXITCODE -ne 0) { throw "yt-dlp failed with exit code $LASTEXITCODE" }
        return
    }
    $py = Get-Command py -ErrorAction SilentlyContinue
    if (-not $py) { throw "yt-dlp was not found. Install it with: py -m pip install -U yt-dlp" }
    & $py.Source -m yt_dlp @Args
    if ($LASTEXITCODE -ne 0) { throw "python -m yt_dlp failed with exit code $LASTEXITCODE" }
}

if ($ListProfiles) {
    Show-BrowserProfiles $BrowserSpec
    exit 0
}

$parent = Split-Path -Parent $Output
if ($parent) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }
if (Test-Path -LiteralPath $Output) { Remove-Item -LiteralPath $Output -Force }

Write-Host "Exporting browser cookies. Treat the output file as a password/session secret."
Write-Host "BrowserSpec: $BrowserSpec"
Invoke-YtDlp @("--cookies-from-browser", $BrowserSpec, "--cookies", $Output)

if (-not (Test-Path -LiteralPath $Output)) { throw "yt-dlp did not create: $Output" }
$first = Get-Content -LiteralPath $Output -TotalCount 1
if ($first -ne "# Netscape HTTP Cookie File" -and $first -ne "# HTTP Cookie File") {
    throw "Unexpected cookie format. Expected a Netscape/HTTP Cookie File header."
}
$youtubeRows = (Get-Content -LiteralPath $Output | Where-Object { $_ -match '(^#HttpOnly_)?[^\t]*youtube\.com\t' }).Count
Write-Host "Cookie file created: $Output"
Write-Host "YouTube-domain rows: $youtubeRows"
Write-Host "No cookie values are printed. Upload this file to the server and delete temporary copies after installation."
