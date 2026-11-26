@echo off
rem Starts the CAD4Ai 3D viewer without Claude and opens it in the browser.
rem   start-viewer.bat                  the viewer waits for a model (or shows the last one)
rem   start-viewer.bat "C:\path\x.step"  opens that model
rem Needs Python 3; CadQuery for parameter rebuilds and exports.
set PORT=8766
set DATA=%USERPROFILE%\.cad4ai-viewer
if "%~1"=="" (
  start "CAD4Ai viewer" /min python "%~dp0viewer\server.py" --port %PORT% --data "%DATA%"
) else (
  start "CAD4Ai viewer" /min python "%~dp0viewer\server.py" --port %PORT% --data "%DATA%" --open "%~f1"
)
timeout /t 2 /nobreak >nul
start "" http://127.0.0.1:%PORT%/
