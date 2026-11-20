#define MyAppName "CheckMate"
#ifndef MyAppVersion
  #define MyAppVersion "0.1.0"
#endif

[Setup]
AppId={{8D2F5E1C-6B7A-4C3D-9E21-5A7B9C0D1E2F}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=CheckMate
DefaultDirName={localappdata}\Programs\CheckMate
DefaultGroupName=CheckMate
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist-installer
OutputBaseFilename=CheckMate-Setup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=..\assets\checkmate.ico
UninstallDisplayIcon={app}\CheckMate.exe
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "desktopicon"; Description: "Creer un raccourci sur le Bureau"; GroupDescription: "Raccourcis"; Flags: unchecked

[Files]
Source: "..\dist\CheckMate\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs

[Icons]
Name: "{userprograms}\CheckMate"; Filename: "{app}\CheckMate.exe"; Parameters: "setup"; Comment: "Configurer CheckMate"
Name: "{userdesktop}\CheckMate"; Filename: "{app}\CheckMate.exe"; Parameters: "setup"; Tasks: desktopicon

[Run]
Filename: "{app}\CheckMate.exe"; Parameters: "setup"; Description: "Configurer CheckMate"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/F /IM CheckMate.exe"; Flags: runhidden; RunOnceId: "KillApp"
Filename: "{sys}\schtasks.exe"; Parameters: "/Delete /F /TN CheckMate"; Flags: runhidden; RunOnceId: "DeleteOldTask"
Filename: "{sys}\reg.exe"; Parameters: "delete ""HKCU\Software\Microsoft\Windows\CurrentVersion\Run"" /v CheckMate /f"; Flags: runhidden; RunOnceId: "DeleteRunKey"

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
begin
  if CurStep = ssInstall then
  begin
    Exec(
      ExpandConstant('{sys}\taskkill.exe'),
      '/F /IM CheckMate.exe',
      '',
      SW_HIDE,
      ewWaitUntilTerminated,
      ResultCode
    );
  end;
end;
