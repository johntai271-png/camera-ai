@echo off
REM Nhấp đúp file này để mở Camera AI (khỏi gõ lệnh)
cd /d "%~dp0"
echo ============================================
echo   CAMERA AI - dang khoi dong...
echo   (Nho: dien thoai phai dang Start server)
echo ============================================
".venv\Scripts\python.exe" main.py
echo.
echo App da dong. Nhan phim bat ky de thoat cua so nay.
pause >nul
