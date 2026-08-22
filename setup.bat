@echo off
setlocal
cd /d "%~dp0"
title SN TalkBot Setup

where py >nul 2>nul
if %errorlevel%==0 (
  set "PY=py -3"
) else (
  where python >nul 2>nul || (
    echo Python 3.9 or newer is required: https://www.python.org/downloads/
    exit /b 1
  )
  set "PY=python"
)

if not exist .venv (
  %PY% -m venv .venv || exit /b 1
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt || exit /b 1

if not exist config.ini copy /Y config_default.ini config.ini >nul
python locales\compile_locales.py || exit /b 1

where deno >nul 2>nul
if errorlevel 1 (
  echo.
  echo Deno 2.3+ is required for full YouTube support with current yt-dlp.
  echo Official install guide: https://docs.deno.com/runtime/getting_started/installation/
)

if not exist TeamTalk5.py goto teamtalk_missing
if not exist TeamTalk5.dll goto teamtalk_missing
goto teamtalk_done

:teamtalk_missing
echo.
echo TeamTalk SDK v5.22a is not installed in this folder.
echo Download Windows x64 SDK:
echo https://www.bearware.dk/teamtalksdk/v5.22a/tt5sdk_v5.22a_win64.7z
echo Extract it, then run:
echo   .venv\Scripts\python.exe tools\install_teamtalk_sdk.py C:\path\to\extracted-sdk

:teamtalk_done
echo.
echo python-mpv also requires the native libmpv DLL on Windows.
echo Install a current Windows mpv/libmpv build and put its DLL in PATH or beside the Python mpv module.
echo See README_TH.md for the recommended source.
echo.
echo Setup complete. After TeamTalk/libmpv are ready, run:
echo   .venv\Scripts\python.exe tools\check_environment.py
echo   run_bot.bat
endlocal
