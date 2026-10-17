; Inno Setup script: wraps the PyInstaller folder into a normal Windows installer.
; Installs per user (no administrator rights needed), adds Start menu / desktop shortcuts and an uninstaller.
;   iscc /DAppVersion=1.0.0 packaging\windows\installer.iss

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{6B0E8B1C-5C7B-4C5E-9E36-3D7F2A9A51C4}
AppName=Manuscript Assistant
AppVersion={#AppVersion}
AppPublisher=Manuscript Assistant contributors
DefaultDirName={localappdata}\Programs\Manuscript Assistant
DefaultGroupName=Manuscript Assistant
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=ManuscriptAssistant-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayName=Manuscript Assistant

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\ManuscriptAssistant\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\Manuscript Assistant"; Filename: "{app}\ManuscriptAssistant.exe"
Name: "{group}\{cm:UninstallProgram,Manuscript Assistant}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Manuscript Assistant"; Filename: "{app}\ManuscriptAssistant.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\ManuscriptAssistant.exe"; Description: "{cm:LaunchProgram,Manuscript Assistant}"; Flags: nowait postinstall skipifsilent
