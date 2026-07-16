@echo off
REM Go bo: khong tu chay Camera AI khi mo may nua
powershell -NoProfile -Command "Remove-Item ([Environment]::GetFolderPath('Startup')+'\CameraAI.lnk') -ErrorAction SilentlyContinue"
echo Da go tu-dong-chay (neu truoc do co cai).
timeout /t 4 >nul
