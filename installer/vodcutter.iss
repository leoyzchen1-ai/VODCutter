; VODCutter installer. Compiled by build.ps1:  ISCC /DAppVersion=x.y.z vodcutter.iss
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppName=VODCutter
AppVersion={#AppVersion}
AppPublisher=leoyz
DefaultDirName={localappdata}\VODCutter
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=Output
OutputBaseFilename=VODCutterSetup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
ChangesEnvironment=yes
InfoAfterFile=payload\POSTINSTALL.txt

[Types]
Name: "cpu"; Description: "CPU only (works everywhere)"
Name: "gpufull"; Description: "With NVIDIA GPU acceleration"
Name: "custom"; Description: "Custom"; Flags: iscustom

[Components]
Name: "core"; Description: "VODCutter pipeline (required)"; Types: cpu gpufull custom; Flags: fixed
Name: "gpu"; Description: "GPU acceleration (NVIDIA) - requires an NVIDIA GPU (~1 GB)"; Types: gpufull

[Files]
Source: "payload\python\*"; DestDir: "{app}\python"; Flags: recursesubdirs ignoreversion; Components: core
Source: "payload\cutter.cmd"; DestDir: "{app}"; Flags: ignoreversion; Components: core
Source: "..\resolve_cut.lua"; DestDir: "{userappdata}\Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts\Utility"; Flags: ignoreversion uninsneveruninstall; Components: core
Source: "payload\config-default.toml"; DestDir: "{userappdata}\cutter"; DestName: "config.toml"; Flags: onlyifdoesntexist uninsneveruninstall; Components: core
Source: "payload\gpu\nvidia\*"; DestDir: "{app}\python\Lib\site-packages\nvidia"; Flags: recursesubdirs ignoreversion; Components: gpu

[Registry]
Root: HKCU; Subkey: "Environment"; ValueType: expandsz; ValueName: "Path"; ValueData: "{olddata};{app}"; Check: NeedsAddPath(ExpandConstant('{app}'))

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
function NeedsAddPath(Param: string): boolean;
var OrigPath: string;
begin
  if not RegQueryStringValue(HKCU, 'Environment', 'Path', OrigPath) then
  begin
    Result := True;
    exit;
  end;
  Result := Pos(';' + Uppercase(Param) + ';', ';' + Uppercase(OrigPath) + ';') = 0;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var P, App: string;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    if RegQueryStringValue(HKCU, 'Environment', 'Path', P) then
    begin
      App := ExpandConstant('{app}');
      StringChangeEx(P, ';' + App, '', True);
      StringChangeEx(P, App + ';', '', True);
      StringChangeEx(P, App, '', True);
      RegWriteExpandStringValue(HKCU, 'Environment', 'Path', P);
    end;
  end;
end;
