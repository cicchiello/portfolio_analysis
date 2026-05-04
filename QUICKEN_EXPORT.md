# OpenClaw Quicken Portfolio Export Automation

Automates a daily export of the Quicken **Investing Portfolio** view to a CSV file for downstream OpenClaw processing.

## What this does

The current workflow is a two-stage Windows automation:

1. A wrapper batch file copies the source Quicken `.QDF` file to a **local working file** on the Windows machine.
2. The batch file launches an AutoHotkey v2 script and waits for it to finish.
3. The AutoHotkey script aborts immediately if Quicken is already running.
4. The AutoHotkey script opens the local working `.QDF` file.
5. It waits for Quicken to finish launching.
6. It opens the **Investing Portfolio** view.
7. It sets:
   - **Show** = `Holdings`
   - **Group By** = `Accounts`
8. It opens the portfolio export workflow.
9. It selects the **Export to:** option.
10. It saves the export to a fixed nightly CSV path.
11. It approves overwrite of the nightly CSV.
12. It closes Quicken.
13. If the AutoHotkey script returns success, the wrapper batch file copies the nightly CSV to an archive filename for that day.

The current nightly CSV path is:

```text
\\%NAS_HOST%\%NAS_SHARE%\openclaw\quicken_exports\portfolio_nightly.csv
```

The current archive directory is:

```text
\\%NAS_HOST%\%NAS_SHARE%\openclaw\quicken_exports
```

---

## Current assumptions

This automation currently assumes all of the following are true:

- It runs on a Windows PC that is always on.
- The Windows user account can launch and use Quicken.
- Auto-login is enabled or the user is already logged in.
- Quicken is installed and can open `.QDF` files through normal Windows file association.
- The working `.QDF` used by the automation is **local** to the Windows machine.
- The source `.QDF` is readable by the wrapper batch file.
- The export destination UNC path is reachable from the PC.
- Quicken UI keyboard shortcuts and dropdown ordering remain stable.

Because this is UI automation, layout or workflow changes in Quicken may require script updates.

---

## Repository purpose

This repo is intended to hold:

- the AutoHotkey automation script
- the wrapper batch file
- Task Scheduler setup notes
- logs or future enhancements for monitoring and error handling

---

## Prerequisites

### Software

- Windows 10 or 11
- Quicken for Windows
- AutoHotkey v2
- PowerShell (used by the batch wrapper for date-stamped archive names)

### Access

- Read access to the source Quicken `.QDF` file
- Read/write access to the local working `.QDF` location
- Write access to the export target directory on the NAS/share
- Write access to the archive directory on the NAS/share

### Recommended environment

- Dedicated Windows account for automation
- Auto-login enabled for unattended execution
- Task Scheduler configured to run only when the user is logged on
- Sleep/hibernation disabled on the automation PC

---

## Why the working QDF is local

Quicken warns when a live data file is opened from a network location. The automation therefore uses this safer pattern:

- keep the source `.QDF` wherever the user normally maintains it
- copy it to a **local working path** before launching Quicken
- open the local working file from AutoHotkey
- export the CSV to the NAS/share

This avoids Quicken's non-local-file warning during the automated run.

---

## Current AutoHotkey script

This is the current unattended export script with explicit exit codes.

