; Inno Setup script — wraps the PyInstaller output (dist\Datas) into Datas-Setup-<version>.exe.
;   * installs into Program Files (asks for admin once) or, if the user prefers, into their own
;     Programs folder without admin — a single dialog at the start
;   * Desktop icon (ticked by default) + Start Menu entry + "Uninstall Datas" entry
;   * uninstall asks: delete the AI models and your notes too, or keep them?
;   iscc /DAppVersion=0.2.0 installer\windows\datas.iss

#ifndef AppVersion
  #define AppVersion "0.2.0"
#endif
#define AppName "Datas.ar"
#define AppExe "Datas.exe"
#define SourceDir "..\..\dist\Datas"

[Setup]
AppId={{C1B98555-CA0F-5131-A621-E87D2BBF05F6}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Datas.ar contributors
AppPublisherURL=https://github.com/Mdatas/datas.ar
AppSupportURL=https://github.com/Mdatas/datas.ar/issues
DefaultDirName={autopf}\Datas
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableDirPage=auto
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog commandline
OutputDir=..\..\dist
OutputBaseFilename=Datas-Setup-{#AppVersion}
SetupIconFile=datas.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"
Name: "{group}\{#AppName} (command line)"; Filename: "cmd.exe"; Parameters: "/k ""{app}\datas-cli.exe"" --help"; WorkingDir: "{app}"; IconFilename: "{app}\{#AppExe}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"; Tasks: desktopicon

[Environment]
; makes `datas-cli` reachable from any terminal (per-user PATH; harmless if unused)
Name: "PATH"; Value: "{app}"; Flags: uninsdeletevalue; Check: NeedsAddPath(ExpandConstant('{app}'))

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "taskkill"; Parameters: "/F /IM llama-server.exe"; Flags: runhidden; RunOnceId: "killllama"
Filename: "taskkill"; Parameters: "/F /IM ggml-rpc-server.exe"; Flags: runhidden; RunOnceId: "killrpc"
Filename: "taskkill"; Parameters: "/F /IM Datas.exe"; Flags: runhidden; RunOnceId: "killdatas"
Filename: "taskkill"; Parameters: "/F /IM datas-cli.exe"; Flags: runhidden; RunOnceId: "killcli"

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
  Msg: string;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{localappdata}\Datas');
    if DirExists(DataDir) then
    begin
      if ActiveLanguage = 'spanish' then
        Msg := 'Datas se desinstaló.' + #13#10#13#10 +
               '¿Querés borrar también las IAs descargadas, tus chats y notas?' + #13#10 +
               '(' + DataDir + ')' + #13#10#13#10 +
               'Sí = borrar todo.   No = conservar la información para una próxima instalación.'
      else
        Msg := 'Datas has been uninstalled.' + #13#10#13#10 +
               'Also delete the downloaded AIs, your chats and notes?' + #13#10 +
               '(' + DataDir + ')' + #13#10#13#10 +
               'Yes = delete everything.   No = keep the information for a future install.';
      if MsgBox(Msg, mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
        DelTree(DataDir, True, True, True);
    end;
  end;
end;
