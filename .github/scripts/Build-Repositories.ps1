# Builds the listed repositories in dependency order, with the same build.ps1 as the BHoM_JSONSchema weekly job.
#
#   Build-Repositories.ps1 -List Included-repositories.txt [-ReposRoot .repos] [-OrderOnly]
#   Build-Repositories.ps1 -List Included-repositories.txt -Plan [-PlanFile plan.json] [-CacheFolder .build-cache]
#   Build-Repositories.ps1 -List Included-repositories.txt -CacheFolder .build-cache [-PlanFile plan.json] [-NoCache]
#
# Without -Plan or -CacheFolder it builds the clones already in <ReposRoot> (see Clone-Repositories.ps1). The order comes from the
# dependencies.txt of each repository (lines like BHoM/BHoM), among the listed repositories only. Building a BHoM repository copies its
# assemblies to %ProgramData%\BHoM\Assemblies, where the next repository and the generator find them. With -OrderOnly the order is printed
# and nothing is built.
#
# -Plan reads the current commit of each repository (develop, else main, else master) and its dependencies.txt at that commit, without
# cloning, and gives each repository a key made from its commit, the keys of its dependencies and the build tools. It prints the plan,
# writes it to -PlanFile, and stops.
#
# -CacheFolder runs the plan (read from -PlanFile when that file exists). A repository whose entry <Name>-<key> is in the folder is copied
# from it; any other is cloned at the planned commit and built, and the files its build added or changed under %ProgramData%\BHoM become
# its entry. Entries of other keys are deleted, and <ReposRoot>/commits.txt is written. -NoCache builds every repository and leaves the
# folder alone.
param(
  [Parameter(Mandatory = $true)][string]$List,
  [string]$ReposRoot = ".repos",
  [switch]$OrderOnly,
  [switch]$Plan,
  [string]$PlanFile,
  [string]$CacheFolder,
  [switch]$NoCache,
  # For tests: "Owner/Name <commit>" lines instead of git ls-remote
  [string]$CommitsFile,
  # For tests: <Name>/dependencies.txt files instead of the ones on GitHub
  [string]$DependenciesRoot,
  # The build tools in the keys; read from msbuild and dotnet when not given
  [string]$ToolsVersion,
  # The OS of the runner that builds, so that a plan made on ubuntu gives the keys of the Windows build
  [string]$OS = $(if ($env:RUNNER_OS) { $env:RUNNER_OS } else { "Windows" }),
  [string]$BHoMRoot = $(if ($env:ProgramData) { Join-Path $env:ProgramData "BHoM" } else { "" }),
  # Bump to throw every cache away
  [string]$Salt = "v1"
)

$ErrorActionPreference = "Stop"
$buildScript = Join-Path $PSScriptRoot "../workflows/build.ps1"

function Read-Lines($lines) {
  @($lines | ForEach-Object { "$_".Trim() } | Where-Object { $_ -ne "" -and -not $_.StartsWith("#") })
}

function Get-Hash([string]$text) {
  $sha = [System.Security.Cryptography.SHA256]::Create()
  [System.BitConverter]::ToString($sha.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($text))).Replace("-", "").ToLower()
}

function Invoke-WithRetry([scriptblock]$body, [string]$what) {
  for ($attempt = 1; ; $attempt++) {
    try {
      return & $body
    } catch {
      if ($attempt -ge 3) { throw "$what failed after 3 attempts: $_" }

      Write-Host "$what failed, retrying: $_"
      Start-Sleep -Seconds (5 * $attempt)
    }
  }
}

# The listed dependencies of one repository, by name, among the listed repositories only
function Select-Dependencies([string]$name, $lines) {
  @(Read-Lines $lines | ForEach-Object { $_.Split("/")[-1] } | Where-Object { $script:names -contains $_ -and $_ -ne $name } | Select-Object -Unique)
}

function Get-Order($dependencies) {
  $script:order = @()
  $script:state = @{}
  foreach ($name in $script:names) { Visit $name $dependencies }

  $script:order
}

