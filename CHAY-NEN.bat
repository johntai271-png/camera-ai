@echo off
REM Chay Camera AI o CHE DO NEN: khong cua so video, xem qua trinh duyet.
REM Log ghi vao data\logs\app.log
cd /d "%~dp0"
if not exist "data\logs" mkdir "data\logs"
echo Dang khoi dong Camera AI che do nen...
start "CameraAI" /min cmd /c ".venv\Scripts\python.exe main.py --headless >> data\logs\app.log 2>&1"
echo.
echo  Da chay nen! Xem camera tai:   http://localhost:8090
echo  (dien thoai cung WiFi: http://IP-MAY-NAY:8090)
echo  Tat he thong: nut "Tat he thong" tren dashboard, hoac chay TAT-CAMERA.bat
timeout /t 6 >nul
