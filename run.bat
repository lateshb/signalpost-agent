@echo off
rem Signalpost agent - one-click runner for Windows. Needs only Python 3.11+.
rem   run.bat                   research the 11 demo companies, then open the results page
rem   run.bat my-companies.txt  research the organisation numbers in that file (one per line)
rem   run.bat FILE --previous out\old-envelopes.jsonl   any extra options go straight to the agent
setlocal
cd /d "%~dp0"

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if defined PY %PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul || set "PY="
if not defined PY (
  echo Python 3.11 or newer is needed: https://www.python.org/downloads/  ^(tick "Add python.exe to PATH"^)
  exit /b 1
)

if not exist ".venv-local\Scripts\python.exe" (
  echo First run: setting up a local Python environment ...
  %PY% -m venv .venv-local || exit /b 1
)
if not exist ".venv-local\installed.txt" (
  echo First run: installing dependencies, about a minute ...
  ".venv-local\Scripts\python.exe" -m pip install --quiet --disable-pip-version-check -r requirements.txt || exit /b 1
  echo ok> ".venv-local\installed.txt"
)

set "INPUT=%~1"
if "%INPUT%"=="" set "INPUT=demo\demo-companies.txt"
if not "%~1"=="" shift
echo Researching the companies in %INPUT% ...
".venv-local\Scripts\python.exe" scripts\run_competition_batch.py "%INPUT%" %1 %2 %3 %4 %5 %6 %7 %8 %9
set "CODE=%errorlevel%"
echo.
echo Results: out\envelopes.jsonl, out\report.json and out\report.html
if not defined SIGNALPOST_NO_OPEN if exist "out\report.html" start "" "out\report.html"
exit /b %CODE%
