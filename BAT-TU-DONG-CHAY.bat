@echo off
REM Cai dat: Camera AI TU CHAY NEN moi khi mo may (tao shortcut trong thu muc Startup)
powershell -NoProfile -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Startup')+'\CameraAI.lnk'); $s.TargetPath='%~dp0CHAY-NEN.bat'; $s.WorkingDirectory='%~dp0'; $s.Save()"
if %errorlevel%==0 (
    echo Xong! Tu gio mo may la Camera AI tu chay nen.
    echo Muon bo: chay TAT-TU-DONG-CHAY.bat
) else (
    echo Loi khi tao shortcut khoi dong.
)
timeout /t 5 >nul
