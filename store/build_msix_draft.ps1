# Windows Store MSIX draft builder — NEVER publish this candidate directly.
param(
    [Parameter(Mandatory=$true)][string]$ExePath,
    [Parameter(Mandatory=$true)][string]$OutputDirectory
)
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

$identityPath = Join-Path $PSScriptRoot "partner-center-identity.json"
if (-not (Test-Path -LiteralPath $identityPath -PathType Leaf)) {
    throw "Canonical Partner Center identity file is missing: $identityPath"
}
$identity = Get-Content -LiteralPath $identityPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($identity.schema_version -ne 1 -or
    $identity.store_id -cne "9PND0HG61XD6" -or
    $identity.identity_name -cne "OkinawaDesktopTools.ScheduledAPIRunner" -or
    $identity.publisher -cne "CN=46263F21-A700-41DB-8C9B-114C22FB82FC" -or
    $identity.publisher_display_name -cne "Okinawa Desktop Tools" -or
    $identity.package_family_name -cne "OkinawaDesktopTools.ScheduledAPIRunner_j8yefg9jgfh58" -or
    $identity.submission_allowed -ne $false -or
    $identity.partner_center_rechecked -isnot [bool]) {
    throw "Canonical Partner Center identity/approval mismatch: abort"
}

$versionTool = Join-Path $PSScriptRoot "msix_version.py"
if (-not (Test-Path -LiteralPath $versionTool -PathType Leaf)) {
    throw "MSIX version validator is missing: $versionTool"
}
$versionOutput = & python $versionTool --json
if ($LASTEXITCODE -ne 0) {
    throw "MSIX version configuration validation failed; no fallback to internal version is permitted."
}
try {
    $versionConfig = ($versionOutput -join [Environment]::NewLine) | ConvertFrom-Json
} catch {
    throw "MSIX version validator returned invalid JSON: $($_.Exception.Message)"
}
$Version = [string]$versionConfig.msix_package_version
if ([string]::IsNullOrWhiteSpace($Version)) {
    throw "Explicit msix_package_version is missing; refusing to build."
}

$exe = if ([IO.Path]::IsPathRooted($ExePath)) { $ExePath } else { Join-Path $repoRoot $ExePath }
if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) { throw "Missing EXE: $exe" }
$out = if ([IO.Path]::IsPathRooted($OutputDirectory)) { $OutputDirectory } else { Join-Path $repoRoot $OutputDirectory }
if (Test-Path -LiteralPath $out) { throw "Output already exists: $out" }
New-Item -ItemType Directory -Path $out | Out-Null
$out = (Resolve-Path $out).Path
$stage = Join-Path $out "msix-stage"
$unpack = Join-Path $out "msix-roundtrip"
New-Item -ItemType Directory -Path (Join-Path $stage "Assets") -Force | Out-Null
Copy-Item -LiteralPath $exe -Destination (Join-Path $stage "ScheduledApiRunner.exe")
$manifestText = Get-Content -LiteralPath (Join-Path $PSScriptRoot "AppxManifest.template.xml") -Raw -Encoding UTF8
$manifestText = $manifestText.Replace("__PACKAGE_IDENTITY_NAME__", [string]$identity.identity_name).Replace(
    "__PUBLISHER__", [string]$identity.publisher).Replace(
    "__PUBLISHER_DISPLAY_NAME__", [string]$identity.publisher_display_name).Replace("__VERSION__", $Version)
if ($manifestText -match '__[A-Z_]+__') { throw "Unresolved manifest template placeholder" }
$manifestPath = Join-Path $stage "AppxManifest.xml"
[IO.File]::WriteAllText($manifestPath,$manifestText,[Text.UTF8Encoding]::new($false))

