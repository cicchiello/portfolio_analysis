rem === ENSURE QUICKEN IS NOT RUNNING BEFORE STARTING ===
tasklist /FI "IMAGENAME eq qw.exe" 2>nul | find /I "qw.exe" >nul
if not errorlevel 1 (
    echo WARNING: Quicken is still running; terminating it
    taskkill /IM qw.exe /F >nul 2>&1
)
timeout /t 5 /nobreak >nul

