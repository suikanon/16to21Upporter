@echo off
REM ^ Don't write everything to screen

REM - Set the working folder
cd /D "%~dp0"

REM - Call the runner
.\Engines\converter_run 1
