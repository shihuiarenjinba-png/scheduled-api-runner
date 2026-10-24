$ErrorActionPreference = 'Stop'

$sourceCommit = (& git -C $PSScriptRoot rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $sourceCommit -notmatch '^[0-9a-fA-F]{40}$') {
    throw 'Unable to resolve exact source commit for validation build.'
}

python -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw 'pip upgrade failed.' }
python -m pip install -r requirements-build.txt
if ($LASTEXITCODE -ne 0) { throw 'build dependency installation failed.' }

python -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw 'unit/UI language tests failed.' }

$stamp = [guid]::NewGuid().ToString("N")
$dest = Join-Path $PSScriptRoot ("dist-validation\\ScheduledApiRunner-" + $stamp)
$work = Join-Path $env:TEMP ("ScheduledApiRunner-work-" + $stamp)
$spec = Join-Path $env:TEMP ("ScheduledApiRunner-spec-" + $stamp)
$example = (Resolve-Path (Join-Path $PSScriptRoot "jobs.example.json")).Path
if (Test-Path -LiteralPath $dest) { throw "Validation output already exists" }

python -m PyInstaller --clean --noconfirm --onefile --windowed --name ScheduledApiRunner --distpath "$dest" --workpath "$work" --specpath "$spec" --add-data "$example;." desktop_app.py
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed.' }
$exePath = Join-Path $dest "ScheduledApiRunner.exe"
if (-not (Test-Path -LiteralPath $exePath -PathType Leaf)) { throw "Wrong EXE entrypoint: $exePath" }
$process = Start-Process -FilePath $exePath -ArgumentList "--self-test" -PassThru -Wait
if ($process.ExitCode -ne 0) { throw "Frozen EXE no-network self-test failed: $($process.ExitCode)" }
$sha = (Get-FileHash -LiteralPath $exePath -Algorithm SHA256).Hash.ToLowerInvariant()
$report = [ordered]@{
    exe = "ScheduledApiRunner.exe"
    source_entrypoint = "desktop_app.py"
    source_commit = $sourceCommit
    sha256 = $sha
    packaged_no_network_self_test = "PASS"
    interactive_windows_qa = $false
    microsoft_store_certified = $false
    signed = $false
    sale_approved = $false
}
$report | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $dest "validation-manifest.json") -Encoding UTF8
Write-Host "NON-SALES validation EXE: $exePath; SHA256: $sha"


Write-Host 'Built ScheduledApiRunner.exe after regression and language tests passed.'
Write-Host 'Before sale: complete SALES_RELEASE_CHECKLIST.md and controlled live-API Windows tests.'
