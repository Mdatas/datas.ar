; Inno Setup script — wraps the PyInstaller output (dist\Datas) into Datas-Setup-<version>.exe.
; Per-user install (no admin), Start Menu + optional Desktop shortcut, clean uninstall that
; keeps the user's models unless they choose otherwise.
;   iscc /DAppVersion=0.1.0 installer\windows\datas.iss

#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif
#define AppName "Datas.ar"
#define AppExe "datas.exe"
#define SourceDir "..\..\dist\Datas"

[Setup]
AppId={{C1B98555-CA0F-5131-A621-E87D2BBF05F6}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Datas.ar contributors
AppPublisherURL=https://datas.ar
AppSupportURL=https://github.com/mdatas/datas.ar/issues
DefaultDirName={localappdata}\Datas\app
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\..\dist
OutputBaseFilename=Datas-Setup-{#AppVersion}
SetupIconFile=datas.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "Datas-Serve.cmd"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\Datas-Serve.cmd"; IconFilename: "{app}\{#AppExe}"; WorkingDir: "{app}"
Name: "{group}\{#AppName} (terminal)"; Filename: "cmd.exe"; Parameters: "/k ""{app}\{#AppExe}"" --help"; WorkingDir: "{app}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\Datas-Serve.cmd"; IconFilename: "{app}\{#AppExe}"; Tasks: desktopicon

[Environment]
; makes `datas` available in new terminals
Name: "PATH"; Value: "{app}"; Flags: uninsdeletevalue; Check: NeedsAddPath(ExpandConstant('{app}'))

[Run]
Filename: "{app}\Datas-Serve.cmd"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent shellexec

[UninstallRun]
Filename: "taskkill"; Parameters: "/F /IM llama-server.exe"; Flags: runhidden; RunOnceId: "killllama"
Filename: "taskkill"; Parameters: "/F /IM datas.exe"; Flags: runhidden; RunOnceId: "killdatas"

[Code]
function NeedsAddPath(Param: string): boolean;
var
  OrigPath: string;
begin
  if not RegQueryStringValue(HKEY_CURRENT_USER, 'Environment', 'Path', OrigPath) then
  begin
    Result := True;
    exit;
  end;
  Result := Pos(';' + Uppercase(Param) + ';', ';' + Uppercase(OrigPath) + ';') = 0;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: string;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{localappdata}\Datas');
    if DirExists(DataDir + '\models') then
      if MsgBox('Also delete downloaded models, llama.cpp and settings in ' + DataDir + '?',
                mbConfirmation, MB_YESNO) = IDYES then
        DelTree(DataDir, True, True, True);
  end;
end;
