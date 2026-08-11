param(
  [Parameter(Mandatory = $true)]
  [string]$DistributionZip
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$fixturePath = Join-Path $repoRoot "smoke/windows/ogr-smoke.geojson"
$templatePath = Join-Path $repoRoot "smoke/windows/ogr-smoke.hpl"

if (-not (Test-Path -LiteralPath $DistributionZip)) {
  throw "Distribution ZIP not found: $DistributionZip"
}
if (-not (Test-Path -LiteralPath $fixturePath)) {
  throw "OGR smoke fixture not found: $fixturePath"
}
if (-not (Test-Path -LiteralPath $templatePath)) {
  throw "OGR smoke pipeline template not found: $templatePath"
}

$workDir = Join-Path $env:RUNNER_TEMP "hop-windows-ogr-smoke"
$extractDir = Join-Path $workDir "distribution"
$nativeTempDir = Join-Path $workDir "native-tmp"
$pipelinePath = Join-Path $workDir "ogr-smoke.hpl"

Remove-Item -LiteralPath $workDir -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $extractDir -Force | Out-Null
New-Item -ItemType Directory -Path $nativeTempDir -Force | Out-Null

Write-Host "Extracting $DistributionZip"
Expand-Archive -LiteralPath $DistributionZip -DestinationPath $extractDir -Force

$hopRun = Get-ChildItem -LiteralPath $extractDir -Filter "hop-run.bat" -File -Recurse |
  Select-Object -First 1
if (-not $hopRun) {
  throw "hop-run.bat not found after extracting $DistributionZip"
}

$fixtureUriPath = (Resolve-Path -LiteralPath $fixturePath).Path.Replace("\", "/")
$escapedFixturePath = [System.Security.SecurityElement]::Escape($fixtureUriPath)
$template = Get-Content -LiteralPath $templatePath -Raw
if (-not $template.Contains("__OGR_SMOKE_FILE__")) {
  throw "Pipeline template does not contain __OGR_SMOKE_FILE__ placeholder"
}
$template.Replace("__OGR_SMOKE_FILE__", $escapedFixturePath) |
  Set-Content -LiteralPath $pipelinePath -Encoding utf8

$nativeTempUriPath = $nativeTempDir.Replace("\", "/")
$previousJavaToolOptions = $env:JAVA_TOOL_OPTIONS
$env:JAVA_TOOL_OPTIONS = "-Djava.io.tmpdir=$nativeTempUriPath"

function Write-NativeDiagnostics {
  Write-Host "Native extraction diagnostics:"
  Get-ChildItem -LiteralPath $nativeTempDir -Recurse -Force -ErrorAction SilentlyContinue |
    Select-Object FullName, Length |
    Format-Table -AutoSize |
    Out-String |
    Write-Host

  $projDll = Get-ChildItem -LiteralPath $nativeTempDir -Filter "proj_9.dll" -File -Recurse -ErrorAction SilentlyContinue |
    Select-Object -First 1
  if ($projDll) {
    $dumpbin = Get-Command dumpbin.exe -ErrorAction SilentlyContinue
    if ($dumpbin) {
      Write-Host "dumpbin /dependents $($projDll.FullName)"
      & $dumpbin.Source /dependents $projDll.FullName | Write-Host
    }
  }
}

Push-Location $hopRun.Directory.FullName
try {
  foreach ($attempt in 1..2) {
    $logPath = Join-Path $workDir "hop-run-$attempt.log"
    Write-Host "Running OGR smoke attempt $attempt with shared java.io.tmpdir=$nativeTempDir"

    $output = & $hopRun.FullName -r local -f $pipelinePath -l BASIC 2>&1
    $exitCode = $LASTEXITCODE
    $output | Tee-Object -FilePath $logPath | Write-Host

    if ($exitCode -ne 0) {
      Write-NativeDiagnostics
      throw "hop-run.bat failed on attempt $attempt with exit code $exitCode"
    }

    $logText = Get-Content -LiteralPath $logPath -Raw
    if ($logText -notmatch "OGR input\.0 - Finished processing .*W=1.*E=0") {
      Write-NativeDiagnostics
      throw "OGR input did not report exactly one written row with zero errors on attempt $attempt"
    }
  }
}
finally {
  Pop-Location
  $env:JAVA_TOOL_OPTIONS = $previousJavaToolOptions
}

Write-Host "Windows OGR end-to-end smoke passed twice."
