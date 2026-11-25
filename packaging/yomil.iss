; Inno Setup script for YOMIL (`make installer`, or CI). Needs Inno Setup 6.3+.
; Build the frozen app first (`make freeze`), then:
;   iscc /DAppVersion=1.2.3 /DFileVersion=1.2.3.0 packaging\yomil.iss
; AppVersion is the package version, which may be a dev build's (1.2.4.dev118+abc1234);
; FileVersion is the Windows file version, which must be four numbers (see
; src/yomil/devtools/versioning.py).
;
; Per-user install: no administrator rights, installed under %LOCALAPPDATA%\Programs.
; The user's data lives in %LOCALAPPDATA%\yomil, which this never touches: the
; uninstaller removes only what it installed.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef FileVersion
  #define FileVersion "0.0.0.0"
#endif

[Setup]
; Never change AppId: it's how an upgrade finds the installed copy.
AppId={{BC2F82C1-DA90-452D-A201-6842457085B6}
AppName=YOMIL
AppVersion={#AppVersion}
AppVerName=YOMIL {#AppVersion}
AppPublisher=YOMIL contributors
VersionInfoVersion={#FileVersion}
PrivilegesRequired=lowest
DefaultDirName={autopf}\YOMIL
DisableDirPage=auto
DisableProgramGroupPage=yes
DisableReadyPage=yes
OutputDir=..\dist
OutputBaseFilename=YOMIL-Setup-{#AppVersion}
SetupIconFile=..\src\yomil\app\icons\yomil.ico
UninstallDisplayIcon={app}\yomil.exe
UninstallDisplayName=YOMIL
WizardStyle=modern
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Close a running YOMIL before replacing its files (it saves its snapshot as it goes).
CloseApplications=yes
RestartApplications=no

[Tasks]
Name: "startup"; Description: "Start YOMIL when I sign in to Windows (recommended, for reminders)"
Name: "desktopicon"; Description: "Put a YOMIL icon on the desktop"; Flags: unchecked

[InstallDelete]
; An upgrade replaces the whole bundle, so no stale libraries from the old version remain.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "..\dist\pyinstaller\YOMIL\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; The AppUserModelID lets reminders appear as Windows toasts. It must match
; APP_USER_MODEL_ID and the shortcut name in src/yomil/app/notify.py.
Name: "{autoprograms}\YOMIL"; Filename: "{app}\yomil.exe"; AppUserModelID: "YOMIL.YOMIL"
Name: "{autodesktop}\YOMIL"; Filename: "{app}\yomil.exe"; Tasks: desktopicon

[Registry]
; The same value Preferences > "Start YOMIL when I sign in" reads and writes
; (src/yomil/autostart.py), so the two always agree.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "YOMIL"; ValueData: """{app}\yomil.exe"" --minimized"; Tasks: startup

[Run]
Filename: "{app}\yomil.exe"; Description: "Open YOMIL now"; Flags: nowait postinstall skipifsilent

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  { Also when it was turned on later from Preferences, not by this installer. }
  if CurUninstallStep = usPostUninstall then
    RegDeleteValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run', 'YOMIL');
end;
