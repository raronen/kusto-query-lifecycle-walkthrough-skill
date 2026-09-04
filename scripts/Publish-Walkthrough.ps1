[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string] $ModelPath,

    [Parameter(Mandatory)]
    [string] $SourceWorkspace,

    [string] $PublisherPath,

    [string] $OutputPath,

    [ValidateRange(1, 600)]
    [int] $PublisherTimeoutSeconds = 60
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$scriptRoot = Split-Path -Parent $PSCommandPath
$renderer = Join-Path $scriptRoot 'render_walkthrough.py'
$arguments = @(
    $renderer,
    '--model', ([IO.Path]::GetFullPath($ModelPath)),
    '--source-workspace', ([IO.Path]::GetFullPath($SourceWorkspace))
)
if (-not [string]::IsNullOrWhiteSpace($OutputPath)) {
    $arguments += @('--output', ([IO.Path]::GetFullPath($OutputPath)))
}

$renderOutput = & python @arguments
if ($LASTEXITCODE -ne 0) {
    throw "Renderer failed with exit code $LASTEXITCODE."
}
$renderResult = $renderOutput | ConvertFrom-Json
$renderOk = $renderResult.ok
if ($renderOk -isnot [bool] -or -not $renderOk) {
    throw 'Renderer did not return exact boolean ok=true.'
}
if (-not (Test-Path -LiteralPath $renderResult.html_path -PathType Leaf)) {
    throw "Rendered HTML was not found at '$($renderResult.html_path)'."
}

$bookmarkStatus = 'skipped'
$bookmarkError = $null
$companionResult = $null
$driverPath = $null
$resultPath = $null
try {
    if ([string]::IsNullOrWhiteSpace($PublisherPath)) {
        $profileRoot = [Environment]::GetFolderPath([Environment+SpecialFolder]::UserProfile)
        if ([string]::IsNullOrWhiteSpace($profileRoot)) {
            throw 'Bookmark publisher path could not be resolved because the user profile is unavailable.'
        }
        $PublisherPath = Join-Path $profileRoot '.copilot\skills\bookmark\scripts\Publish-Bookmark.ps1'
    }
    if (-not (Test-Path -LiteralPath $PublisherPath -PathType Leaf)) {
        $bookmarkError = "Bookmark publisher was not found at '$PublisherPath'."
    }
    else {
        $driverPath = Join-Path ([IO.Path]::GetTempPath()) "kusto-bookmark-publisher-$([guid]::NewGuid().ToString('N')).ps1"
        $resultPath = Join-Path ([IO.Path]::GetTempPath()) "kusto-bookmark-result-$([guid]::NewGuid().ToString('N')).json"
        $driver = @'
$ErrorActionPreference = 'Stop'
try {
    $output = @(& $env:KUSTO_BOOKMARK_PUBLISHER `
        -HtmlPath $env:KUSTO_BOOKMARK_HTML `
        -Title $env:KUSTO_BOOKMARK_TITLE 3>&1 4>&1 5>&1 6>&1)
    $result = $output | Select-Object -Last 1
    if ($null -eq $result) {
        throw 'Bookmark publisher returned no result.'
    }
    $envelope = [pscustomobject]@{ ok = $true; result = $result; error = $null }
}
catch {
    $envelope = [pscustomobject]@{ ok = $false; result = $null; error = $_.Exception.Message }
}
[IO.File]::WriteAllText(
    $env:KUSTO_BOOKMARK_RESULT,
    ($envelope | ConvertTo-Json -Depth 20 -Compress),
    [Text.UTF8Encoding]::new($false))
'@
        [IO.File]::WriteAllText($driverPath, $driver, [Text.UTF8Encoding]::new($false))
        $startInfo = [Diagnostics.ProcessStartInfo]::new()
        $startInfo.FileName = (Get-Process -Id $PID).Path
        $startInfo.Arguments = "-NoLogo -NoProfile -NonInteractive -File `"$driverPath`""
        $startInfo.UseShellExecute = $false
        $startInfo.CreateNoWindow = $true
        $startInfo.RedirectStandardOutput = $true
        $startInfo.RedirectStandardError = $true
        $startInfo.EnvironmentVariables['KUSTO_BOOKMARK_PUBLISHER'] = [IO.Path]::GetFullPath($PublisherPath)
        $startInfo.EnvironmentVariables['KUSTO_BOOKMARK_HTML'] = $renderResult.html_path
        $startInfo.EnvironmentVariables['KUSTO_BOOKMARK_TITLE'] = $renderResult.title
        $startInfo.EnvironmentVariables['KUSTO_BOOKMARK_RESULT'] = $resultPath

        $process = [Diagnostics.Process]::new()
        $process.StartInfo = $startInfo
        if (-not $process.Start()) {
            throw 'Bookmark publisher process could not be started.'
        }
        $stdoutDrain = $process.StandardOutput.BaseStream.CopyToAsync([IO.Stream]::Null)
        $stderrDrain = $process.StandardError.BaseStream.CopyToAsync([IO.Stream]::Null)
        if (-not $process.WaitForExit($PublisherTimeoutSeconds * 1000)) {
            try {
                $process.Kill($true)
            }
            catch {
                $process.Kill()
            }
            [void]$process.WaitForExit(5000)
            throw "Bookmark publication timed out after $PublisherTimeoutSeconds seconds."
        }
        if ($process.ExitCode -ne 0) {
            throw "Bookmark publisher process exited with code $($process.ExitCode)."
        }
        if (-not (Test-Path -LiteralPath $resultPath -PathType Leaf)) {
            throw 'Bookmark publisher exited without a result.'
        }
        $publicationEnvelope = [IO.File]::ReadAllText($resultPath) | ConvertFrom-Json
        if ($publicationEnvelope.ok -isnot [bool] -or -not $publicationEnvelope.ok) {
            throw $publicationEnvelope.error
        }
        $publishResult = $publicationEnvelope.result
        $companionResult = $publishResult.CompanionResult
        $companionOk = $companionResult.ok
        if ($companionOk -is [bool] -and $companionOk) {
            $bookmarkStatus = 'published'
        }
        else {
            $bookmarkStatus = 'failed'
            $bookmarkError = 'Bookmark publication was not confirmed because CompanionResult.ok was not exact boolean true.'
        }
    }
}
catch {
    $bookmarkStatus = 'failed'
    $bookmarkError = $_.Exception.Message
}
finally {
    if ($null -ne $driverPath) {
        Remove-Item -LiteralPath $driverPath -Force -ErrorAction SilentlyContinue
    }
    if ($null -ne $resultPath) {
        Remove-Item -LiteralPath $resultPath -Force -ErrorAction SilentlyContinue
    }
}

[pscustomobject]@{
    Ok = $true
    HtmlPath = $renderResult.html_path
    EvidenceMode = $renderResult.evidence_mode
    PlanProvenance = $renderResult.plan_provenance
    Compliance = $renderResult.compliance
    BookmarkStatus = $bookmarkStatus
    BookmarkError = $bookmarkError
    DestinationPath = @('Favorites bar', 'Imported')
    CompanionResult = $companionResult
}