function Visit([string]$name, $dependencies) {
  if ($script:state[$name] -eq "done") { return }
  if ($script:state[$name] -eq "visiting") { throw "Circular dependency involving $name" }

  $script:state[$name] = "visiting"
  foreach ($dependency in $dependencies[$name]) { Visit $dependency $dependencies }

  $script:state[$name] = "done"
  $script:order += $name
}

function Get-Commit([string]$repository) {
  $heads = Invoke-WithRetry {
    $found = git ls-remote --heads "https://github.com/$repository.git" develop main master
    if ($LASTEXITCODE -ne 0) { throw "git ls-remote exited with $LASTEXITCODE" }

    $found
  } "Reading the branches of $repository"

  foreach ($branch in "develop", "main", "master") {
    $line = @($heads | Where-Object { $_ -match "\srefs/heads/$branch$" }) | Select-Object -First 1
    if ($line) { return ($line -split "\s+")[0] }
  }

  throw "Could not find a develop, main or master branch of $repository"
}

function Get-DependencyLines([string]$repository, [string]$commit) {
  if ($DependenciesRoot) {
    $file = Join-Path $DependenciesRoot "$($repository.Split('/')[-1])/dependencies.txt"
    if (Test-Path $file) { return Get-Content $file }

    return @()
  }

  $url = "https://raw.githubusercontent.com/$repository/$commit/dependencies.txt"
  Invoke-WithRetry {
    try {
      (Invoke-WebRequest $url -UseBasicParsing).Content -split "`r?`n"
    } catch {
      $status = 0
      if ($_.Exception.Response) { $status = [int]$_.Exception.Response.StatusCode }

      # A repository without the file has no dependencies
      if ($status -ne 404) { throw }

      @()
    }
  } "Reading dependencies.txt of $repository"
}

function Get-ToolsVersion {
  $versions = @()
  if (Get-Command msbuild -ErrorAction SilentlyContinue) { $versions += "msbuild " + "$(msbuild -nologo -version | Select-Object -Last 1)".Trim() }

  if (Get-Command dotnet -ErrorAction SilentlyContinue) { $versions += "dotnet " + "$(dotnet --version)".Trim() }

  if ($versions.Count -eq 0) { return "none" }

  $versions -join ", "
}

# Hosted runners in the middle of an image rollout differ in patch versions, so only MSBuild major.minor and the SDK feature band count
function Get-ToolsName([string]$tools) {
  $tools = $tools -replace "msbuild (\d+\.\d+)[\d.]*", 'msbuild $1'
  $tools -replace "dotnet (\d+\.\d+\.\d)\d*[^\s,]*", 'dotnet $1xx'
}

