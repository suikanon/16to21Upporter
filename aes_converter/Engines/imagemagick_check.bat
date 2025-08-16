REM - Script to check if imagemagick is in the PATH and that its version is 7.1 or higher

setlocal EnableDelayedExpansion

for /f "tokens=*" %%A in ('magick -version 2^>nul') do (

  set imagemagick_version_line=%%A

  if "!imagemagick_version_line:~21,1!"=="7" (
    if "!imagemagick_version_line:~23,1!" GEQ "1" (
      set imagemagick_version_ok=1
    )
  )
  if "!imagemagick_version_line:~21,1!" GEQ "8" (
    set imagemagick_version_ok=1
  )
)

if not defined imagemagick_version_ok (

  echo -
  echo - ImageMagick 7.1+ is missing from your pc, please install it
  echo -
  echo - If it is already installed, reinstall it, and make sure to check
  echo - the "Add application directory to your system path" checkbox
  echo -
  echo Press any key to open the ImageMagick download webpage...

  pause >nul

  start "" "https://imagemagick.org/script/download.php#windows"

  timeout /t 5 >nul

  echo -
  echo Press any key to resume the compiler after installing or fixing ImageMagick...

  pause >nul

  .\Engines\imagemagick_check
)