# Temporary technical logos. Replace with owner-approved commercial artwork.
Add-Type -AssemblyName System.Drawing
foreach ($size in @(44,50,150)) {
    $name = switch ($size) { 44 { "Square44x44Logo.png" }; 50 { "StoreLogo.png" }; 150 { "Square150x150Logo.png" } }
    $bitmap = [Drawing.Bitmap]::new($size,$size)
    $graphics = [Drawing.Graphics]::FromImage($bitmap)
    try {
        $graphics.Clear([Drawing.Color]::FromArgb(18,42,66))
        $font = [Drawing.Font]::new("Segoe UI",[single]($size*0.32),[Drawing.FontStyle]::Bold,[Drawing.GraphicsUnit]::Pixel)
        $brush = [Drawing.SolidBrush]::new([Drawing.Color]::White)
        $format = [Drawing.StringFormat]::new()
        try {
            $format.Alignment = [Drawing.StringAlignment]::Center
            $format.LineAlignment = [Drawing.StringAlignment]::Center
            $graphics.DrawString("SA",$font,$brush,[Drawing.RectangleF]::new(0,0,[single]$size,[single]$size),$format)
            $bitmap.Save((Join-Path $stage ("Assets\"+$name)),[Drawing.Imaging.ImageFormat]::Png)
        } finally { $format.Dispose();$brush.Dispose();$font.Dispose() }
    } finally { $graphics.Dispose();$bitmap.Dispose() }
}

function Assert-Manifest([string]$Path) {
    [xml]$xml = Get-Content -LiteralPath $Path -Raw -Encoding UTF8
    $ns = [Xml.XmlNamespaceManager]::new($xml.NameTable)
    $ns.AddNamespace("f","http://schemas.microsoft.com/appx/manifest/foundation/windows10")
    $element = $xml.SelectSingleNode("/f:Package/f:Identity",$ns)
    if ($null -eq $element -or $element.Name -cne [string]$identity.identity_name -or
        $element.Publisher -cne [string]$identity.publisher -or $element.Version -cne $Version -or
        $element.ProcessorArchitecture -cne "x64") { throw "Manifest Identity does not match Partner Center" }
    $app = $xml.SelectSingleNode("/f:Package/f:Applications/f:Application",$ns)
    if ($null -eq $app -or $app.Executable -cne "ScheduledApiRunner.exe" -or
        $app.GetAttribute("RuntimeBehavior","http://schemas.microsoft.com/appx/manifest/uap/windows10/10") -cne "packagedClassicApp" -or
        $app.GetAttribute("TrustLevel","http://schemas.microsoft.com/appx/manifest/uap/windows10/10") -cne "mediumIL") {
        throw "MSIX full-trust application entry is invalid"
    }
    if (-not $xml.SelectSingleNode("/f:Package/f:Capabilities/*[local-name()='Capability' and @Name='runFullTrust']",$ns)) {
        throw "Missing full-trust capability"
    }
}
Assert-Manifest $manifestPath
$kitBase = [Environment]::GetEnvironmentVariable("ProgramFiles(x86)")
$kit = Join-Path $kitBase "Windows Kits\10\bin"
$makeappx = Get-ChildItem -LiteralPath $kit -Recurse -Filter MakeAppx.exe -File -ErrorAction SilentlyContinue |
    Where-Object { $_.DirectoryName -match '\\x64$' } | Sort-Object FullName -Descending | Select-Object -First 1
if ($null -eq $makeappx) { throw "x64 MakeAppx.exe not installed" }
$msixName = "ScheduledApiRunner_$($Version)_x64_StoreDraft_UNSIGNED.msix"
$msix = Join-Path $out $msixName
& $makeappx.FullName pack /v /h SHA256 /d $stage /p $msix
if ($LASTEXITCODE -ne 0) { throw "MakeAppx pack FAILED: $LASTEXITCODE" }
New-Item -ItemType Directory -Path $unpack | Out-Null
& $makeappx.FullName unpack /p $msix /d $unpack
if ($LASTEXITCODE -ne 0) { throw "MakeAppx unpack FAILED: $LASTEXITCODE" }
Assert-Manifest (Join-Path $unpack "AppxManifest.xml")
$sourceSha = (Get-FileHash -Algorithm SHA256 -LiteralPath $exe).Hash.ToLowerInvariant()
$unpackedSha = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $unpack "ScheduledApiRunner.exe")).Hash.ToLowerInvariant()
if ($sourceSha -cne $unpackedSha) { throw "MSIX EXE hash changed after pack/unpack" }
$packageSha = (Get-FileHash -Algorithm SHA256 -LiteralPath $msix).Hash.ToLowerInvariant()
$report = [ordered]@{
    store_id = [string]$identity.store_id; identity_name = [string]$identity.identity_name
    identity_publisher = [string]$identity.publisher; msix_file = $msixName; msix_version = $Version
    identity_record_source = [string]$identity.evidence
    partner_center_rechecked = [bool]$identity.partner_center_rechecked
    internal_app_version = $versionConfig.internal_app_version
    msix_package_version_status = [string]$versionConfig.msix_package_version_status
    previous_store_accepted_version = $versionConfig.previous_store_accepted_version
    store_version_history_verified = [bool]$versionConfig.store_version_history_verified
    source_exe_sha256 = $sourceSha; unpacked_exe_sha256 = $unpackedSha; msix_sha256 = $packageSha
    manifest_identity_verified = $true; makeappx_pack_unpack = "PASS"; signed = $false
    approved_logo = $false; manual_windows_acceptance = $false; store_submission_approved = $false; sale_approved = $false; public_release_approved = $false
}
$report | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $out "msix_validation.json") -Encoding UTF8
"$packageSha  $msixName" | Set-Content -LiteralPath (Join-Path $out "msix.sha256.txt") -Encoding ASCII
Write-Host "Validated UNSIGNED draft MSIX: $msix"
Write-Warning "Technical review only: temporary icons, unsigned, not approved for upload or sale."

