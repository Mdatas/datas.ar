; Inno Setup script — the ONE file a Windows user gets: Datas-Setup-<version>.exe
;   * opens a small window: Install · Repair · Uninstall · Exit, plus "Read me"
;   * Install/Repair: stops Datas, removes ANY earlier copy of the program (never the data),
;     installs into the user's Programs folder (no admin password needed), Desktop + Start Menu
;     icons, then shows what was kept (AIs, chats, notes) — no other questions asked
;   * Uninstall: "delete everything" or "keep my AIs, chats and notes"
;   iscc /DAppVersion=0.6.1 installer\windows\datas.iss

#ifndef AppVersion
  #define AppVersion "0.6.1"
#endif
#define AppName "Datas.ar"
#define AppExe "Datas.exe"
#define SourceDir "..\..\dist\Datas"
#define UninstKey "Software\Microsoft\Windows\CurrentVersion\Uninstall\{C1B98555-CA0F-5131-A621-E87D2BBF05F6}_is1"

[Setup]
AppId={{C1B98555-CA0F-5131-A621-E87D2BBF05F6}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Datas.ar contributors
AppPublisherURL=https://github.com/Mdatas/datas.ar
AppSupportURL=https://github.com/Mdatas/datas.ar/issues
; {autopf} = C:\Users\<you>\AppData\Local\Programs\Datas (Windows' per-user "Program Files");
; power users can still run Datas-Setup.exe /ALLUSERS to install into C:\Program Files.
DefaultDirName={autopf}\Datas
DefaultGroupName={#AppName}
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=commandline
DisableWelcomePage=yes
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableReadyPage=yes
DisableFinishedPage=no
ShowLanguageDialog=auto
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

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"

[Environment]
; makes `datas-cli` reachable from any terminal (per-user PATH; harmless if unused)
Name: "PATH"; Value: "{app}"; Flags: uninsdeletevalue; Check: NeedsAddPath(ExpandConstant('{app}'))

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
; an automatic update started by Datas itself ("Install now") opens Datas again when done
Filename: "{app}\{#AppExe}"; Flags: nowait; Check: Relaunch

[UninstallRun]
Filename: "taskkill"; Parameters: "/F /IM llama-server.exe"; Flags: runhidden; RunOnceId: "killllama"
Filename: "taskkill"; Parameters: "/F /IM ggml-rpc-server.exe"; Flags: runhidden; RunOnceId: "killrpc"
Filename: "taskkill"; Parameters: "/F /IM Datas.exe"; Flags: runhidden; RunOnceId: "killdatas"
Filename: "taskkill"; Parameters: "/F /IM datas-cli.exe"; Flags: runhidden; RunOnceId: "killcli"

[Code]
var
  FoundModels, FoundChats: Integer;
  FoundNotes: Boolean;
  PrevRemoved, Mode, Summary: String;

function ES: Boolean;
begin
  Result := ActiveLanguage = 'spanish';
end;

function T(En, Sp: String): String;
begin
  if ES then Result := Sp else Result := En;
end;

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

function DataDir: String;
begin
  Result := ExpandConstant('{localappdata}\Datas');
end;

procedure InventoryData;
begin
  FoundModels := CountModels(DataDir + '\models');
  FoundChats := CountFiles(DataDir + '\chats', '*.json');
  FoundNotes := FileExists(DataDir + '\memory.md');
end;

function DataSummary: String;
begin
  Result := '';
  if FoundModels > 0 then Result := Result + IntToStr(FoundModels) + T(' downloaded AI(s)', ' IA(s) descargadas');
  if FoundChats > 0 then
  begin
    if Result <> '' then Result := Result + ', ';
    Result := Result + IntToStr(FoundChats) + T(' saved chat(s)', ' chat(s) guardados');
  end;
  if FoundNotes then
  begin
    if Result <> '' then Result := Result + ', ';
    Result := Result + T('your notes', 'tus notas');
  end;
end;

{ Is there a Datas program on this PC? (Setup.exe install, per-user or all-users, or the old script install) }
function FindInstalled(var Location, Version, Uninst: String): Boolean;
var
  Roots: array[0..1] of Integer;
  i: Integer;
begin
  Result := False;
  Roots[0] := HKEY_CURRENT_USER;
  Roots[1] := HKEY_LOCAL_MACHINE;
  for i := 0 to 1 do
    if RegQueryStringValue(Roots[i], '{#UninstKey}', 'UninstallString', Uninst) then
    begin
      Uninst := RemoveQuotes(Uninst);
      if FileExists(Uninst) then
      begin
        RegQueryStringValue(Roots[i], '{#UninstKey}', 'InstallLocation', Location);
        RegQueryStringValue(Roots[i], '{#UninstKey}', 'DisplayVersion', Version);
        Result := True;
        Exit;
      end;
    end;
  if DirExists(DataDir + '\app') then
  begin
    Location := DataDir + '\app';
    Version := T('(older script install)', '(instalación antigua por script)');
    Uninst := '';
    Result := True;
  end;
end;

procedure KillDatas;
var
  R: Integer;
begin
  Exec('taskkill', '/F /IM Datas.exe /IM datas-cli.exe /IM llama-server.exe /IM ggml-rpc-server.exe /IM rpc-server.exe', '', SW_HIDE, ewWaitUntilTerminated, R);
end;

{ Shortcuts the app itself created (one per installed AI) are listed in <data>\shortcuts.txt }
procedure RemoveAppShortcuts;
var
  Lines: TArrayOfString;
  i: Integer;
begin
  if LoadStringsFromFile(DataDir + '\shortcuts.txt', Lines) then
    for i := 0 to GetArrayLength(Lines) - 1 do
      if (Trim(Lines[i]) <> '') and FileExists(Trim(Lines[i])) then DeleteFile(Trim(Lines[i]));
  DeleteFile(DataDir + '\shortcuts.txt');
end;

{ Remove the old PowerShell/venv-based install if present: program files only. }
procedure RemoveScriptInstall;
var
  AppDir: String;
begin
  AppDir := DataDir + '\app';
  if DirExists(AppDir) then
  begin
    DelTree(AppDir, True, True, True);
    PrevRemoved := PrevRemoved + AppDir + #13#10;
  end;
  RegDeleteKeyIncludingSubkeys(HKEY_CURRENT_USER, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\Datas.ar');
  DeleteFile(ExpandConstant('{userdesktop}\Datas.ar.lnk'));
  DeleteFile(ExpandConstant('{userprograms}\Datas.ar.lnk'));
end;

{ Remove an earlier Setup.exe install that lives somewhere else (e.g. all-users in Program Files). }
procedure RemoveOtherSetupInstall;
var
  Key, Loc, Uninst: String;
  R: Integer;
  Roots: array[0..1] of Integer;
  i: Integer;
begin
  Roots[0] := HKEY_LOCAL_MACHINE;
  Roots[1] := HKEY_CURRENT_USER;
  Key := '{#UninstKey}';
  for i := 0 to 1 do
  begin
    if RegQueryStringValue(Roots[i], Key, 'InstallLocation', Loc) and
       (CompareText(RemoveBackslash(Loc), RemoveBackslash(ExpandConstant('{app}'))) <> 0) and
       RegQueryStringValue(Roots[i], Key, 'UninstallString', Uninst) then
    begin
      Uninst := RemoveQuotes(Uninst);
      if FileExists(Uninst) then
      begin
        { ShellExec so an all-users copy can ask for the one admin click it needs }
        ShellExec('', Uninst, '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /KEEPDATA', '', SW_HIDE, ewWaitUntilTerminated, R);
        PrevRemoved := PrevRemoved + Loc + #13#10;
      end;
    end;
  end;
end;

{ ---------- Uninstall from the launcher window ---------- }
procedure DoUninstall(Purge: Boolean);
var
  Loc, Ver, Uninst, Msg: String;
  R: Integer;
begin
  KillDatas;
  if FindInstalled(Loc, Ver, Uninst) and (Uninst <> '') then
    ShellExec('', Uninst, '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /KEEPDATA', '', SW_HIDE, ewWaitUntilTerminated, R);
  RemoveScriptInstall;
  RemoveAppShortcuts;
  if Purge then
  begin
    DelTree(DataDir, True, True, True);
    Msg := T('Datas and all its data were removed from this PC.',
             'Datas y todos sus datos se quitaron de esta PC.');
  end
  else
    Msg := T('Datas was removed. Your AIs, chats and notes were kept in' + #13#10 + DataDir + #13#10 + 'and will be picked up again if you reinstall.',
             'Datas se quitó. Tus IAs, chats y notas quedaron en' + #13#10 + DataDir + #13#10 + 'y se recuperan si volvés a instalar.');
  MsgBox(Msg, mbInformation, MB_OK);
end;

{ Three clear buttons instead of Yes/No/Cancel. Returns 1 = keep data, 2 = delete everything, 0 = back. }
function AskUninstall: Integer;
var
  F: TSetupForm;
  L: TNewStaticText;
  BKeep, BAll, BBack: TNewButton;
  R: Integer;
begin
  F := CreateCustomForm(ScaleX(460), ScaleY(190), True, True);
  try
    F.Caption := T('Uninstall Datas', 'Desinstalar Datas');
    F.CenterOnShow := True;
    L := TNewStaticText.Create(F);
    L.Parent := F;
    L.Left := ScaleX(20); L.Top := ScaleY(16); L.Width := ScaleX(420);
    L.WordWrap := True; L.AutoSize := True;
    L.Caption := T('The program will be removed. What about your downloaded AIs, chats and notes?' + #13#10 + '(' + DataSummary + ')',
                   'El programa se quita. ¿Qué hacemos con tus IAs descargadas, chats y notas?' + #13#10 + '(' + DataSummary + ')');
    BKeep := TNewButton.Create(F); BKeep.Parent := F;
    BKeep.Left := ScaleX(20); BKeep.Top := ScaleY(80); BKeep.Width := ScaleX(420); BKeep.Height := ScaleY(30);
    BKeep.Caption := T('Uninstall, but KEEP my AIs, chats and notes', 'Desinstalar, pero CONSERVAR mis IAs, chats y notas');
    BKeep.ModalResult := mrNo;
    BAll := TNewButton.Create(F); BAll.Parent := F;
    BAll.Left := ScaleX(20); BAll.Top := ScaleY(116); BAll.Width := ScaleX(420); BAll.Height := ScaleY(30);
    BAll.Caption := T('Uninstall and DELETE everything', 'Desinstalar y BORRAR todo');
    BAll.ModalResult := mrYes;
    BBack := TNewButton.Create(F); BBack.Parent := F;
    BBack.Left := ScaleX(340); BBack.Top := ScaleY(152); BBack.Width := ScaleX(100); BBack.Height := ScaleY(26);
    BBack.Caption := T('Back', 'Volver');
    BBack.ModalResult := mrCancel; BBack.Cancel := True;
    F.ActiveControl := BKeep;
    R := F.ShowModal;
    if R = mrNo then Result := 1 else if R = mrYes then Result := 2 else Result := 0;
  finally
    F.Free;
  end;
end;

procedure ShowReadme;
var
  F: TSetupForm;
  M: TNewMemo;
  B: TNewButton;
begin
  F := CreateCustomForm(ScaleX(560), ScaleY(420), True, True);
  try
    F.Caption := T('Read me — Datas.ar', 'Leeme — Datas.ar');
    F.CenterOnShow := True;
    M := TNewMemo.Create(F);
    M.Parent := F;
    M.Left := ScaleX(12); M.Top := ScaleY(12); M.Width := ScaleX(536); M.Height := ScaleY(360);
    M.ReadOnly := True; M.ScrollBars := ssVertical; M.WordWrap := True;
    M.Text := T(
      'DATAS.AR ' + '{#AppVersion}' + ' — local AI for everyone' + #13#10#13#10 +
      'WHAT IT IS' + #13#10 +
      'Datas looks at your PC (memory, graphics card, processor) and picks the best free, open AI model it can run without freezing your computer. Downloads it, runs it, done. Everything happens on your PC: nothing you type leaves it unless you turn on internet access for a session.' + #13#10#13#10 +
      'THE BUTTONS' + #13#10 +
      '• Install — installs Datas (or replaces an older copy with a clean one). Your downloaded AIs, chats and notes are always kept and connected to the new install.' + #13#10 +
      '• Repair — same as Install: puts the program files and icons back in order. Use it if Datas stopped opening.' + #13#10 +
      '• Uninstall — removes the program. You choose: keep your AIs, chats and notes for later, or delete everything.' + #13#10 +
      '• Exit — closes this window without changing anything.' + #13#10#13#10 +
      'WHERE THINGS GO' + #13#10 +
      'Program: your Programs folder (AppData\Local\Programs\Datas). No administrator password needed.' + #13#10 +
      'Your data (AIs, chats, notes, settings, logs): AppData\Local\Datas.' + #13#10 +
      'Icons: Desktop and Start Menu. Each AI you install gets its own Desktop icon too.' + #13#10#13#10 +
      'FIRST RUN' + #13#10 +
      'Click Run, say what you want the AI for, and accept the recommendation. The first start also downloads the engine (llama.cpp) and the AI model: a few minutes depending on your connection.' + #13#10#13#10 +
      'PRIVACY' + #13#10 +
      'Remember mode keeps chats and notes so the AI gets to know you. Forget mode saves nothing. You switch anytime in Settings.' + #13#10#13#10 +
      'HELP, SOURCE CODE AND CREDITS' + #13#10 +
      'https://github.com/Mdatas/datas.ar  (free software, GPL-3.0-or-later)' + #13#10 +
      'Windows SmartScreen may warn about an unknown publisher the first time: "More info" → "Run anyway". The installer is not signed yet.',

      'DATAS.AR ' + '{#AppVersion}' + ' — IA local para todos' + #13#10#13#10 +
      'QUÉ ES' + #13#10 +
      'Datas mira tu PC (memoria, placa de video, procesador) y elige el mejor modelo de IA libre y abierto que puede correr sin colgar la computadora. Lo descarga, lo ejecuta, listo. Todo pasa en tu PC: nada de lo que escribís sale de ahí salvo que actives internet para una sesión.' + #13#10#13#10 +
      'LOS BOTONES' + #13#10 +
      '• Instalar — instala Datas (o reemplaza una copia anterior por una limpia). Tus IAs descargadas, chats y notas se conservan siempre y quedan conectados a la nueva instalación.' + #13#10 +
      '• Reparar — igual que Instalar: vuelve a poner en orden los archivos del programa y los íconos. Usalo si Datas dejó de abrir.' + #13#10 +
      '• Desinstalar — quita el programa. Elegís: conservar tus IAs, chats y notas para después, o borrar todo.' + #13#10 +
      '• Salir — cierra esta ventana sin cambiar nada.' + #13#10#13#10 +
      'DÓNDE VA CADA COSA' + #13#10 +
      'Programa: tu carpeta de programas (AppData\Local\Programs\Datas). No hace falta clave de administrador.' + #13#10 +
      'Tus datos (IAs, chats, notas, ajustes, registros): AppData\Local\Datas.' + #13#10 +
      'Íconos: Escritorio y menú Inicio. Cada IA que instalás también tiene su ícono en el Escritorio.' + #13#10#13#10 +
      'PRIMER USO' + #13#10 +
      'Tocá Ejecutar, decí para qué querés la IA y aceptá la recomendación. La primera vez también se descarga el motor (llama.cpp) y el modelo: unos minutos según tu conexión.' + #13#10#13#10 +
      'PRIVACIDAD' + #13#10 +
      'El modo Recordar guarda chats y notas para que la IA te conozca. El modo Olvidar no guarda nada. Lo cambiás cuando quieras en Ajustes.' + #13#10#13#10 +
      'AYUDA, CÓDIGO FUENTE Y CRÉDITOS' + #13#10 +
      'https://github.com/Mdatas/datas.ar  (software libre, GPL-3.0-or-later)' + #13#10 +
      'Windows SmartScreen puede avisar de un editor desconocido la primera vez: "Más información" → "Ejecutar de todas formas". El instalador todavía no está firmado.');
    B := TNewButton.Create(F); B.Parent := F;
    B.Left := ScaleX(448); B.Top := ScaleY(382); B.Width := ScaleX(100); B.Height := ScaleY(26);
    B.Caption := T('Close', 'Cerrar'); B.ModalResult := mrOk; B.Default := True; B.Cancel := True;
    F.ActiveControl := B;
    F.ShowModal;
  finally
    F.Free;
  end;
end;

{ ---------- The launcher window: Install · Repair · Uninstall · Exit · Read me ---------- }
function ShowLauncher: Boolean;
var
  F: TSetupForm;
  Title, Status: TNewStaticText;
  BInstall, BRepair, BUninstall, BExit, BReadme: TNewButton;
  Loc, Ver, Uninst, St: String;
  Installed: Boolean;
  R, Choice: Integer;
begin
  Result := False;
  Installed := FindInstalled(Loc, Ver, Uninst);
  InventoryData;
  F := CreateCustomForm(ScaleX(460), ScaleY(300), True, True);
  try
    F.Caption := 'Datas.ar ' + '{#AppVersion}';
    F.CenterOnShow := True;

    Title := TNewStaticText.Create(F); Title.Parent := F;
    Title.Left := ScaleX(20); Title.Top := ScaleY(16); Title.AutoSize := True;
    Title.Font.Size := 14; Title.Font.Style := [fsBold];
    Title.Caption := T('Datas.ar — local AI for everyone', 'Datas.ar — IA local para todos');

    Status := TNewStaticText.Create(F); Status.Parent := F;
    Status.Left := ScaleX(20); Status.Top := ScaleY(50); Status.Width := ScaleX(420);
    Status.WordWrap := True; Status.AutoSize := True;
    if Installed then
    begin
      St := T('Installed on this PC: version ' + Ver + ' in ' + Loc, 'Instalado en esta PC: versión ' + Ver + ' en ' + Loc);
      if DataSummary <> '' then St := St + #13#10 + T('Your data: ', 'Tus datos: ') + DataSummary;
    end
    else
    begin
      St := T('Datas is not installed on this PC yet.', 'Datas todavía no está instalado en esta PC.');
      if DataSummary <> '' then St := St + #13#10 + T('Found data from an earlier install (it will be kept): ', 'Hay datos de una instalación anterior (se conservan): ') + DataSummary;
    end;
    Status.Caption := St;

    BInstall := TNewButton.Create(F); BInstall.Parent := F;
    BInstall.Left := ScaleX(20); BInstall.Top := ScaleY(112); BInstall.Width := ScaleX(205); BInstall.Height := ScaleY(44);
    if Installed then BInstall.Caption := T('Install again (clean)', 'Instalar de nuevo (limpio)')
    else BInstall.Caption := T('Install', 'Instalar');
    BInstall.ModalResult := mrOk; BInstall.Default := True;

    BRepair := TNewButton.Create(F); BRepair.Parent := F;
    BRepair.Left := ScaleX(235); BRepair.Top := ScaleY(112); BRepair.Width := ScaleX(205); BRepair.Height := ScaleY(44);
    BRepair.Caption := T('Repair', 'Reparar'); BRepair.ModalResult := mrRetry; BRepair.Enabled := Installed;

    BUninstall := TNewButton.Create(F); BUninstall.Parent := F;
    BUninstall.Left := ScaleX(20); BUninstall.Top := ScaleY(166); BUninstall.Width := ScaleX(205); BUninstall.Height := ScaleY(44);
    BUninstall.Caption := T('Uninstall', 'Desinstalar'); BUninstall.ModalResult := mrAbort; BUninstall.Enabled := Installed;

    BExit := TNewButton.Create(F); BExit.Parent := F;
    BExit.Left := ScaleX(235); BExit.Top := ScaleY(166); BExit.Width := ScaleX(205); BExit.Height := ScaleY(44);
    BExit.Caption := T('Exit', 'Salir'); BExit.ModalResult := mrCancel; BExit.Cancel := True;

    BReadme := TNewButton.Create(F); BReadme.Parent := F;
    BReadme.Left := ScaleX(20); BReadme.Top := ScaleY(240); BReadme.Width := ScaleX(120); BReadme.Height := ScaleY(28);
    BReadme.Caption := T('Read me', 'Leeme'); BReadme.ModalResult := mrIgnore;

    F.ActiveControl := BInstall;
    repeat
      R := F.ShowModal;
      if R = mrIgnore then ShowReadme
      else if R = mrAbort then
      begin
        Choice := AskUninstall;
        if Choice = 1 then begin DoUninstall(False); Exit; end;
        if Choice = 2 then begin DoUninstall(True); Exit; end;
        R := mrIgnore; { back to the launcher }
      end;
    until R <> mrIgnore;
    if R = mrOk then begin Mode := 'install'; Result := True; end
    else if R = mrRetry then begin Mode := 'repair'; Result := True; end;
  finally
    F.Free;
  end;
end;

function Relaunch: Boolean;
begin
  Result := WizardSilent and (ExpandConstant('{param:relaunch|0}') = '1');
end;

function InitializeSetup: Boolean;
begin
  { /VERYSILENT (used by a newer Setup replacing this one, or by scripts) skips the window }
  if WizardSilent then begin Mode := 'install'; Result := True; end
  else Result := ShowLauncher;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssInstall then
  begin
    KillDatas;
    RemoveScriptInstall;
    RemoveOtherSetupInstall;
    InventoryData;
  end;
  if CurStep = ssPostInstall then
  begin
    if Mode = 'repair' then Summary := T('Datas was repaired.', 'Datas se reparó.')
    else Summary := T('Datas is installed.', 'Datas quedó instalado.');
    if PrevRemoved <> '' then
      Summary := Summary + #13#10 + T('The earlier copy of the program was removed: ', 'Se quitó la copia anterior del programa: ') + Trim(PrevRemoved);
    if DataSummary <> '' then
      Summary := Summary + #13#10 + T('Kept and connected to this install: ', 'Se conservó y quedó conectado: ') + DataSummary + '.' + #13#10 +
                 T('You decide what to do with it from "My AIs" and Settings.', 'Vos decidís qué hacer desde "Mis IAs" y Ajustes.');
    Summary := Summary + #13#10#13#10 + T('Open Datas from the Desktop icon or the Start Menu.', 'Abrí Datas desde el ícono del Escritorio o el menú Inicio.');
  end;
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if (CurPageID = wpFinished) and (Summary <> '') then
  begin
    WizardForm.FinishedLabel.Caption := Summary;
    WizardForm.FinishedLabel.AdjustHeight;
    WizardForm.RunList.Top := WizardForm.FinishedLabel.Top + WizardForm.FinishedLabel.Height + ScaleY(12);
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
  Msg: string;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    { /KEEPDATA: another installer is replacing this copy, or the launcher already asked. Never ask, never delete. }
    if CmdLineParamExists('/KEEPDATA') then Exit;
    if CmdLineParamExists('/PURGEDATA') then begin DelTree(DataDir, True, True, True); Exit; end;
    { Started from Settings → Apps: ask here. }
    if DirExists(DataDir) then
    begin
      InventoryData;
      Msg := T('Datas has been uninstalled.' + #13#10#13#10 + 'Also delete the downloaded AIs, your chats and notes? (' + DataSummary + ')' + #13#10 + DataDir + #13#10#13#10 + 'Yes = delete everything.   No = keep them for a future install.',
               'Datas se desinstaló.' + #13#10#13#10 + '¿Borrar también las IAs descargadas, tus chats y notas? (' + DataSummary + ')' + #13#10 + DataDir + #13#10#13#10 + 'Sí = borrar todo.   No = conservarlos para una próxima instalación.');
      if MsgBox(Msg, mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
        DelTree(DataDir, True, True, True);
    end;
  end;
end;
