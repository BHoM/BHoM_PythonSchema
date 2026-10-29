# Clones the repositories to build (read only: nothing is ever pushed to them) into one folder, and records the commit of each.
#
#   Clone-Repositories.ps1 -List Included-repositories.txt [-Target .repos]
#
# Each repository comes from its develop branch, or main, or master. <Target>/commits.txt gets one "Owner/Name <commit>" line per repository,
# for the commit message of the generation, so anyone can reproduce it.
param(
  [Parameter(Mandatory = $true)][string]$List,
  [string]$Target = ".repos"
)

$ErrorActionPreference = "Stop"

$repositories = Get-Content $List | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne "" -and -not $_.StartsWith("#") } | Select-Object -Unique

New-Item -ItemType Directory -Force $Target | Out-Null
$commits = @()

foreach ($repository in $repositories) {
  $name = $repository.Split("/")[1]
  $folder = Join-Path $Target $name
  $cloned = $false

  foreach ($branch in "develop", "main", "master") {
    Write-Host "Cloning $repository ($branch)..."
    git clone "https://github.com/$repository.git" $folder --branch $branch --depth 1 --quiet 2>$null
    if ($LASTEXITCODE -eq 0) {
      $cloned = $true
      break
    }
  }

  if (-not $cloned) {
    throw "Could not clone $repository (tried develop, main and master)"
  }

  $commit = (git -C $folder rev-parse HEAD).Trim()
  Write-Host "  $repository at $commit"
  $commits += "$repository $commit"
}

$commits | Set-Content (Join-Path $Target "commits.txt")
