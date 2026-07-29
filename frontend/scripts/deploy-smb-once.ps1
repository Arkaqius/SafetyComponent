[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)]
  [string]$SourceDirectory,

  [Parameter(Mandatory = $true)]
  [string]$HostName,

  [string]$FolderName = 'SafetyHome'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-FileManifest {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Root
  )

  $normalizedRoot = (Resolve-Path -LiteralPath $Root).ProviderPath.TrimEnd('\')
  return @(
    Get-ChildItem -LiteralPath $normalizedRoot -Recurse -File |
      ForEach-Object {
        [pscustomobject]@{
          RelativePath = $_.FullName.Substring($normalizedRoot.Length).TrimStart('\')
          Length = $_.Length
          Sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash
        }
      } |
      Sort-Object RelativePath
  )
}

function Assert-MatchingManifest {
  param(
    [Parameter(Mandatory = $true)]
    [string]$ExpectedRoot,

    [Parameter(Mandatory = $true)]
    [string]$ActualRoot
  )

  $expected = Get-FileManifest -Root $ExpectedRoot
  $actual = Get-FileManifest -Root $ActualRoot

  if ($expected.Count -ne $actual.Count) {
    throw "Niezgodna liczba plikow: lokalnie $($expected.Count), zdalnie $($actual.Count)."
  }

  for ($index = 0; $index -lt $expected.Count; $index += 1) {
    $expectedFile = $expected[$index]
    $actualFile = $actual[$index]
    if (
      $expectedFile.RelativePath -ne $actualFile.RelativePath -or
      $expectedFile.Length -ne $actualFile.Length -or
      $expectedFile.Sha256 -ne $actualFile.Sha256
    ) {
      throw "Niezgodny plik po wdrozeniu: $($expectedFile.RelativePath)."
    }
  }

  return $actual
}

if ($FolderName -notmatch '^[A-Za-z0-9_-]+$') {
  throw 'FolderName moze zawierac wylacznie litery, cyfry, myslnik i podkreslenie.'
}

$frontendRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$expectedSource = (Resolve-Path -LiteralPath (Join-Path $frontendRoot 'dist')).Path
$source = (Resolve-Path -LiteralPath $SourceDirectory).Path
if ($source -ne $expectedSource) {
  throw "Zrodlo wdrozenia musi wskazywac dokladnie na $expectedSource."
}
if (-not (Test-Path -LiteralPath (Join-Path $source 'index.html') -PathType Leaf)) {
  throw 'Brak dist/index.html.'
}

$username = Read-Host 'Samba username'
$securePassword = Read-Host 'Samba password' -AsSecureString
if ([string]::IsNullOrWhiteSpace($username) -or $securePassword.Length -eq 0) {
  throw 'Brak danych uwierzytelniajacych Samba.'
}

$credential = [pscredential]::new($username, $securePassword)
$driveName = "HakitDeploy$([guid]::NewGuid().ToString('N').Substring(0, 8))"
$shareRoot = "\\$HostName\config"
$drive = $null
$staging = $null
$backup = $null
$target = $null
$previousVersionMoved = $false
$newVersionPromoted = $false
$deploymentVerified = $false

try {
  $drive = New-PSDrive -Name $driveName -PSProvider FileSystem -Root $shareRoot -Credential $credential
  $wwwRoot = "$driveName`:\www"
  if (-not (Test-Path -LiteralPath $wwwRoot -PathType Container)) {
    throw "Brak istniejacego katalogu /config/www na $HostName."
  }

  $target = Join-Path $wwwRoot $FolderName
  $timestamp = [DateTime]::UtcNow.ToString('yyyyMMddHHmmssfff')
  $staging = Join-Path $wwwRoot ".$FolderName.deploy-$timestamp"
  $backup = Join-Path $wwwRoot ".$FolderName.backup-$timestamp"

  $expectedPrefix = "$driveName`:\www\"
  foreach ($remotePath in @($target, $staging, $backup)) {
    if (-not $remotePath.StartsWith($expectedPrefix, [StringComparison]::OrdinalIgnoreCase)) {
      throw "Niebezpieczna sciezka zdalna: $remotePath."
    }
  }

  New-Item -ItemType Directory -Path $staging | Out-Null
  Get-ChildItem -LiteralPath $source -Force |
    Copy-Item -Destination $staging -Recurse -Force
  Assert-MatchingManifest -ExpectedRoot $source -ActualRoot $staging | Out-Null

  if (Test-Path -LiteralPath $target) {
    Move-Item -LiteralPath $target -Destination $backup
    $previousVersionMoved = $true
  }

  Move-Item -LiteralPath $staging -Destination $target
  $newVersionPromoted = $true

  $finalManifest = Assert-MatchingManifest -ExpectedRoot $source -ActualRoot $target
  if (-not (Test-Path -LiteralPath (Join-Path $target 'index.html') -PathType Leaf)) {
    throw 'Brak index.html po podmianie.'
  }
  $deploymentVerified = $true

  if ($previousVersionMoved -and (Test-Path -LiteralPath $backup)) {
    try {
      Remove-Item -LiteralPath $backup -Recurse -Force
    }
    catch {
      Write-Warning "Nowa wersja dziala, ale nie usunieto backupu: $backup."
    }
  }

  [pscustomobject]@{
    Success = $true
    Target = "/config/www/$FolderName"
    FileCount = $finalManifest.Count
    IndexSha256 = (Get-FileHash -LiteralPath (Join-Path $target 'index.html') -Algorithm SHA256).Hash
    PreviousVersionReplaced = $previousVersionMoved
  } | ConvertTo-Json -Compress
}
catch {
  if (-not $deploymentVerified) {
    if ($newVersionPromoted -and $null -ne $target -and (Test-Path -LiteralPath $target)) {
      Remove-Item -LiteralPath $target -Recurse -Force
    }
    if ($previousVersionMoved -and $null -ne $backup -and (Test-Path -LiteralPath $backup)) {
      Move-Item -LiteralPath $backup -Destination $target
    }
    if ($null -ne $staging -and (Test-Path -LiteralPath $staging)) {
      Remove-Item -LiteralPath $staging -Recurse -Force
    }
  }
  throw
}
finally {
  $securePassword = $null
  $credential = $null
  if ($null -ne $drive) {
    Remove-PSDrive -Name $driveName -Force
  }
}