function New-BuildPlan {
  $commits = @{}
  if ($CommitsFile) {
    foreach ($line in (Read-Lines (Get-Content $CommitsFile))) {
      $parts = $line -split "\s+"
      $commits[$parts[0]] = $parts[1]
    }
  }

  foreach ($repository in $script:repositories) {
    if (-not $commits[$repository]) { $commits[$repository] = Get-Commit $repository }
  }

  $dependencies = @{}
  foreach ($repository in $script:repositories) {
    $name = $repository.Split("/")[-1]
    $dependencies[$name] = @(Select-Dependencies $name (Get-DependencyLines $repository $commits[$repository]))
  }

  $tools = $ToolsVersion
  if (-not $tools) { $tools = Get-ToolsVersion }

  $tools = Get-ToolsName $tools

  # Line endings depend on the checkout, so they are not part of the hash
  $toolsHash = Get-Hash "$tools|$((Get-Content $buildScript -Raw).Replace("`r`n", "`n"))"

  # The source key is the plan's key without the tools, so that ubuntu can find the state of a Windows build
  $sourceKeys = @{}
  $entries = @()
  foreach ($name in (Get-Order $dependencies)) {
    $repository = $script:fullNames[$name]
    $dependencyKeys = @($dependencies[$name] | ForEach-Object { $sourceKeys[$_] } | Sort-Object)
    $sourceKeys[$name] = Get-Hash ((@($Salt, $OS, $repository, $commits[$repository]) + $dependencyKeys) -join "|")
    $key = Get-Hash "$($sourceKeys[$name])|$toolsHash"
    $entries += [pscustomobject]@{
      repository   = $repository
      name         = $name
      commit       = $commits[$repository]
      dependencies = @($dependencies[$name])
      key          = $key
      entry        = "$name-$($key.Substring(0, 16))"
    }
  }

  $state = Get-Hash ((@($sourceKeys.Values) | Sort-Object) -join "|")
  $prefix = "bhom-build-cache-$Salt-$OS-"
  [pscustomobject]@{
    salt         = $Salt
    os           = $OS
    tools        = $tools
    cacheKey     = "$prefix$($state.Substring(0, 16))-$($toolsHash.Substring(0, 16))"
    cachePrefix  = $prefix
    statePrefix  = "$prefix$($state.Substring(0, 16))-"
    repositories = $entries
  }
}

function Set-StepOutput([string]$name, [string]$value) {
  if ($env:GITHUB_OUTPUT) { Add-Content -Path $env:GITHUB_OUTPUT -Value "$name=$value" }
}

function Build-Repository([string]$name, [string]$folder) {
  Push-Location $folder
  try {
    Write-Host "Building $name..."
    $solution = Get-ChildItem -Filter *.sln | Select-Object -First 1
    $paths = if ($solution) { @($solution.FullName) } else { @(Get-ChildItem -Recurse -Filter *.csproj | ForEach-Object { $_.FullName }) }
    foreach ($path in $paths) {
      & $buildScript -SolutionOrProjectPath $path
      if ($LASTEXITCODE -ne 0) { throw "Building $name failed (exit code $LASTEXITCODE)" }
    }
  } finally {
    Pop-Location
  }
}

# Clones only the planned commit, so that a push during the run cannot make the build differ from its key
function Get-Clone([string]$repository, [string]$commit, [string]$folder) {
  if (-not (Test-Path (Join-Path $folder ".git"))) {
    git init --quiet $folder
    if ($LASTEXITCODE -ne 0) { throw "git init $folder failed" }
  }

  Write-Host "Cloning $repository at $commit..."
  Invoke-WithRetry {
    git -C $folder fetch --depth 1 --quiet "https://github.com/$repository.git" $commit
    if ($LASTEXITCODE -ne 0) { throw "git fetch exited with $LASTEXITCODE" }
  } "Fetching $repository"

  git -C $folder checkout --quiet --detach FETCH_HEAD
  if ($LASTEXITCODE -ne 0) { throw "Could not check out $repository at $commit" }
}

# Relative path to "size|last write time" of every file under the folder
function Get-Snapshot([string]$root) {
  $snapshot = @{}
  $length = (Get-Item $root).FullName.TrimEnd("\", "/").Length + 1
  foreach ($file in (Get-ChildItem $root -Recurse -File -Force)) {
    $snapshot[$file.FullName.Substring($length)] = "$($file.Length)|$($file.LastWriteTimeUtc.Ticks)"
  }

  $snapshot
}

function Copy-Folder([string]$source, [string]$target) {
  robocopy $source $target /E /COPY:DAT /R:2 /W:1 /NFL /NDL /NJH /NJS /NP | Out-Null
  if ($LASTEXITCODE -ge 8) { throw "Copying $source to $target failed (robocopy exit code $LASTEXITCODE)" }

  $global:LASTEXITCODE = 0
}

$script:repositories = @(Read-Lines (Get-Content $List) | Select-Object -Unique)
$script:names = @($script:repositories | ForEach-Object { $_.Split("/")[-1] })
$script:fullNames = @{}
foreach ($repository in $script:repositories) { $script:fullNames[$repository.Split("/")[-1]] = $repository }

if (-not $Plan -and -not $CacheFolder) {
  $dependencies = @{}
  foreach ($name in $script:names) {
    $dependencies[$name] = @()
    $file = Join-Path $ReposRoot "$name/dependencies.txt"
    if (Test-Path $file) { $dependencies[$name] = @(Select-Dependencies $name (Get-Content $file)) }
  }

  $order = Get-Order $dependencies
  Write-Host "Build order: $($order -join ', ')"
  if ($OrderOnly) { return }

  foreach ($name in $order) { Build-Repository $name (Join-Path $ReposRoot $name) }

  return
}

if (-not $Plan -and $PlanFile -and (Test-Path $PlanFile)) {
  $buildPlan = Get-Content $PlanFile -Raw | ConvertFrom-Json
} else {
  $buildPlan = New-BuildPlan
}

$useCache = $CacheFolder -and -not $NoCache
$buildPlan.repositories | ForEach-Object {
  $cache = if (-not $CacheFolder) { "-" } elseif (-not $useCache) { "ignored" } elseif (Test-Path (Join-Path $CacheFolder $_.entry)) { "hit" } else { "miss" }
  [pscustomobject]@{ Repository = $_.repository; Commit = $_.commit.Substring(0, 10); Entry = $_.entry; Cache = $cache }
} | Format-Table -AutoSize | Out-String | Write-Host
Write-Host "Cache key: $($buildPlan.cacheKey) (tools: $($buildPlan.tools))"
if ($env:ImageOS) { Write-Host "Runner image: $env:ImageOS $env:ImageVersion" }


if ($Plan) {
  if ($PlanFile) { $buildPlan | ConvertTo-Json -Depth 5 | Set-Content $PlanFile -Encoding utf8 }

  Set-StepOutput "key" $buildPlan.cacheKey
  Set-StepOutput "prefix" $buildPlan.cachePrefix
  Set-StepOutput "state-prefix" $buildPlan.statePrefix
  return
}

# The empty folders that a build creates next to the assemblies
foreach ($folder in "Assemblies", "Datasets", "Upgrades", "Settings", "Developer") {
  New-Item -ItemType Directory -Force (Join-Path $BHoMRoot $folder) | Out-Null
}

New-Item -ItemType Directory -Force $ReposRoot | Out-Null
if ($useCache) { New-Item -ItemType Directory -Force $CacheFolder | Out-Null }

$built = @()
foreach ($repository in $buildPlan.repositories) {
  $entryFolder = Join-Path $CacheFolder $repository.entry
  if ($useCache -and (Test-Path $entryFolder)) {
    Write-Host "Restoring $($repository.name) from the cache..."
    Copy-Folder $entryFolder $BHoMRoot
    continue
  }

  $clone = Join-Path $ReposRoot $repository.name
  Get-Clone $repository.repository $repository.commit $clone
  $before = Get-Snapshot $BHoMRoot
  Build-Repository $repository.name $clone
  $built += $repository.name
  if (-not $useCache) { continue }

  # Comparing size and time is enough: a build writes its files anew
  $after = Get-Snapshot $BHoMRoot
  New-Item -ItemType Directory -Force $entryFolder | Out-Null
  foreach ($path in $after.Keys) {
    if ($before[$path] -eq $after[$path]) { continue }

    $target = Join-Path $entryFolder $path
    New-Item -ItemType Directory -Force (Split-Path -Parent $target) | Out-Null
    Copy-Item -LiteralPath (Join-Path $BHoMRoot $path) -Destination $target
  }
}

# Only the current heads can be needed again, so the folder never holds more than one entry per repository
if ($useCache) {
  $kept = @($buildPlan.repositories | ForEach-Object { $_.entry })
  Get-ChildItem $CacheFolder -Directory | Where-Object { $kept -notcontains $_.Name } | ForEach-Object {
    Write-Host "Deleting the old entry $($_.Name)"
    Remove-Item -LiteralPath $_.FullName -Recurse -Force
  }
}

$buildPlan.repositories | ForEach-Object { "$($_.repository) $($_.commit)" } | Set-Content (Join-Path $ReposRoot "commits.txt")
Write-Host "Built: $(if ($built) { $built -join ', ' } else { 'nothing' })"
Set-StepOutput "built" ($built -join ",")
Set-StepOutput "added" $(if ($useCache) { $built -join "," } else { "" })
