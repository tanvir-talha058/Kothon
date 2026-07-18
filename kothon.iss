; Inno Setup script for Kothon — compile with Inno Setup 6 (iscc kothon.iss)
; Prerequisite: python -m PyInstaller kothon.spec  (produces dist\Kothon)

#define AppName "Kothon"
#define AppVersion "0.2.0"
#define AppExe "Kothon.exe"

[Setup]
AppId={{7E1B3C55-9A0D-4E7B-B7A1-KOTHON020}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Tanvir
AppPublisherURL=https://github.com/your-username/kothon
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
; Per-user install: no UAC prompt, friendlier with antivirus for unsigned builds
PrivilegesRequired=lowest
OutputBaseFilename=KothonSetup-{#AppVersion}
OutputDir=installer
SetupIconFile=assets\kothon.ico
UninstallDisplayIcon={app}\{#AppExe}
LicenseFile=LICENSE
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Shortcuts:"
Name: "startup"; Description: "Start {#AppName} when Windows starts"; GroupDescription: "Options:"; Flags: unchecked

[Files]
; App files (PyInstaller output). The models junction/folder inside dist is
; excluded — models are taken from the project models directory below.
Source: "dist\Kothon\*"; DestDir: "{app}"; Excludes: "models\*"; Flags: recursesubdirs ignoreversion
; Speech models shipped with the installer
Source: "models\*"; DestDir: "{app}\models"; Excludes: "*.zip"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
  ValueType: string; ValueName: "{#AppName}"; ValueData: """{app}\{#AppExe}"""; \
  Flags: uninsdeletevalue; Tasks: startup

[Run]
Filename: "{app}\{#AppExe}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Settings are the user's — leave ~/.kothon in place on uninstall
Type: filesandordirs; Name: "{app}"
