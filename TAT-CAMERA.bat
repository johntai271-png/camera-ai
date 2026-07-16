@echo off
REM Tat Camera AI dang chay nen (goi nut tat cua dashboard)
curl -s -X POST http://localhost:8090/api/quit >nul 2>&1
if %errorlevel%==0 (
    echo Da gui lenh tat. He thong se dong trong vai giay.
) else (
    echo Khong lien lac duoc dashboard - co the app khong chay, hoac port khac 8090.
)
timeout /t 4 >nul
