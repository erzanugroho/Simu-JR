#define MyAppName "Simu JR"
#ifndef MyAppVersion
#define MyAppVersion "1.0.0"
#endif
#ifndef ProjectRoot
#define ProjectRoot "..\.."
#endif
#ifndef OutputDir
#define OutputDir "..\..\dist-installer"
#endif

[Setup]
AppId={{7B49EB2C-2BF3-4798-A695-5100A0000001}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=Simu JR
DefaultDirName={autopf}\Simu JR
DefaultGroupName=Simu JR
DisableProgramGroupPage=yes
OutputDir={#OutputDir}
OutputBaseFilename=SimuJR-Setup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
UninstallDisplayIcon={app}\run-simujr.bat

[Files]
Source: "{#OutputDir}\payload\app\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Dirs]
Name: "{commonappdata}\SimuJR"
Name: "{commonappdata}\SimuJR\results"
Name: "{commonappdata}\SimuJR\temp_uploads"
Name: "{commonappdata}\SimuJR\logs"
Name: "{commonappdata}\SimuJR\rag"
Name: "{commonappdata}\SimuJR\rag_backup"

[Icons]
Name: "{group}\Simu JR"; Filename: "{app}\run-simujr.bat"; WorkingDir: "{app}"
Name: "{group}\Configure Simu JR"; Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -File ""{app}\tools\installer\configure-simujr.ps1"" -InstallDir ""{app}"" -DataRoot ""{commonappdata}\SimuJR"""; WorkingDir: "{app}"
Name: "{group}\Update RAG Data"; Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -File ""{app}\tools\installer\update-rag-data-pack.ps1"""; WorkingDir: "{app}"
Name: "{autodesktop}\Simu JR"; Filename: "{app}\run-simujr.bat"; WorkingDir: "{app}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Run]
Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -File ""{app}\tools\installer\configure-simujr.ps1"" -InstallDir ""{app}"" -DataRoot ""{commonappdata}\SimuJR"""; Flags: runhidden

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
