<#
.SYNOPSIS
    Registers CuteMD as a Markdown editor in Windows file associations.
.DESCRIPTION
    Run this script AFTER building/installing CuteMD.
    It adds "Open with CuteMD" to the right-click menu for .md files.
    Uses per-user registration (no admin required).
.PARAMETER ExePath
    Full path to cutemd.exe. Default: next to this script.
.EXAMPLE
    ./scripts/register_windows.ps1
    ./scripts/register_windows.ps1 -ExePath "C:\Program Files\CuteMD\cutemd.exe"
#>
param(
    [string]$ExePath = ""
)

$ErrorActionPreference = "Stop"

# Resolve exe path
if (-not $ExePath) {
    $ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
    $ExePath = Join-Path $ScriptDir "..\dist\cutemd\cutemd.exe"
}
if (-not (Test-Path $ExePath)) {
    Write-Error "cutemd.exe not found at: $ExePath"
    exit 1
}
$ExePath = (Resolve-Path $ExePath).Path

Write-Host "Registering CuteMD as Markdown editor..."
Write-Host "  Exe : $ExePath"

# Friendly name
$ProgId = "CuteMD.md"
$FriendlyName = "Markdown file (CuteMD)"

# --- Per-user registration under HKCU\SOFTWARE\Classes ---
$RegRoot = "HKCU:\SOFTWARE\Classes"

# ProgID entry
New-Item -Path "$RegRoot\$ProgId" -Force | Out-Null
Set-ItemProperty -Path "$RegRoot\$ProgId" -Name "(Default)" -Value $FriendlyName

# Icon
New-Item -Path "$RegRoot\$ProgId\DefaultIcon" -Force | Out-Null
Set-ItemProperty -Path "$RegRoot\$ProgId\DefaultIcon" -Name "(Default)" -Value "`"$ExePath`",0"

# Shell → open command
New-Item -Path "$RegRoot\$ProgId\shell\open\command" -Force | Out-Null
Set-ItemProperty -Path "$RegRoot\$ProgId\shell\open\command" -Name "(Default)" -Value "`"$ExePath`" `"%1`""

# Friendly name for the "Open" verb
Set-ItemProperty -Path "$RegRoot\$ProgId\shell\open" -Name "FriendlyAppName" -Value "CuteMD"

# Associate .md and .markdown extensions
foreach ($ext in @(".md", ".markdown")) {
    New-Item -Path "$RegRoot\$ext\OpenWithProgids" -Force | Out-Null
    New-ItemProperty -Path "$RegRoot\$ext\OpenWithProgids" -Name $ProgId -Value "" -PropertyType String -Force | Out-Null
    Write-Host "  Registered $ext"
}

# Register in "Open with" list via Application Registration
$AppRegPath = "$RegRoot\Applications\cutemd.exe"
New-Item -Path "$AppRegPath\shell\open\command" -Force | Out-Null
Set-ItemProperty -Path "$AppRegPath\shell\open\command" -Name "(Default)" -Value "`"$ExePath`" `"%1`""
Set-ItemProperty -Path "$AppRegPath\shell\open" -Name "FriendlyAppName" -Value "CuteMD"

# Capabilities (for Default Programs)
$CapPath = "$AppRegPath\Capabilities"
New-Item -Path $CapPath -Force | Out-Null
Set-ItemProperty -Path $CapPath -Name "ApplicationName" -Value "CuteMD"
Set-ItemProperty -Path $CapPath -Name "ApplicationDescription" -Value "A non-WYSIWYG Markdown editor"
New-Item -Path "$CapPath\FileAssociations" -Force | Out-Null
New-ItemProperty -Path "$CapPath\FileAssociations" -Name ".md" -Value $ProgId -PropertyType String -Force | Out-Null
New-ItemProperty -Path "$CapPath\FileAssociations" -Name ".markdown" -Value $ProgId -PropertyType String -Force | Out-Null

# Register with Default Programs
$RegisteredApps = "HKCU:\SOFTWARE\RegisteredApplications"
New-Item -Path $RegisteredApps -Force | Out-Null
Set-ItemProperty -Path $RegisteredApps -Name "CuteMD" -Value "$AppRegPath\Capabilities"

Write-Host "Done. CuteMD now appears in 'Open with' menu and as default program option."
Write-Host "Use 'Default Programs' in Windows Settings to set CuteMD as default for .md files."
