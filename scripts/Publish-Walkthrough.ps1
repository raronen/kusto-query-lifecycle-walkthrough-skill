[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string] $ModelPath,

    [Parameter(Mandatory)]
    [string] $SourceWorkspace,

    [string] $PublisherPath = (Join-Path $env:USERPROFILE '.copilot\skills\bookmark\scripts\Publish-Bookmark.ps1')
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
if (-not (Test-Path -LiteralPath $PublisherPath -PathType Leaf)) {
    throw "Bookmark publisher was not found at '$PublisherPath'."
}

$publishResult = & $PublisherPath -HtmlPath $renderResult.html_path -Title $renderResult.title
$companionOk = $publishResult.CompanionResult.ok
if ($companionOk -isnot [bool] -or -not $companionOk) {
    throw 'Publication failed because CompanionResult.ok was not exact boolean true.'
}

[pscustomobject]@{
    HtmlPath = $renderResult.html_path
    EvidenceMode = $renderResult.evidence_mode
    DestinationPath = @('Favorites bar', 'Imported')
    CompanionResult = $publishResult.CompanionResult
}
