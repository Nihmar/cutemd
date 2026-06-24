; Inno Setup script for CuteMD - Markdown Editor
;
; Prerequisites:
;   1. PyInstaller build completed (dist\cutemd\ folder exists)
;   2. Inno Setup 6+ installed (https://jrsoftware.org/isinfo.php)
;   3. Optional: resources\cutemd.ico  (96x96 .ico, else default icon used)
;
; Build:   iscc scripts\cutemd_setup.iss
; Output:  dist\CuteMD_Setup.exe

#define MyAppName "CuteMD"
#define MyAppVersion "0.9.8.1"
#define MyAppPublisher "CuteMD Contributors"
#define MyAppURL "https://github.com/Nihmar/cutemd"
#define MyAppExeName "cutemd.exe"

[Setup]
AppId={{B8F4A3D2-9E5C-4A7B-8D1F-2C6E0A5F9B3D}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
SetupIconFile=..\resources\cutemd.ico
OutputDir=..\dist
OutputBaseFilename=CuteMD_Setup
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes
UninstallDisplayName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\cutemd\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
; --- File associations: .md and .markdown ---
; ProgID registration (machine-wide)
Root: HKLM; Subkey: "SOFTWARE\Classes\CuteMD.md"; ValueType: string; ValueName: ""; ValueData: "Markdown file (CuteMD)"; Flags: uninsdeletekey
Root: HKLM; Subkey: "SOFTWARE\Classes\CuteMD.md\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#MyAppExeName},0"; Flags: uninsdeletekey
Root: HKLM; Subkey: "SOFTWARE\Classes\CuteMD.md\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""; Flags: uninsdeletekey
Root: HKLM; Subkey: "SOFTWARE\Classes\CuteMD.md\shell\open"; ValueType: string; ValueName: "FriendlyAppName"; ValueData: "{#MyAppName}"; Flags: uninsdeletekey

; Associate .md extension
Root: HKLM; Subkey: "SOFTWARE\Classes\.md\OpenWithProgids"; ValueType: string; ValueName: "CuteMD.md"; ValueData: ""; Flags: uninsdeletevalue
Root: HKLM; Subkey: "SOFTWARE\Classes\.md"; ValueType: string; ValueName: ""; ValueData: "CuteMD.md"; Flags: uninsdeletevalue

; Associate .markdown extension
Root: HKLM; Subkey: "SOFTWARE\Classes\.markdown\OpenWithProgids"; ValueType: string; ValueName: "CuteMD.md"; ValueData: ""; Flags: uninsdeletevalue
Root: HKLM; Subkey: "SOFTWARE\Classes\.markdown"; ValueType: string; ValueName: ""; ValueData: "CuteMD.md"; Flags: uninsdeletevalue

; Register as an installed application (appears in Default Programs)
Root: HKLM; Subkey: "SOFTWARE\RegisteredApplications"; ValueType: string; ValueName: "{#MyAppName}"; ValueData: "SOFTWARE\{#MyAppName}\Capabilities"; Flags: uninsdeletevalue
Root: HKLM; Subkey: "SOFTWARE\{#MyAppName}\Capabilities"; ValueType: string; ValueName: "ApplicationName"; ValueData: "{#MyAppName}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "SOFTWARE\{#MyAppName}\Capabilities"; ValueType: string; ValueName: "ApplicationDescription"; ValueData: "A non-WYSIWYG Markdown editor"; Flags: uninsdeletekey
Root: HKLM; Subkey: "SOFTWARE\{#MyAppName}\Capabilities\FileAssociations"; ValueType: string; ValueName: ".md"; ValueData: "CuteMD.md"; Flags: uninsdeletekey
Root: HKLM; Subkey: "SOFTWARE\{#MyAppName}\Capabilities\FileAssociations"; ValueType: string; ValueName: ".markdown"; ValueData: "CuteMD.md"; Flags: uninsdeletekey

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
