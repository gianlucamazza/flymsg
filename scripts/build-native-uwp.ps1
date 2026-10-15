# Packaging patterns adapted from xbox-gpu-training/scripts/build-e0-uwp.ps1 (MIT).
param([string]$Commit = $(if ($env:GITHUB_SHA) { $env:GITHUB_SHA } else { "unknown" }))
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$sdkRoot = "${env:ProgramFiles(x86)}\Windows Kits\10"
$sdk = Get-ChildItem "$sdkRoot\Include" -Directory | Where-Object { Test-Path "$($_.FullName)\um\d3d12.h" } | Sort-Object Name -Descending | Select-Object -First 1
$vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
$vs = & $vswhere -latest -products '*' -property installationPath
$targets = Get-ChildItem "$vs\MSBuild\Microsoft\VC" -Directory | Sort-Object Name -Descending | Select-Object -First 1
$toolset = Get-ChildItem "$($targets.FullName)\Platforms\x64\PlatformToolsets" -Directory | Where-Object { $_.Name -match '^v\d+$' } | Sort-Object Name -Descending | Select-Object -First 1
if (-not $sdk -or -not $toolset) { throw "Windows SDK/MSVC toolset missing" }
& nuget restore native/uwp/packages.config -PackagesDirectory native/uwp/packages -NonInteractive
if ($LASTEXITCODE -ne 0) { throw "CppWinRT restore failed" }
& "$sdkRoot\bin\$($sdk.Name)\x64\dxc.exe" -T cs_6_0 -E CSMain -Gis -Ges -Fo native/uwp/Assets/lif.cso native/lif.hlsl
if ($LASTEXITCODE -ne 0) { throw "HLSL compile failed" }
& "$vs\MSBuild\Current\Bin\MSBuild.exe" native/uwp/FlymsgWorker.vcxproj /m /p:Configuration=Release /p:Platform=x64 "/p:FlymsgSdkVersion=$($sdk.Name)" "/p:FlymsgToolset=$($toolset.Name)" "/p:FlymsgCommit=$Commit" /p:AppxPackageSigningEnabled=false /p:UapAppxPackageBuildMode=SideloadOnly
if ($LASTEXITCODE -ne 0) { throw "UWP build failed" }
