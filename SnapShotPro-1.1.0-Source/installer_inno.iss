#ifndef AppVersion
  #define AppVersion "1.1.0"
#endif
[Setup]
AppId={{9F572D8A-5F1A-4FBE-B3A9-4E65245BD3C1}
AppName=SnapShot Pro
AppVersion={#AppVersion}
AppPublisher=Lyaritech
AppCopyright=Copyright (C) 2026 SnapShot Pro • Lyaritech
DefaultDirName={localappdata}\Programs\SnapShot Pro
DefaultGroupName=SnapShot Pro
PrivilegesRequired=lowest
OutputDir=dist
OutputBaseFilename=SnapShotPro-{#AppVersion}-Windows-Setup
SetupIconFile=assets\icon.ico
UninstallDisplayIcon={app}\SnapShotPro.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "autostart"; Description: "Start SnapShot Pro automatically on Windows startup (PC restart)"; GroupDescription: "{cm:AdditionalIcons}"
[Files]
#ifdef OneFile
Source: "dist\SnapShotPro.exe"; DestDir: "{app}"; Flags: ignoreversion
#else
Source: "dist\SnapShotPro\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
#endif
[Icons]
Name: "{group}\SnapShot Pro"; Filename: "{app}\SnapShotPro.exe"
Name: "{group}\Uninstall SnapShot Pro"; Filename: "{uninstallexe}"
Name: "{autodesktop}\SnapShot Pro"; Filename: "{app}\SnapShotPro.exe"; Tasks: desktopicon
Name: "{userstartup}\SnapShot Pro"; Filename: "{app}\SnapShotPro.exe"; Tasks: autostart
[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "SnapShot Pro"; ValueData: """{app}\SnapShotPro.exe"""; Flags: uninsdeletevalue; Tasks: autostart
[Run]
Filename: "{app}\SnapShotPro.exe"; Description: "{cm:LaunchProgram,SnapShot Pro}"; Flags: nowait postinstall skipifsilent