```ahk
#Requires AutoHotkey v2.0
#SingleInstance Force

qdfPath := "C:\tmp\HOME_nightly.QDF"
exportPath := A_Args[1]  ; passed by portfolio_export.bat

; Exit codes:
;   0  = success
;   10 = Quicken already running
;   11 = QDF file missing
;   12 = Quicken window did not appear
;   13 = Quicken window could not be activated

if ProcessExist("qw.exe") {
    ExitApp 10
}

if !FileExist(qdfPath) {
    ExitApp 11
}

Run qdfPath
Sleep 25000

if !WinExist("ahk_exe qw.exe") {
    ExitApp 12
}

WinActivate "ahk_exe qw.exe"
Sleep 1000

if !WinActive("ahk_exe qw.exe") {
    ExitApp 13
}

Send "^u"
Sleep 3000

Send "!s"
Sleep 500
Send "{Home}"
Sleep 300
Send "{Down}"
Sleep 300
Send "{Down}"
Sleep 300
Send "{Down}"
Sleep 300
Send "{Down}"
Sleep 300
Send "{Down}"
Sleep 300
Send "{Down}"
Sleep 300
Send "{Down}"
Sleep 300
Send "{Down}"
Sleep 300
Send "{Down}"
Sleep 300
Send "{Enter}"
Sleep 1500

Send "!g"
Sleep 500
Send "{Home}"
Sleep 300
Send "{Enter}"
Sleep 2000

Send "^p"
Sleep 2000

Send "!x"
Sleep 500
Send "{Space}"
Sleep 1000

Send "{Enter}"
Sleep 3000

SendText exportPath
Sleep 500
Send "{Enter}"
Sleep 3000

; Approve overwrite
Send "!y"
Sleep 3000

; Close Quicken
WinActivate "ahk_exe qw.exe"
Sleep 500
Send "!{F4}"
Sleep 3000

ExitApp 0
```

---

## Current batch wrapper

This is the current wrapper batch file. It copies the working `.QDF`, runs the AutoHotkey script, checks the return code, and archives the resulting CSV.

```bat
@echo off
setlocal

rem === CONFIGURE THESE PATHS ===
set "NAS_HOST=YOUR_NAS_HOST"
set "NAS_SHARE=YOUR_NAS_SHARE"
set "SRC=G:\My Drive\personal\finances\HOME.QDF"
set "DST=C:\tmp\HOME_nightly.QDF"
set "AHKEXE=C:\Program Files\AutoHotkey\v2\AutoHotkey64.exe"

rem === DERIVED PATHS (no need to edit below this line) ===
set "NAS=\\%NAS_HOST%\%NAS_SHARE%"
set "AHK=%NAS%\portfolio-analysis\ahk\QuickenPortfolioExport.ahk"
set "EXPORT_CSV=%NAS%\openclaw\quicken_exports\portfolio_nightly.csv"
set "FINAL_DIR=%NAS%\openclaw\quicken_exports"

for /f %%I in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd"') do set "TODAY=%%I"
set "FINAL_CSV=portfolio_%TODAY%.csv"

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
"%AHKEXE%" "%AHK%"
set "RC=%ERRORLEVEL%"

if not "%RC%"=="0" (
    echo ERROR: AutoHotkey export script failed with code %RC%.
    exit /b %RC%
)

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
    echo ERROR: Failed copying final CSV to archive name.
    exit /b 9
)

echo Success:
echo   Export created: %EXPORT_CSV%
echo   Archived as:    %FINAL_DIR%\%FINAL_CSV%

exit /b 0
```

---

## Exit codes

### AutoHotkey script exit codes

- `0` = success
- `10` = Quicken already running
- `11` = working QDF file missing
- `12` = Quicken window did not appear after launch
- `13` = Quicken window could not be activated

### Batch wrapper exit codes

- `0` = success
- `2` = source QDF missing
- `3` = AutoHotkey executable missing
- `4` = AutoHotkey script missing
- `5` = could not create local working directory
- `6` = failed copying source QDF to local working QDF
- `7` = expected nightly export CSV missing after AHK success
- `8` = could not create archive directory
- `9` = failed copying the nightly CSV into the archive filename
- any propagated AutoHotkey nonzero code = AHK-stage failure

---

## Configuration

These are the main values you are likely to customize.

### In the AutoHotkey script

#### `qdfPath`

Local path to the copied working Quicken data file.

Example:

```ahk
qdfPath := "C:\tmp\HOME_nightly.QDF"
```

#### `exportPath`

Nightly CSV path written by Quicken.

Example:

```ahk
exportPath := A_Args[1]  ; passed by portfolio_export.bat
```

### In the batch wrapper

#### `SRC`

Source `.QDF` to be copied into the local working location.

#### `DST`

Local working `.QDF` opened by the automation.

#### `AHKEXE`

Path to AutoHotkey v2 executable.

#### `AHK`

Path to the AutoHotkey automation script.

