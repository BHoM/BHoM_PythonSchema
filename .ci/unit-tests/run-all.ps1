# Runs every stage end to end: build, C# tests (which also generate the Python), the py2cs drafts, the Roslyn round trip,
# the pytest suites and Pyright. Stops at the first failing stage.
#
#   .\run-all.ps1                 full run
#   .\run-all.ps1 -SkipPyright    skip the Pyright pass over the repository sources
#
# It never builds a BHoM repository for you: missing assemblies are reported by the preflight, and the real-type tests
# are ignored locally (they fail when the CI environment variable is "true").

param([switch]$SkipPyright)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$solution = Join-Path $root ".ci\generation\PythonSchemaGeneration.sln"
$output = Join-Path $PSScriptRoot "_output"
$python = Join-Path $root ".venv\Scripts\python.exe"
Set-Location $root

function Step($name, [scriptblock]$body) {
    Write-Host "`n=== $name" -ForegroundColor Cyan
    & $body
    if ($LASTEXITCODE -ne 0) { throw "Stage failed: $name (exit code $LASTEXITCODE)" }
}

# ---- preflight
Write-Host "=== Preflight" -ForegroundColor Cyan
$assemblies = Join-Path $env:ProgramData "BHoM\Assemblies"
$required = "BHoM", "BHoM_Engine", "Reflection_Engine", "JsonSchema_oM", "JsonSchema_Engine", "Quantities_oM",
            "Geometry_oM", "Structure_oM", "Graphics_oM", "Acoustic_oM", "Architecture_oM", "dKoP_oM"
$missing = $required | Where-Object { -not (Test-Path (Join-Path $assemblies "$_.dll")) }
if ($missing) {
    Write-Host "Missing from ${assemblies}: $($missing -join ', ')" -ForegroundColor Yellow
    Write-Host "Real-type tests will be ignored (CI=true makes them fail). Build the owning BHoM repos to install the dlls." -ForegroundColor Yellow
} else {
    Write-Host "All $($required.Count) required assemblies are installed."
}
if (-not (Test-Path $python)) { throw "No virtual environment: run  python -m venv .venv ; .venv\Scripts\python -m pip install -e '.[dev]'" }
$env:PYTHONPATH = Join-Path $root ".ci\generation"

# ---- C#
Step "dotnet build" { dotnet build $solution -c Release --nologo -v quiet }
Step "dotnet test (generates the fixture and spike Python)" { dotnet test $solution -c Release --no-build --nologo --filter "Category!=RoundTrip" }

# ---- Python to C# drafts and the round trip
foreach ($set in "fixtures", "spike") {
    $package = Join-Path $output "$set\bhom_schema"
    if (Test-Path $package) {
        Step "py2cs drafts ($set)" { & $python -m py2cs drafts --root $package --out (Join-Path $output "roundtrip\$set") }
    }
}
Step "dotnet test (Roslyn round trip)" { dotnet test $solution -c Release --no-build --nologo --filter "Category=RoundTrip" }

# ---- Python (separate sessions: the fixture and spike packages share assembly folder names such as BHoM)
Step "pytest py2cs" { & $python -m pytest ".ci/unit-tests/python/test_py2cs" -q }
Step "pytest generated fixtures" { & $python -m pytest ".ci/unit-tests/python/test_fixtures" -q }
Step "pytest generated spike types" { & $python -m pytest ".ci/unit-tests/python/test_spike" -q }
Step "pytest alignment and round trip" { & $python -m pytest ".ci/unit-tests/python/test_alignment" -q }

# ---- Pyright over the repository sources (the generated output is checked inside the pytest suites)
if (-not $SkipPyright) {
    Step "pyright" { & $python -m pyright }
}

Write-Host "`nAll stages passed." -ForegroundColor Green
