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
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: checkedonce
Name: "autostart";   Description: "Start &claude-mnemos when I sign in to Windows"; GroupDescription: "Startup:"; Flags: checkedonce

[Files]
; PyInstaller produces dist/claude-mnemos/ as a one-dir bundle.
; Path is relative to this .iss file.
Source: "..\..\dist\claude-mnemos\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "MicrosoftEdgeWebview2Setup.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Parameters: "launcher"
Name: "{group}\Open Dashboard"; Filename: "http://localhost:5757"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{userdesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Parameters: "launcher"; Tasks: desktopicon

[Run]
; Install Edge WebView2 Runtime if missing (required by pywebview).
Filename: "{tmp}\MicrosoftEdgeWebview2Setup.exe"; Parameters: "/silent /install"; Check: not WebView2RuntimeInstalled; StatusMsg: "Installing Edge WebView2 Runtime..."

Filename: "{app}\{#MyAppExeName}"; Parameters: "launcher"; Description: "Start claude-mnemos now"; Flags: postinstall nowait skipifsilent

[UninstallRun]
; Order matters: cleanup actions FIRST (while exe is still launchable),
; THEN force-kill any surviving claude-mnemos.exe processes so file removal
; isn't blocked by locked .exe / .pyd handles. CloseApplications=force in
; [Setup] handles install-time but not uninstall-time, hence the explicit
; taskkill here.
Filename: "{app}\{#MyAppExeName}"; Parameters: "tray uninstall"; Flags: runhidden; RunOnceId: "RemoveAutostart"
Filename: "{app}\{#MyAppExeName}"; Parameters: "daemon stop";    Flags: runhidden; RunOnceId: "StopDaemon"
Filename: "{app}\{#MyAppExeName}"; Parameters: "hooks uninstall"; Flags: runhidden; RunOnceId: "RemoveHooks"
Filename: "{sys}\taskkill.exe"; Parameters: "/F /IM claude-mnemos.exe /T"; Flags: runhidden; RunOnceId: "KillMnemos"
Filename: "{sys}\taskkill.exe"; Parameters: "/F /IM claude-mnemos-cli.exe /T"; Flags: runhidden; RunOnceId: "KillMnemosCli"

[Code]
function WebView2RuntimeInstalled: Boolean;
var
  V: string;
begin
  Result := RegQueryStringValue(HKLM,
    'Software\Wow6432Node\Microsoft\EdgeUpdate\ClientState\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}',
    'pv', V) and (V <> '');
  if not Result then
    Result := RegQueryStringValue(HKCU,
      'Software\Microsoft\EdgeUpdate\ClientState\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}',
      'pv', V) and (V <> '');
end;

// ---------------------------------------------------------------------------
// Detect-and-uninstall previous version (v0.0.9+ feature).
//
// Inno's default behaviour is "in-place upgrade": same AppId + DefaultDirName
// → it overwrites files in the existing dir without explicit uninstall. That
// works when nothing is locked, but the bundled tray + daemon + launcher
// processes hold .exe / .pyd handles that block file replacement, leaving the
// install in a half-overwritten state.
//
// Cleaner: detect the old install via its uninstall registry entry and run
// its unins000.exe /SILENT first — that path INCLUDES our [UninstallRun]
// taskkill steps (since v0.0.6) so processes are guaranteed dead before the
// new bundle lands.
// ---------------------------------------------------------------------------

function GetUninstallString: String;
var
  RegKey, S: String;
begin
  // Inno appends "_is1" to AppId for its uninstall registry entry.
  RegKey := 'Software\Microsoft\Windows\CurrentVersion\Uninstall\' +
            '{{4F2A8C90-7D5C-4B1A-9D3E-8E9F1A2B3C4D}_is1';
  S := '';
  if not RegQueryStringValue(HKLM, RegKey, 'UninstallString', S) then
    RegQueryStringValue(HKCU, RegKey, 'UninstallString', S);
  Result := S;
end;

function IsUpgrade: Boolean;
begin
  Result := (GetUninstallString() <> '');
end;

function UnInstallOldVersion: Boolean;
var
  S: String;
  ResultCode: Integer;
begin
  Result := False;
  S := GetUninstallString();
  if S = '' then
    Exit;
  S := RemoveQuotes(S);
  // /SILENT runs the uninstaller without UI; /SUPPRESSMSGBOXES kills any
  // confirmation prompts; /NORESTART blocks the uninstaller from rebooting
  // (we never need a reboot for our payload). ewWaitUntilTerminated blocks
  // the installer thread until uninstall is fully done — critical so file
  // removal completes BEFORE we start writing the new bundle.
  Result := Exec(S, '/SILENT /SUPPRESSMSGBOXES /NORESTART', '',
                 SW_HIDE, ewWaitUntilTerminated, ResultCode) and (ResultCode = 0);
end;

function InitializeSetup(): Boolean;
var
  Response: Integer;
begin
  Result := True;
  if not IsUpgrade() then
    Exit;
  Response := MsgBox(
    'A previous version of claude-mnemos is already installed.' + #13#10#13#10 +
    'Uninstall it before installing this update?' + #13#10 +
    '(recommended — guarantees a clean install)' + #13#10#13#10 +
    'Yes  — uninstall the old version, then install this one' + #13#10 +
    'No   — install in place over the existing files' + #13#10 +
    'Cancel — abort this installer',
    mbConfirmation, MB_YESNOCANCEL);
  if Response = IDCANCEL then begin
    Result := False;  // user aborted whole install
    Exit;
  end;
  if Response = IDYES then begin
    if not UnInstallOldVersion() then begin
      MsgBox('Could not uninstall the previous version automatically. ' +
             'Please uninstall it manually from Settings → Apps, then re-run this installer.',
             mbError, MB_OK);
      Result := False;
    end;
  end;
  // IDNO → fall through; Inno will do its default in-place upgrade.
end;
