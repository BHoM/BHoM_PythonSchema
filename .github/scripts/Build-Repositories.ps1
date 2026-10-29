# Builds the cloned repositories in dependency order, with the same build.ps1 as the BHoM_JSONSchema weekly job.
#
#   Build-Repositories.ps1 -List Included-repositories.txt [-Extra BHoM/BHoM_Adapter] [-ReposRoot .repos] [-OrderOnly]
#
# The order comes from the dependencies.txt of each repository (lines like BHoM/BHoM), among the listed repositories only. Building a
# BHoM repository copies its assemblies to %ProgramData%\BHoM\Assemblies, where the next repository and the generator find them.
# With -OrderOnly the order is printed and nothing is built.
param(
  [Parameter(Mandatory = $true)][string]$List,
  [string[]]$Extra = @(),
  [string]$ReposRoot = ".repos",
  [switch]$OrderOnly
)

$ErrorActionPreference = "Stop"

$names = @(Get-Content $List | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne "" -and -not $_.StartsWith("#") }) + $Extra |
  ForEach-Object { $_.Split("/")[-1] } | Select-Object -Unique

$dependencies = @{}
foreach ($name in $names) {
  $dependencies[$name] = @()
  $file = Join-Path $ReposRoot "$name/dependencies.txt"
  if (Test-Path $file) {
    $dependencies[$name] = @(Get-Content $file | ForEach-Object { $_.Trim() } |
      Where-Object { $_ -ne "" -and -not $_.StartsWith("#") } |
      ForEach-Object { $_.Split("/")[-1] } |
      Where-Object { $names -contains $_ -and $_ -ne $name })
  }
}

$script:order = @()
$script:state = @{}

function Visit([string]$name) {
  if ($script:state[$name] -eq "done") { return }
  if ($script:state[$name] -eq "visiting") { throw "Circular dependency involving $name" }
  $script:state[$name] = "visiting"
  foreach ($dependency in $dependencies[$name]) { Visit $dependency }
  $script:state[$name] = "done"
  $script:order += $name
}

foreach ($name in $names) { Visit $name }

Write-Host "Build order: $($script:order -join ', ')"
if ($OrderOnly) { return }

$buildScript = Join-Path $PSScriptRoot "../workflows/build.ps1"
foreach ($name in $script:order) {
  Push-Location (Join-Path $ReposRoot $name)
  try {
    Write-Host "Building $name..."
    $solution = Get-ChildItem -Filter *.sln | Select-Object -First 1
    if ($solution) {
      & $buildScript -SolutionOrProjectPath $solution.FullName
    } else {
      foreach ($project in Get-ChildItem -Recurse -Filter *.csproj) {
        & $buildScript -SolutionOrProjectPath $project.FullName
      }
    }
  } finally {
    Pop-Location
  }
}
