# build.ps1
param(
  [string]$SolutionOrProjectPath
)

function Test-IsSdkProject {
  param([string]$csprojPath)
  try {
    [xml]$xml = Get-Content -LiteralPath $csprojPath
  } catch { return $false }
  # SDK-style has <Project Sdk="..."> on the root element
  return $xml.Project -and $xml.Project.Sdk
}

function Get-SolutionProjects {
  param([string]$slnPath)
  $root = Split-Path -Parent $slnPath
  Select-String -Path $slnPath -Pattern 'Project\(".*"\)\s*=\s*".*?",\s*"(.*?)",\s*".*?"' |
    ForEach-Object {
      $rel = $_.Matches[0].Groups[1].Value
      if ($rel -and $rel.EndsWith(".csproj", [StringComparison]::OrdinalIgnoreCase)) {
        Join-Path $root $rel
      }
    } | Where-Object { Test-Path $_ }
}

function Classify-Build {
  param([string]$path)

  if ($path.EndsWith(".sln")) {
    $projects = Get-SolutionProjects $path
    if (-not $projects) { return "none" }

    $hasPackagesConfig = $projects | ForEach-Object {
      $pkg = Join-Path (Split-Path -Parent $_) "packages.config"
      Test-Path $pkg
    } | Where-Object { $_ } | Measure-Object | Select-Object -ExpandProperty Count

    if ($hasPackagesConfig -gt 0) { return "legacy" }

    $allSdk = $projects | ForEach-Object { Test-IsSdkProject $_ } |
      Where-Object { -not $_ } | Measure-Object | Select-Object -ExpandProperty Count
    return ($allSdk -eq 0) ? "sdk" : "legacy"
  }
  elseif ($path.EndsWith(".csproj")) {
    $pkg = Join-Path (Split-Path -Parent $path) "packages.config"
    if (Test-Path $pkg) { return "legacy" }
    return (Test-IsSdkProject $path) ? "sdk" : "legacy"
  }
  else {
    return "none"
  }
}

$path = Resolve-Path $SolutionOrProjectPath
$kind = Classify-Build $path
Write-Host "Detected build kind: $kind"

switch ($kind) {
  "sdk" {
    Write-Host "Using dotnet restore/build"
    dotnet restore "$path"
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    dotnet build "$path" --configuration Release --no-restore --verbosity minimal
    exit $LASTEXITCODE
  }
  "legacy" {
    Write-Host "Using NuGet + MSBuild (/restore)"
    nuget restore "$path" -NonInteractive
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    msbuild "$path" /restore /m /p:Configuration=Release /p:Platform="Any CPU" /verbosity:minimal /nologo
    exit $LASTEXITCODE
  }
  default {
    Write-Host "No solution or project found or unrecognized format."
    exit 0
  }
}
