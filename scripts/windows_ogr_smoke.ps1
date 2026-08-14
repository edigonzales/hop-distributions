param(
  [Parameter(Mandatory = $true)]
  [string]$DistributionZip
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$fixturePath = Join-Path $repoRoot "smoke/windows/ogr-smoke.geojson"
$templatePath = Join-Path $repoRoot "smoke/windows/ogr-smoke.hpl"
$curveGeneratorPath = Join-Path $repoRoot "smoke/windows/create_curve_gpkg.py"
$curveTemplatePath = Join-Path $repoRoot "smoke/windows/curve-preview-smoke.hpl"

if (-not (Test-Path -LiteralPath $DistributionZip)) {
  throw "Distribution ZIP not found: $DistributionZip"
}
if (-not (Test-Path -LiteralPath $fixturePath)) {
  throw "OGR smoke fixture not found: $fixturePath"
}
if (-not (Test-Path -LiteralPath $templatePath)) {
  throw "OGR smoke pipeline template not found: $templatePath"
}
if (-not (Test-Path -LiteralPath $curveGeneratorPath)) {
  throw "Curve GeoPackage generator not found: $curveGeneratorPath"
}
if (-not (Test-Path -LiteralPath $curveTemplatePath)) {
  throw "Curve preview pipeline template not found: $curveTemplatePath"
}

$workDir = Join-Path $env:RUNNER_TEMP "hop-windows-ogr-smoke"
$extractDir = Join-Path $workDir "distribution"
$nativeTempDir = Join-Path $workDir "native-tmp"
$pipelinePath = Join-Path $workDir "ogr-smoke.hpl"
$curveGpkgPath = Join-Path $workDir "curve-preview.gpkg"
$curvePipelinePath = Join-Path $workDir "curve-preview-smoke.hpl"

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

Write-Host "Generating SQL/MM CURVEPOLYGON GeoPackage fixture"
& python $curveGeneratorPath $curveGpkgPath
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $curveGpkgPath)) {
  throw "Failed to create CurvePolygon GeoPackage fixture"
}

$curveGpkgUriPath = (Resolve-Path -LiteralPath $curveGpkgPath).Path.Replace("\", "/")
$escapedCurveGpkgPath = [System.Security.SecurityElement]::Escape($curveGpkgUriPath)
$curveTemplate = Get-Content -LiteralPath $curveTemplatePath -Raw
if (-not $curveTemplate.Contains("__CURVE_GPKG_FILE__")) {
  throw "Curve pipeline template does not contain __CURVE_GPKG_FILE__ placeholder"
}
$curveTemplate.Replace("__CURVE_GPKG_FILE__", $escapedCurveGpkgPath) |
  Set-Content -LiteralPath $curvePipelinePath -Encoding utf8

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
    Write-Host "Running OGR -> Geometry Calculator smoke attempt $attempt with shared java.io.tmpdir=$nativeTempDir"

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
    if ($logText -notmatch "Geometry Calculator\.0 - Finished processing .*W=1.*E=0") {
      Write-NativeDiagnostics
      throw "Geometry Calculator did not process the OGR geometry with one written row and zero errors on attempt $attempt"
    }
    if ($logText -notmatch "Output\.0 - Finished processing .*R=1.*E=0") {
      Write-NativeDiagnostics
      throw "Output did not receive the geometry calculator row on attempt $attempt"
    }
  }

  $curveLogPath = Join-Path $workDir "curve-preview.log"
  Write-Host "Running CurvePolygon OGR -> ValueMetaGeometry string rendering smoke"
  $curveOutput = & $hopRun.FullName -r local -f $curvePipelinePath -l BASIC 2>&1
  $curveExitCode = $LASTEXITCODE
  $curveOutput | Tee-Object -FilePath $curveLogPath | Write-Host

  if ($curveExitCode -ne 0) {
    Write-NativeDiagnostics
    throw "CurvePolygon preview pipeline failed with exit code $curveExitCode"
  }

  $curveLogText = Get-Content -LiteralPath $curveLogPath -Raw
  if ($curveLogText -notmatch "OGR input\.0 - Finished processing .*W=1.*E=0") {
    throw "CurvePolygon OGR input did not report one written row with zero errors"
  }
  if ($curveLogText -notmatch "CURVE_PREVIEW_STRING") {
    throw "Write To Log did not execute the CurvePolygon string-rendering path"
  }
  if ($curveLogText -notmatch "geometry\s*=\s*(?:SRID=2056;)?CURVEPOLYGON\s*\(") {
    throw "CurvePolygon was not rendered as CURVEPOLYGON in the installed distribution"
  }
  if ($curveLogText -notmatch "CIRCULARSTRING\s*\(") {
    throw "CurvePolygon string output did not preserve its CIRCULARSTRING ring"
  }
  if ($curveLogText -match "geometry\s*=\s*(?:SRID=2056;)?POLYGON\s*\(") {
    throw "CurvePolygon regressed to a linear POLYGON preview string"
  }
}
finally {
  Pop-Location
  $env:JAVA_TOOL_OPTIONS = $previousJavaToolOptions
}

Write-Host "Windows geometry runtime end-to-end smokes passed: OGR -> Geometry Calculator twice and CurvePolygon preview rendering."
