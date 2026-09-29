#define AppName "Codex Usage Monitor"
#define AppVersion "1.0.0"
#define AppExeName "CodexUsageMonitor.exe"
#define AppIdValue "{5C6581F9-7DA6-4269-B760-9FE3799FABB7}"

[Setup]
AppId={{5C6581F9-7DA6-4269-B760-9FE3799FABB7}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
OutputDir=output
OutputBaseFilename=CodexUsageMonitor-Setup-v1.0.0
SetupIconFile=..\assets\CodexUsageMonitor.ico
UninstallDisplayIcon={app}\{#AppExeName}
UninstallDisplayName={#AppName}
VersionInfoDescription={#AppName} Installer
VersionInfoProductName={#AppName}
VersionInfoVersion=1.0.0.0
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
CloseApplicationsFilter={#AppExeName}
RestartApplications=no
RestartIfNeededByRun=no
UsePreviousAppDir=yes
UsePreviousGroup=yes
MinVersion=10.0

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear un acceso directo en el &escritorio"; GroupDescription: "Accesos directos adicionales:"; Flags: unchecked

[Files]
Source: "..\dist\CodexUsageMonitor\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\{#AppExeName}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Ejecutar {#AppName}"; WorkingDir: "{app}"; Flags: nowait postinstall skipifsilent

[Code]
const
  RunKey = 'Software\Microsoft\Windows\CurrentVersion\Run';
  RunValueName = 'CodexUsageMonitor';

var
  MigrateAutostart: Boolean;

function TryParseCodexMonitorCommand(Value: String; RequireExisting: Boolean;
  var ExecutablePath: String): Boolean;
var
  ClosingQuote: Integer;
  Remainder: String;
begin
  Result := False;
  ExecutablePath := '';
  Value := Trim(Value);
  if Value = '' then
    Exit;

  if Value[1] = '"' then
  begin
    ClosingQuote := Pos('"', Copy(Value, 2, Length(Value) - 1));
    if ClosingQuote = 0 then
      Exit;
    ClosingQuote := ClosingQuote + 1;
    ExecutablePath := Copy(Value, 2, ClosingQuote - 2);
    Remainder := Trim(Copy(Value, ClosingQuote + 1, Length(Value)));
    if Remainder <> '' then
      Exit;
  end
  else
    ExecutablePath := Value;

  if CompareText(ExtractFileName(ExecutablePath), '{#AppExeName}') <> 0 then
    Exit;
  if RequireExisting and (not FileExists(ExecutablePath)) then
    Exit;

  Result := True;
end;

function SameExecutablePath(LeftPath, RightPath: String): Boolean;
begin
  Result := CompareText(ExpandFileName(LeftPath), ExpandFileName(RightPath)) = 0;
end;

function InitializeSetup: Boolean;
var
  ExistingCommand: String;
  ExistingExecutable: String;
begin
  MigrateAutostart := False;
  if RegQueryStringValue(HKCU, RunKey, RunValueName, ExistingCommand) then
    MigrateAutostart := TryParseCodexMonitorCommand(
      ExistingCommand, True, ExistingExecutable);
  Result := True;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  InstalledExecutable: String;
begin
  if (CurStep = ssPostInstall) and MigrateAutostart then
  begin
    InstalledExecutable := ExpandConstant('{app}\{#AppExeName}');
    RegWriteStringValue(HKCU, RunKey, RunValueName,
      '"' + InstalledExecutable + '"');
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ExistingCommand: String;
  ExistingExecutable: String;
  InstalledExecutable: String;
begin
  if CurUninstallStep <> usUninstall then
    Exit;

  if not RegQueryStringValue(HKCU, RunKey, RunValueName, ExistingCommand) then
    Exit;
  if not TryParseCodexMonitorCommand(
    ExistingCommand, False, ExistingExecutable) then
    Exit;

  InstalledExecutable := ExpandConstant('{app}\{#AppExeName}');
  if SameExecutablePath(ExistingExecutable, InstalledExecutable) then
    RegDeleteValue(HKCU, RunKey, RunValueName);
end;
