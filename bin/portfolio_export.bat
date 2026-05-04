@echo off
setlocal

rem === NOTE: ENSURE QUICKEN IS NOT RUNNING BEFORE STARTING ===
rem This script assumes that qw.exe is not running
rem (This script can't kill it because doing so requires elevated privileges, but
rem  Quicken is not supposed to be run with elevated privileges and this script
rem  must launch a fresh instance of the qw.exe process.)

rem === LOAD DEPLOYMENT CONFIG ===
if not exist "%~dp0config.bat" (
    echo ERROR: %~dp0config.bat not found. Copy config.bat.example to config.bat and fill in your values.
    exit /b 1
)
call "%~dp0config.bat"

rem === DERIVED PATHS (no need to edit below this line) ===
set "NAS=\\%NAS_HOST%\%NAS_SHARE%"
set "AHK=%NAS%\portfolio-analysis\ahk\QuickenPortfolioExport.ahk"
set "EXPORT_CSV=%NAS%\openclaw\quicken_exports\portfolio_nightly.csv"
set "FINAL_DIR=%NAS%\openclaw\quicken_exports"

for /f %%I in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd"') do set "TODAY=%%I"
set "FINAL_CSV=portfolio_%TODAY%.csv"

rem === IDEMPOTENCY: skip if today's archive already exists ===
if exist "%FINAL_DIR%\%FINAL_CSV%" (
    echo Already exported today: %FINAL_DIR%\%FINAL_CSV%
    exit /b 0
)

rem === GUARD: source must exist ===
if not exist "%SRC%" (
    echo ERROR: Source file not found:
    echo   %SRC%
    exit /b 2
)

rem === GUARD: AutoHotkey executable must exist ===
if not exist "%AHKEXE%" (
    echo ERROR: AutoHotkey executable not found:
    echo   %AHKEXE%
    exit /b 3
)

rem === GUARD: AHK script must exist ===
if not exist "%AHK%" (
    echo ERROR: AutoHotkey script not found:
    echo   %AHK%
    exit /b 4
)

rem === ENSURE DESTINATION FOLDER EXISTS ===
for %%I in ("%DST%") do set "DSTDIR=%%~dpI"
if not exist "%DSTDIR%" (
    mkdir "%DSTDIR%"
    if errorlevel 1 (
        echo ERROR: Could not create destination folder:
        echo   %DSTDIR%
        exit /b 5
    )
)

rem === ENSURE TRANSIENT EXPORT FILE DOES NOT EXIST ===
if exist "%EXPORT_CSV%" (
    del "%EXPORT_CSV%"
)

rem === ENSURE QUICKEN IS NOT RUNNING BEFORE STARTING ===
tasklist /FI "IMAGENAME eq qw.exe" 2>nul | find /I "qw.exe" >nul
if not errorlevel 1 (
    echo ERROR: Quicken is still running and could not be terminated.
    echo        Run the task with highest privileges, or close Quicken manually.
    exit /b 10
)

rem === COPY QDF TO LOCAL WORKING FILE ===
copy /Y "%SRC%" "%DST%" >nul
if errorlevel 1 (
    echo ERROR: Copy of QDF failed.
    exit /b 6
)

echo Copy successful:
echo   %SRC%
echo   ^>
echo   %DST%

rem === RUN AHK EXPORT SCRIPT AND WAIT FOR IT ===
"%AHKEXE%" "%AHK%" "%EXPORT_CSV%"
set "RC=%ERRORLEVEL%"

if not "%RC%"=="0" (
    echo ERROR: AutoHotkey export script failed with code %RC%.
    exit /b %RC%
)

rem === CLOSE QUICKEN ===
taskkill /IM qw.exe /F >nul 2>&1
timeout /t 15 /nobreak >nul

rem === CHECK FOR EXPECTED EXPORT OUTPUT ===
if not exist "%EXPORT_CSV%" (
    echo ERROR: Expected export CSV not found:
    echo   %EXPORT_CSV%
    exit /b 7
)

rem === ENSURE ARCHIVE DIRECTORY EXISTS ===
if not exist "%FINAL_DIR%" (
    mkdir "%FINAL_DIR%"
    if errorlevel 1 (
        echo ERROR: Could not create archive directory:
        echo   %FINAL_DIR%
        exit /b 8
    )
)

rem === COPY/RENAME EXPORT TO ARCHIVE FILE ===
copy /Y "%EXPORT_CSV%" "%FINAL_DIR%\%FINAL_CSV%" >nul
if errorlevel 1 (
    echo ERROR: Failed copying final CSV to destination name.
    exit /b 9
)
del "%EXPORT_CSV%"

echo Success:
echo   Export created:    %FINAL_DIR%\%FINAL_CSV%

exit /b 0
