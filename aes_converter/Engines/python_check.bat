REM - Script to check if python is in the PATH and that its version is 3.9 or higher

setlocal EnableDelayedExpansion

for /f "tokens=*" %%A in ('py -3 -V 2^>nul') do (

  set python_version_line=%%A

  if "!python_version_line:~7,1!"=="3" (
    if "!python_version_line:~9,1!"=="9" (
      set python_version_ok=1
    )
    if "!python_version_line:~9,1!" GEQ "1" (
      if not "!python_version_line:~10,1!"=="." (
        set python_version_ok=1
      )
    )
  )
)

if not defined python_version_ok (

  echo -
  echo - Python 3.9+ is missing from your pc, please install it
  echo -
  echo - If it is already installed, run the installer again, choose Modify, click Next and make
  echo - sure to check the "Add Python to environment variables" checkbox, then click Install
  echo -
  echo Press any key to open the Python download webpage...

  pause >nul

  start "" https://www.python.org/downloads/

  timeout /t 5 >nul

  echo -
  echo Press any key to resume the compiler after installing or fixing Python...

  pause >nul

  .\Engines\python_check
)
