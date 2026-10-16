@echo off
rem Double-click to set up the project and open the dashboard (Windows).
setlocal
cd /d "%~dp0"

where uv >nul 2>nul
if errorlevel 1 (
    echo [1/4] Installing uv...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
    if errorlevel 1 goto fail
    set "PATH=%USERPROFILE%\.local\bin;%PATH%"
)

echo [2/4] Python 3.12 and dependencies (first run downloads a few hundred MB)...
uv sync
if errorlevel 1 goto fail

echo [3/4] Catalog, 14 days of partner feeds, dbt build...
uv run hcq demo
if errorlevel 1 goto fail

echo [4/4] Dashboard: http://localhost:8501  (close this window to stop it)
uv run hcq dashboard
goto end

:fail
echo.
echo Something failed above. Copy the output of this window and send it to Claude.

:end
pause
