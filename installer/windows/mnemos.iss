; installer/windows/mnemos.iss
; Inno Setup script for claude-mnemos.
; Build:
;   "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer/windows/mnemos.iss
; Output:
;   installer/windows/dist/claude-mnemos-setup-x64.exe

#define MyAppName "claude-mnemos"
#define MyAppVersion "0.0.1"
#define MyAppPublisher "Yarik"
#define MyAppURL "https://github.com/DeveloperrOp/claude-mnemos"
#define MyAppExeName "claude-mnemos.exe"

[Setup]
AppId={{4F2A8C90-7D5C-4B1A-9D3E-8E9F1A2B3C4D}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
LicenseFile=
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=dist
OutputBaseFilename=claude-mnemos-setup-x64
Compression=lzma2/ultra
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
CloseApplications=force
RestartApplications=no
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked
Name: "autostart";   Description: "Start &claude-mnemos when I sign in to Windows"; GroupDescription: "Startup:"; Flags: checkedonce

[Files]
; PyInstaller produces dist/claude-mnemos/ as a one-dir bundle.
; Path is relative to this .iss file.
Source: "..\..\dist\claude-mnemos\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Parameters: "tray run"
Name: "{group}\Open Dashboard"; Filename: "http://localhost:5757"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{userdesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Parameters: "tray run"; Tasks: desktopicon

[Run]
; Launch tray (which auto-spawns daemon) on first run.
Filename: "{app}\{#MyAppExeName}"; Parameters: "tray run"; Description: "Start claude-mnemos now"; Flags: postinstall nowait skipifsilent

[UninstallRun]
; Stop the tray + daemon before file removal.
Filename: "{app}\{#MyAppExeName}"; Parameters: "tray uninstall"; Flags: runhidden; RunOnceId: "RemoveAutostart"
Filename: "{app}\{#MyAppExeName}"; Parameters: "daemon stop";    Flags: runhidden; RunOnceId: "StopDaemon"
Filename: "{app}\{#MyAppExeName}"; Parameters: "hooks uninstall"; Flags: runhidden; RunOnceId: "RemoveHooks"
