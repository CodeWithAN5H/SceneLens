; Inno Setup script for the SceneLens Windows installer.
;
; Build the folder shape first, then compile this script:
;
;   build.bat                 (creates dist\SceneLens\)
;   build.bat installer       (builds the app, then the installer)
;
; Output: dist\SceneLens-Setup-<version>.exe
;
; The version block below is generated from scenelens/config.py by
; scripts\make_installer.py, which also runs ISCC; edit config.py instead of
; this file when bumping the version.

#define MyAppName "SceneLens"
; Default version, overridden by build.bat with /DMyAppVersion=<from config.py>
#ifndef MyAppVersion
  #define MyAppVersion "1.0.0"
#endif
#define MyAppPublisher "SceneLens"
#define MyAppURL "https://github.com/scenelens/scenelens"
#define MyAppExeName "SceneLens.exe"
#define MyAppDescription "Universal scene identifier - movie, TV and game frame recognition"

[Setup]
AppId={{7B2F9C41-3E5D-4A68-9C10-2D8F5A6E4B31}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
UninstallDisplayName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}
; The app stores its data in %APPDATA%\SceneLens, so nothing inside {app} is
; user data; uninstalling removes the program only.
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=SceneLens-Setup-{#MyAppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Keep the installer's own file properties consistent with the app.
VersionInfoVersion={#MyAppVersion}.0
VersionInfoProductVersion={#MyAppVersion}.0
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppDescription}
VersionInfoProductName={#MyAppName}
SetupIconFile=..\build\SceneLens\SceneLens.ico
; Per-user install: no UAC prompt, installs to {localappdata}\Programs.
; The app's own data never lives under {app} (it is in %APPDATA%\SceneLens).
PrivilegesRequired=lowest

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; \
    GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; The whole folder build: exe, DLLs, runtime and bundled assets.
Source: "..\dist\SceneLens\*"; \
    DestDir: "{app}"; \
    Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; \
    Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; \
    Description: "{cm:LaunchProgram,{#MyAppName}}"; \
    Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Remove every leftover in {app} so the install folder disappears completely on
; uninstall (nothing there is user data: history/settings live in
; %APPDATA%\SceneLens and are kept). Inno's keyword is filesandordirs.
Type: filesandordirs; Name: "{app}"
; Backstop for anything recreated outside {app} itself.
Type: filesandordirs; Name: "{app}\__pycache__"
