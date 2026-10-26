#requires -Version 5.1
<#
Enrolls a verified Pardis Root CA into ordinary Windows Firefox.
Run from an elevated PowerShell on a device you own/manage.
Only Firefox policies are changed, NOT the Windows certificate store.
The root .cer must be copied from a trusted admin source and its SHA-256
fingerprint confirmed independently. Use Firefox Group Policy / Intune for
unattended fleet-wide rollout instead of a per-device script.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$RootCertificatePath,
    [Parameter(Mandatory=$true)][string]$ExpectedSha256,
    [string]$FirefoxInstallDir
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$id = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($id)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run PowerShell as Administrator, with the computer owner approval.'
}
$expected = ($ExpectedSha256 -replace '[:\s-]', '').ToUpperInvariant()
if ($expected -notmatch '^[0-9A-F]{64}$') {
    throw 'Provide an independently verified, 64-digit Root CA SHA-256 fingerprint.'
}

$filePath = (Resolve-Path -LiteralPath $RootCertificatePath).ProviderPath
$bytes = [IO.File]::ReadAllBytes($filePath)
try {
    $cert = New-Object Security.Cryptography.X509Certificates.X509Certificate2 -ArgumentList @(,$bytes)
} catch {
    throw 'Cannot load certificate: export a DER .cer from Ubuntu.'
}
try {
    # Disallow PEM bundles, appended content and unexpected certificates.
    if ($bytes.Length -ne $cert.RawData.Length) {
        throw 'The certificate file must be exactly one DER-encoded .cer.'
    }
    for ($i=0; $i -lt $bytes.Length; $i++) {
        if ($bytes[$i] -ne $cert.RawData[$i]) {
            throw 'The file does not match the parsed DER Root CA.'
        }
    }
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        $actual = [BitConverter]::ToString($sha.ComputeHash($cert.RawData)).Replace('-', '')
    } finally {
        $sha.Dispose()
    }
    if ($actual -cne $expected) {
        throw "Root CA SHA-256 fingerprint mismatch. Expected $expected, got $actual. No trust changed."
    }
    if ($cert.Subject -ne $cert.Issuer -or
        $cert.GetNameInfo([Security.Cryptography.X509Certificates.X509NameType]::SimpleName, $false) -ne 'Pardis AI Innovation Root CA') {
        throw 'Unexpected certificate identity. Expected the self-issued Pardis AI Innovation Root CA.'
    }
    $basic = @($cert.Extensions | Where-Object { $_.Oid.Value -eq '2.5.29.19' })
    if ($basic.Count -ne 1 -or -not $basic[0].CertificateAuthority) {
        throw 'Supplied certificate is not a CA=true Root certificate.'
    }
    if ($cert.NotBefore.ToUniversalTime() -gt [DateTime]::UtcNow -or
        $cert.NotAfter.ToUniversalTime() -le [DateTime]::UtcNow) {
        throw 'Root CA is not currently valid.'
    }

    $installs = @()
    if ($FirefoxInstallDir) {
        $installs = @($FirefoxInstallDir)
    } else {
        $installs += (Join-Path $env:ProgramFiles 'Mozilla Firefox')
        $x86 = [Environment]::GetEnvironmentVariable('ProgramFiles(x86)')
        if ($x86) { $installs += (Join-Path $x86 'Mozilla Firefox') }
    }
    $installs = @($installs | Where-Object {
        Test-Path -LiteralPath (Join-Path $_ 'firefox.exe') -PathType Leaf
    } | Select-Object -Unique)
    if ($installs.Count -eq 0) {
        throw 'Firefox not found. Supply -FirefoxInstallDir pointing to the folder containing firefox.exe.'
    }

    # Prevalidate existing managed policies before making any changes.
    foreach ($installDir in $installs) {
        $policyPath = Join-Path $installDir 'distribution\policies.json'
        if (Test-Path -LiteralPath $policyPath) {
            $existing = Get-Content -LiteralPath $policyPath -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($null -eq $existing -or
                $null -eq $existing.PSObject.Properties['policies'] -or
                $existing.policies -isnot [pscustomobject]) {
                throw "Unsupported existing Firefox policies.json; coordinate with your IT administrator: $policyPath"
            }
            $existingCerts = $existing.policies.PSObject.Properties['Certificates']
            if ($null -ne $existingCerts) {
                if ($existingCerts.Value -isnot [pscustomobject]) {
                    throw "Unsupported existing Certificates policy: $policyPath"
                }
                $installedRoots = $existingCerts.Value.PSObject.Properties['Install']
                if ($null -ne $installedRoots -and $installedRoots.Value -isnot [array]) {
                    throw "Existing Certificates.Install is not an array: $policyPath"
                }
            }
        }
    }

    $destDir = Join-Path $env:ProgramData 'Pardis\Certificates'
    $dest = Join-Path $destDir 'pardis-root.cer'
    if (Test-Path -LiteralPath $dest) {
        $installed = [IO.File]::ReadAllBytes($dest)
        if ($installed.Length -ne $bytes.Length) {
            throw 'Different Root file already installed. Refusing overwrite.'
        }
        for ($i=0; $i -lt $bytes.Length; $i++) {
            if ($bytes[$i] -ne $installed[$i]) {
                throw 'Different Root already installed. Refusing overwrite.'
            }
        }
    } else {
        New-Item -ItemType Directory -Force -Path $destDir | Out-Null
        Copy-Item -LiteralPath $filePath -Destination $dest
    }

    foreach ($installDir in $installs) {
        $distribution = Join-Path $installDir 'distribution'
        $path = Join-Path $distribution 'policies.json'
        New-Item -ItemType Directory -Force -Path $distribution | Out-Null
        $hadPolicy = Test-Path -LiteralPath $path
        if ($hadPolicy) {
            $policy = Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json
        } else {
            $policy = [pscustomobject]@{ policies = [pscustomobject]@{} }
        }
        $entry = $policy.policies.PSObject.Properties['Certificates']
        if ($null -eq $entry) {
            $policy.policies | Add-Member -MemberType NoteProperty -Name Certificates -Value ([pscustomobject]@{ Install=@($dest) })
        } else {
            $cp = $entry.Value
            $installEntry = $cp.PSObject.Properties['Install']
            if ($null -eq $installEntry) {
                $cp | Add-Member -MemberType NoteProperty -Name Install -Value @($dest)
            } else {
                $current = @($installEntry.Value)
                if ($current -notcontains $dest) {
                    $installEntry.Value = @($current + $dest)
                }
            }
        }
        $staged = Join-Path $distribution ('policies.json.new-' + $PID)
        try {
            $json = $policy | ConvertTo-Json -Depth 40
            [IO.File]::WriteAllText($staged, $json + [Environment]::NewLine, (New-Object Text.UTF8Encoding($false)))
            if ($hadPolicy) {
                $stamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
                Copy-Item -LiteralPath $path -Destination ($path + '.backup-' + $stamp)
            }
            Move-Item -LiteralPath $staged -Destination $path -Force
        } finally {
            Remove-Item -LiteralPath $staged -Force -ErrorAction SilentlyContinue
        }
        Write-Host "[Pardis] Updated Firefox policies: $path"
    }
    Write-Host "[Pardis] Root CA SHA-256 verified: $actual"
    Write-Host '[Pardis] Restart ordinary Firefox; inspect about:policies#active.'
    Write-Host '[Pardis] Verify https://ca1.iravand.ir without any TLS bypass.'
} finally {
    $cert.Dispose()
}
