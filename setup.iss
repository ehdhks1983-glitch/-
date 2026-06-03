[Setup]
AppName=GIF Maker Pro
AppVersion=1.0.0
DefaultDirName={localappdata}\GIF Maker Pro
DefaultGroupName=GIF Maker Pro
OutputDir=output
OutputBaseFilename=GIFMakerPro_Setup
SetupIconFile=app_icon.ico
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=lowest

[Files]
Source: "dist\GIF Maker Pro.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "app_icon.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "ffmpeg\ffmpeg.exe"; DestDir: "{app}\ffmpeg"; Flags: ignoreversion
Source: "ffmpeg\ffprobe.exe"; DestDir: "{app}\ffmpeg"; Flags: ignoreversion skipifsourcedoesntexist

[Dirs]
Name: "{app}\data"

[Icons]
Name: "{group}\GIF Maker Pro"; Filename: "{app}\GIF Maker Pro.exe"
Name: "{autodesktop}\GIF Maker Pro"; Filename: "{app}\GIF Maker Pro.exe"

[Run]
Filename: "{app}\GIF Maker Pro.exe"; Flags: nowait postinstall skipifsilent
