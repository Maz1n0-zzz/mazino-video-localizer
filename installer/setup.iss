; Inno Setup script — gộp 3 bundle PyInstaller (pyvideotrans_cli, vsr_cli,
; web_server) + ffmpeg dùng chung + model whisper medium (offline) thành 1
; setup.exe cho Windows.
;
; Script này KHÔNG tự build gì — nó chỉ đóng gói những gì đã có sẵn trong 1
; thư mục "staging" được chuẩn bị trước (bởi GitHub Actions workflow, xem
; .github/workflows/build-windows-installer.yml). Layout staging mong đợi,
; truyền vào qua biến /DStageDir=<path> khi gọi ISCC:
;
;   <StageDir>/
;     web_server/          <- toàn bộ nội dung dist/web_server (từ web_server.spec)
;     pyvideotrans/         <- toàn bộ nội dung dist/pyvideotrans_cli (từ pyvideotrans_cli.spec)
;     vsr/                   <- toàn bộ nội dung dist/vsr_cli (từ vsr_cli.spec)
;     ffmpeg/ffmpeg.exe, ffprobe.exe   <- ffmpeg tĩnh có libass (dùng chung, orchestrator.py gọi trực tiếp)
;     pvt_models/models--Systran--faster-whisper-medium/...   <- model whisper đã tải sẵn (offline)
;
; Layout cài đặt cuối (khớp orchestrator.py FROZEN branch, xem comment trong
; orchestrator.py): web_server.exe PHẢI nằm ở {app} top-level, các exe con
; nằm trong {app}\pyvideotrans\ và {app}\vsr\.

#ifndef StageDir
  #define StageDir "..\dist_stage"
#endif

[Setup]
AppId={{6F1B2E3A-6C2E-4B7B-9B0A-8C7B6C6F2E10}}
AppName=Mazino Video Localizer
AppVersion=1.0.0
AppPublisher=Mazino
; KHÔNG dùng {autopf} (Program Files) — app tự viết cfg.json/params.json/
; tmp/logs/models trực tiếp vào chính thư mục cài đặt lúc chạy (không tách
; riêng thư mục "user data" như convention Windows thường), nên cần 1 nơi
; user thường có quyền ghi không cần admin. {localappdata} khớp với
; PrivilegesRequired=lowest (cài đặt per-user, không cần elevation).
DefaultDirName={localappdata}\MazinoVideoLocalizer
DefaultGroupName=Mazino Video Localizer
DisableProgramGroupPage=yes
OutputDir=..\dist_installer
OutputBaseFilename=MazinoVideoLocalizer-Setup
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
; Ứng dụng cá nhân, không ký code — người dùng sẽ thấy cảnh báo
; SmartScreen khi chạy setup.exe lần đầu, chấp nhận được vì dùng nội bộ.

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
; web_server + web_static ở top-level {app}
Source: "{#StageDir}\web_server\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

; pyvideotrans onedir bundle
Source: "{#StageDir}\pyvideotrans\*"; DestDir: "{app}\pyvideotrans"; Flags: recursesubdirs createallsubdirs ignoreversion

; video-subtitle-remover onedir bundle (đã kèm sẵn model sttn-auto/big-lama/
; ProPainter + ffmpeg riêng của nó bên trong, xem vsr_cli.spec)
Source: "{#StageDir}\vsr\*"; DestDir: "{app}\vsr"; Flags: recursesubdirs createallsubdirs ignoreversion

; ffmpeg dùng chung cho orchestrator.py (build_fixed_ass/compose_final) —
; bản tĩnh có libass, KHÁC với ffmpeg riêng của vsr (chỉ dùng để transcode)
Source: "{#StageDir}\ffmpeg\*"; DestDir: "{app}\ffmpeg"; Flags: recursesubdirs createallsubdirs ignoreversion

; Model whisper "medium" tải sẵn — đặt vào đúng cache dir mà faster-whisper/
; huggingface_hub kỳ vọng, dưới pyvideotrans/models/ (ROOT_DIR khi FROZEN =
; thư mục chứa pyvideotrans_cli.exe, xem videotrans/configure/_paths.py)
Source: "{#StageDir}\pvt_models\*"; DestDir: "{app}\pyvideotrans\models"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\Mazino Video Localizer"; Filename: "{app}\web_server.exe"; WorkingDir: "{app}"
Name: "{group}\{cm:UninstallProgram,Mazino Video Localizer}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Mazino Video Localizer"; Filename: "{app}\web_server.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Run]
Filename: "{app}\web_server.exe"; Description: "Chạy Mazino Video Localizer ngay"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Dọn thư mục cache/tmp sinh ra lúc chạy (không phải file cài đặt gốc)
Type: filesandordirs; Name: "{app}\tmp"
Type: filesandordirs; Name: "{app}\logs"
Type: filesandordirs; Name: "{app}\outputs"
Type: filesandordirs; Name: "{app}\pyvideotrans\tmp"
Type: filesandordirs; Name: "{app}\pyvideotrans\logs"
Type: filesandordirs; Name: "{app}\vsr\tmp"
