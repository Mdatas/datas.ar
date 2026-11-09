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
var
  FoundModels, FoundChats: Integer;
  FoundNotes: Boolean;
  PrevRemoved: String;

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

function CountFiles(Dir, Mask: String): Integer;
var
  FR: TFindRec;
begin
  Result := 0;
  if FindFirst(AddBackslash(Dir) + Mask, FR) then
  begin
    try
      repeat
        if (FR.Attributes and FILE_ATTRIBUTE_DIRECTORY) = 0 then Result := Result + 1;
      until not FindNext(FR);
    finally
      FindClose(FR);
    end;
  end;
end;

function CountModels(Dir: String): Integer;
var
  FR: TFindRec;
begin
  Result := CountFiles(Dir, '*.gguf');
  if FindFirst(AddBackslash(Dir) + '*', FR) then
  begin
    try
      repeat
        if ((FR.Attributes and FILE_ATTRIBUTE_DIRECTORY) <> 0) and (FR.Name <> '.') and (FR.Name <> '..') then
          Result := Result + CountFiles(AddBackslash(Dir) + FR.Name, '*.gguf');
      until not FindNext(FR);
    finally
      FindClose(FR);
    end;
  end;
end;

procedure KillDatas;
var
  R: Integer;
begin
  Exec('taskkill', '/F /IM Datas.exe /IM datas-cli.exe /IM llama-server.exe /IM ggml-rpc-server.exe /IM rpc-server.exe', '', SW_HIDE, ewWaitUntilTerminated, R);
end;

{ Remove the PowerShell/venv-based install (Install-Datas.ps1) if present: app files only. }
procedure RemoveScriptInstall;
var
  AppDir: String;
begin
  AppDir := ExpandConstant('{localappdata}\Datas\app');
  if DirExists(AppDir) then
  begin
    DelTree(AppDir, True, True, True);
    PrevRemoved := PrevRemoved + 'script install (' + AppDir + ')' + #13#10;
  end;
  RegDeleteKeyIncludingSubkeys(HKEY_CURRENT_USER, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\Datas.ar');
  DeleteFile(ExpandConstant('{userdesktop}\Datas.ar.lnk'));
  DeleteFile(ExpandConstant('{userprograms}\Datas.ar.lnk'));
end;

{ Remove an earlier Setup.exe install that lives somewhere else (per-user vs all-users). }
procedure RemoveOtherSetupInstall;
var
  Key, Loc, Uninst: String;
  R: Integer;
  Roots: array[0..1] of Integer;
  i: Integer;
begin
  Roots[0] := HKEY_LOCAL_MACHINE;
  Roots[1] := HKEY_CURRENT_USER;
  Key := 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{C1B98555-CA0F-5131-A621-E87D2BBF05F6}_is1';
  for i := 0 to 1 do
  begin
    if RegQueryStringValue(Roots[i], Key, 'InstallLocation', Loc) and
       (CompareText(RemoveBackslash(Loc), RemoveBackslash(ExpandConstant('{app}'))) <> 0) and
       RegQueryStringValue(Roots[i], Key, 'UninstallString', Uninst) then
    begin
      Uninst := RemoveQuotes(Uninst);
      if FileExists(Uninst) then
      begin
        Exec(Uninst, '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /KEEPDATA', '', SW_HIDE, ewWaitUntilTerminated, R);
        PrevRemoved := PrevRemoved + 'previous Datas in ' + Loc + #13#10;
      end;
    end;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  DataDir, Msg: String;
begin
  if CurStep = ssInstall then
  begin
    KillDatas;
    RemoveScriptInstall;
    RemoveOtherSetupInstall;
    DataDir := ExpandConstant('{localappdata}\Datas');
    FoundModels := CountModels(DataDir + '\models');
    FoundChats := CountFiles(DataDir + '\chats', '*.json');
    FoundNotes := FileExists(DataDir + '\memory.md');
  end;
  if (CurStep = ssPostInstall) and ((FoundModels > 0) or (FoundChats > 0) or FoundNotes or (PrevRemoved <> '')) then
  begin
    if ActiveLanguage = 'spanish' then
    begin
      Msg := 'Instalación limpia lista.' + #13#10#13#10;
      if PrevRemoved <> '' then Msg := Msg + 'Se quitó la copia anterior del programa:' + #13#10 + PrevRemoved + #13#10;
      Msg := Msg + 'Tus datos se conservaron y ya están conectados a esta instalación:' + #13#10 +
             '  • ' + IntToStr(FoundModels) + ' IA(s) descargadas' + #13#10 +
             '  • ' + IntToStr(FoundChats) + ' chat(s) guardados' + #13#10;
      if FoundNotes then Msg := Msg + '  • tus notas (memory.md)' + #13#10;
      Msg := Msg + #13#10 + 'Vos decidís qué hacer con ellos desde "Mis IAs" y Ajustes.';
    end
    else
    begin
      Msg := 'Clean install done.' + #13#10#13#10;
      if PrevRemoved <> '' then Msg := Msg + 'The earlier copy of the program was removed:' + #13#10 + PrevRemoved + #13#10;
      Msg := Msg + 'Your data was kept and is already connected to this install:' + #13#10 +
             '  • ' + IntToStr(FoundModels) + ' downloaded AI(s)' + #13#10 +
             '  • ' + IntToStr(FoundChats) + ' saved chat(s)' + #13#10;
      if FoundNotes then Msg := Msg + '  • your notes (memory.md)' + #13#10;
      Msg := Msg + #13#10 + 'You decide what to do with them from "My AIs" and Settings.';
    end;
    MsgBox(Msg, mbInformation, MB_OK);
  end;
end;

function CmdLineParamExists(const Value: string): Boolean;
var
  I: Integer;
begin
  Result := False;
  for I := 1 to ParamCount do
    if CompareText(ParamStr(I), Value) = 0 then
    begin
      Result := True;
      Exit;
    end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: string;
  Msg: string;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    { /KEEPDATA is passed by a newer installer replacing this one: never ask, never delete. }
    if CmdLineParamExists('/KEEPDATA') then Exit;
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
