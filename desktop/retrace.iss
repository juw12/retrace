; Retrace for Windows - per-user installer (no admin rights). build.py compiles it with:
;   iscc /DAppVersion=1.0.0 /DSourceDir=<dist\Retrace> /DOutputDir=<dist> /DIconFile=<build\retrace.ico> retrace.iss
; Installs to %LOCALAPPDATA%\Programs\Retrace, adds Retrace to the Start menu (and optionally the desktop) and lists it
; in Settings > Apps. The window keeps its data (what you saved in it) in %LOCALAPPDATA%\Retrace, which
; uninstalling leaves in place so a reinstall finds it again.

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#ifndef SourceDir
  #define SourceDir "dist\Retrace"
#endif
#ifndef OutputDir
  #define OutputDir "dist"
#endif
#ifndef IconFile
  #define IconFile "build\retrace.ico"
#endif

[Setup]
AppId={{E81247BA-698B-569E-A6DE-E1E1C366EEFB}
AppName=Retrace
AppVersion={#AppVersion}
AppVerName=Retrace {#AppVersion}
AppPublisher=Juwen Lie
AppPublisherURL=https://juw12.github.io/retrace/
AppSupportURL=https://github.com/juw12/retrace
DefaultDirName={autopf}\Retrace
DisableDirPage=yes
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir={#OutputDir}
OutputBaseFilename=Retrace-Windows-Setup
SetupIconFile={#IconFile}
UninstallDisplayIcon={app}\Retrace.exe
UninstallDisplayName=Retrace
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=no
SetupLogging=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userprograms}\Retrace"; Filename: "{app}\Retrace.exe"; Comment: "Find the AI, prompt, model, tools and settings behind an image"
Name: "{userdesktop}\Retrace"; Filename: "{app}\Retrace.exe"; Comment: "Find the AI, prompt, model, tools and settings behind an image"; Tasks: desktopicon

[Run]
Filename: "{app}\Retrace.exe"; Description: "{cm:LaunchProgram,Retrace}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{app}\Retrace.exe"; Parameters: "--stop"; Flags: runhidden waituntilterminated; RunOnceId: "StopRetrace"

[Code]
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
begin
  Result := '';
  { Updating: close an open Retrace window first so its files can be replaced. }
  if FileExists(ExpandConstant('{app}\Retrace.exe')) then
    Exec(ExpandConstant('{app}\Retrace.exe'), '--stop', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;