#### `EXPORT_CSV`

Nightly CSV expected after the AHK script completes.

#### `FINAL_DIR`

Directory receiving archive copies of the nightly CSV.

#### `FINAL_CSV`

Date-stamped archive filename, currently `portfolio_yyyy-mm-dd.csv`.

---

## Timing values

The script currently uses fixed delays such as:

- `Sleep 25000` after launching Quicken
- `Sleep 3000` after opening views/dialogs

These may need adjustment depending on machine speed, Quicken updates, or network conditions.

---

## Running manually

To test manually:

1. Log into the Windows account used for automation.
2. Ensure Quicken is not already open.
3. Run the batch file from Command Prompt by full path.
4. Confirm that:
   - the source QDF is copied locally
   - the correct working QDF opens
   - the portfolio view is selected
   - the export is written to the nightly CSV path
   - overwrite is handled
   - Quicken closes when done
   - the archive copy is created with the expected filename

---

## Running from Task Scheduler

The intended final scheduler entry point is the **batch wrapper**, not the `.ahk` file directly.

Recommended Task Scheduler settings:

- **Trigger:** Daily at the desired time
- **Action:** Start the batch file, or start `cmd.exe /c <batchfile>`
- **Run only when user is logged on:** Yes
- **Start in:** the wrapper script directory

A robust explicit configuration is usually:

- **Program/script:**

```text
C:\Windows\System32\cmd.exe
```

- **Add arguments:**

```text
/c "C:\path\to\wrapper.bat"
```

- **Start in:**

```text
C:\path\to
```

Do at least one manual **Run** from Task Scheduler before relying on the daily trigger.

---

## Known fragility points

This is UI automation, so it can break if any of the following change:

- Quicken keyboard shortcuts
- the order of items in the **Show** dropdown
- the default position in the **Group By** dropdown
- the export dialog layout
- overwrite confirmation wording or accelerator keys
- launch timing

After Quicken updates, rerun a manual test.

---

## Troubleshooting

### Quicken opens the wrong file

Make sure the batch wrapper copied the desired source `.QDF` to the local working path, and that the AHK script launches the local working file:

```ahk
Run qdfPath
```

Do not rely on launching `qw.exe` alone.

### Quicken warns about the file not being local

The working `.QDF` should be local, for example:

```text
C:\tmp\HOME_nightly.QDF
```

The CSV output can still be written to the NAS/share.

### Script starts while Quicken is already open

This is an intentional guard. The AHK script returns exit code `10`:

```ahk
if ProcessExist("qw.exe") {
    ExitApp 10
}
```

### Export path fails

Verify that the Windows account running the scheduler can browse and write to:

```text
\\%NAS_HOST%\%NAS_SHARE%\openclaw\quicken_exports\
```

### Archive file is overwritten on repeated same-day runs

The current archive filename uses only the date. Multiple successful runs on the same day will overwrite the same archive file.

If that becomes a problem, switch to a timestamp including hours/minutes/seconds.

### The wrong dropdown item is selected

Quicken may have changed the item ordering. Re-test manually and update the number of `{Down}` key presses.

### Task Scheduler run behaves differently than manual run

Common causes:

- user not logged in
- network share not yet available
- Quicken startup slower under scheduled launch
- script working directory not set
- mapped drives not available in the scheduler context

Note that the current `SRC` path uses a mapped `G:` drive. If Task Scheduler runs under a context where `G:` is not mounted, the wrapper will fail early.

---

## Suggested repo contents

A simple starting layout:

```text
.
├── README.md
├── QuickenPortfolioExport.ahk
├── run_quicken_export.bat
├── archive/
└── logs/
```

---

## Status

Current status: **working manually end-to-end**.

Validated behaviors:

- local working QDF launch works
- portfolio export works
- overwrite approval works
- Quicken closes after export
- wrapper batch file waits for AHK completion
- AHK exit codes propagate back to the wrapper
- archive copy after successful export works

Remaining operational validation:

- Task Scheduler invocation test
- unattended reboot + auto-login test
- repeated daily reliability test
- optional logging for batch and AHK runs
