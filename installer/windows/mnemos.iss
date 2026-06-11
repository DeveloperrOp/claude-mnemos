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
; Switched from lzma2/ultra + SolidCompression in v0.0.34 — those
; settings produce a tightly packed exe that Defender's heuristic
; scanner increasingly flags as suspicious on Win11. Default lzma
; (no /ultra, no solid) yields a slightly larger but more readily
; trusted binary.
Compression=lzma
WizardStyle=modern
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
CloseApplications=force
RestartApplications=no
UninstallDisplayIcon={app}\{#MyAppExeName}
; Full VersionInfo block — exe with rich metadata is less likely to
; trip Defender's "unknown vendor" heuristic.
VersionInfoVersion={#MyAppVersion}.0
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription=claude-mnemos installer
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}
VersionInfoCopyright=Copyright (c) 2026 {#MyAppPublisher}

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

; Consume the "autostart" task (v0.0.48): unchecked -> remove the Startup
; shortcut AND record autostart_decision="declined" so first-run postinstall
; doesn't re-install it. Checked -> RewriteAutostartLnk in [Code] writes the lnk.
Filename: "{app}\{#MyAppExeName}"; Parameters: "tray uninstall"; Tasks: not autostart; Flags: runhidden

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

// ---------------------------------------------------------------------------
// Kill anything holding port 5757 + any python process running claude_mnemos
// before we install. This closes the gap that taskkill /IM claude-mnemos.exe
// misses — a dev-tree `python -m claude_mnemos.daemon` (PID 30536 in the
// 2026-05-25 incident) keeps the port bound, the new bundle's daemon fails
// to bind, and the user sees stale state from the dev daemon's runtime dir.
// ---------------------------------------------------------------------------

procedure KillStaleProcesses;
var
  ResultCode: Integer;
begin
  // Best-effort: each command swallows its own errors via runhidden.
  // /F = force, /T = also kill child processes.

  // 1. Anything matching our installed exe names — same as [UninstallRun]
  //    but runs PRE-install too, before file replacement.
  Exec(ExpandConstant('{sys}\taskkill.exe'),
       '/F /IM claude-mnemos.exe /T',
       '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Exec(ExpandConstant('{sys}\taskkill.exe'),
       '/F /IM claude-mnemos-cli.exe /T',
       '', SW_HIDE, ewWaitUntilTerminated, ResultCode);

  // 2. Any python.exe with 'claude_mnemos' in its command line. Catches
  //    `python -m claude_mnemos.daemon` from a developer install. WMIC is
  //    deprecated in Win11 but PowerShell Get-CimInstance works everywhere.
  Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
       '-NoProfile -Command "Get-CimInstance Win32_Process -Filter ''Name=''''python.exe'''''' | Where-Object { $_.CommandLine -like ''*claude_mnemos*'' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"',
       '', SW_HIDE, ewWaitUntilTerminated, ResultCode);

  // 3. Whoever holds the daemon's TCP port. PID is in column 5 of netstat
  //    -ano output (last field for LISTENING rows). PowerShell parses it
  //    and force-kills.
  Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
       '-NoProfile -Command "Get-NetTCPConnection -LocalPort 5757 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"',
       '', SW_HIDE, ewWaitUntilTerminated, ResultCode);

  // Give Windows a moment to release file handles before file copy starts.
  Sleep(1500);
end;

// ---------------------------------------------------------------------------
// Autostart shortcut handling (v0.0.48: the [Tasks] "autostart" checkbox is
// authoritative — it was a placebo since v0.0.5).
//
// Background (2026-06-10 incident): the Startup-folder Mnemos.lnk can go
// stale two ways:
//   1. It points at a DIFFERENT install (dev venv pythonw.exe, an old install
//      dir). At sign-in that stale tray grabs the single-instance mutex and
//      the freshly installed exe exits silently — "переустановил, ничего не
//      открылось".
//   2. The uninstall-old-version step above removes it (its [UninstallRun]
//      includes `tray uninstall`), silently dropping autostart on upgrades.
//
// Strategy: the "autostart" task decides, in both directions.
//   Checked   -> CurStepChanged(ssPostInstall) rewrites the .lnk from scratch
//                to point at the just-installed exe. Covers fresh installs,
//                upgrades AND stale-shortcut repair — this subsumes the old
//                "restore the .lnk only if it existed before the uninstall"
//                snapshot.
//   Unchecked -> the [Run] `tray uninstall` entry removes the .lnk and
//                records autostart_decision="declined", which the exe's
//                first-run postinstall respects (it skips autostart install
//                when declined) and won't silently re-add it.
//
// Task memory: checkedonce remembers the user's previous selection ONLY on
// the in-place (IDNO) upgrade path. Inno keeps prior task selections in the
// {AppId}_is1 registry key, and the recommended IDYES path runs the OLD
// uninstaller (UnInstallOldVersion in InitializeSetup) which deletes that key
// BEFORE the wizard reads it — the checkbox would silently revert to checked
// and a user who declined autostart would get it back with a blind "Next".
// InitializeWizard below therefore re-reads the decline persisted in
// %USERPROFILE%\.claude-mnemos\install-state.json (which survives uninstalls)
// and pre-unchecks the task.
// ---------------------------------------------------------------------------

function AutostartLnkPath: String;
begin
  Result := ExpandConstant('{userstartup}\Mnemos.lnk');
end;

procedure RewriteAutostartLnk;
var
  Sh, Lnk: Variant;
begin
  try
    Sh := CreateOleObject('WScript.Shell');
    Lnk := Sh.CreateShortcut(AutostartLnkPath());
    Lnk.TargetPath := ExpandConstant('{app}\{#MyAppExeName}');
    // Bare subcommand — the bundled exe rejects the legacy
    // "-m claude_mnemos.tray run" arguments with exit 2.
    Lnk.Arguments := 'tray run';
    Lnk.WorkingDirectory := ExpandConstant('{app}');
    Lnk.WindowStyle := 7;  // minimized; tray app has no main window
    Lnk.Save;
    Log('Autostart shortcut rewritten to ' + ExpandConstant('{app}\{#MyAppExeName}'));
  except
    // Better no autostart than a stale one that hijacks the mutex.
    Log('Autostart shortcut rewrite failed (' + GetExceptionMessage + '); deleting it');
    DeleteFile(AutostartLnkPath());
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  // The "autostart" task is authoritative (v0.0.48): checked -> write a fresh
  // shortcut pointing at the just-installed exe (covers both fresh installs
  // and upgrades, and repairs stale dev-venv shortcuts); unchecked -> the
  // [Run] "tray uninstall" entry removes it and records the decline.
  if (CurStep = ssPostInstall) and WizardIsTaskSelected('autostart') then
    RewriteAutostartLnk();
end;

function AutostartPreviouslyDeclined: Boolean;
var
  StatePath: String;
  S: AnsiString;
  T: String;
begin
  Result := False;
  StatePath := ExpandConstant('{%USERPROFILE}\.claude-mnemos\install-state.json');
  if not FileExists(StatePath) then
    Exit;
  if not LoadStringFromFile(StatePath, S) then
    Exit;
  T := String(S);
  // install-state.json is pydantic model_dump_json output. Probe both the
  // indented ('": "') and compact ('":"') separators with a plain substring
  // search — ASCII patterns are BOM/UTF-8 safe, and a full JSON parse is
  // overkill in Pascal script. tests/installer/test_iss_autostart_repair.py
  // cross-checks these literals against the real serializer output.
  Result := (Pos('"autostart_decision": "declined"', T) > 0) or
            (Pos('"autostart_decision":"declined"', T) > 0);
end;

procedure InitializeWizard;
begin
  // Runs after the wizard form (and its tasks list) is created — the earliest
  // point where WizardSelectTasks is valid. '!name' deselects; the parameter
  // is processed like /MERGETASKS, so the desktopicon task keeps its state.
  if AutostartPreviouslyDeclined() then begin
    WizardSelectTasks('!autostart');
    Log('autostart task pre-unchecked: install-state.json records a prior decline');
  end;
end;

function InitializeSetup(): Boolean;
var
  Response: Integer;
begin
  Result := True;

  // Always run the kill sweep before anything else — handles both fresh and
  // upgrade installs. Fresh installs are no-ops (no processes to kill);
  // upgrades benefit even on the IDNO path (in-place overwrite needs file
  // handles released).
  KillStaleProcesses();

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
