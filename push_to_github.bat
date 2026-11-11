@echo off
setlocal
title Push Taylor's Campus EV Charging Dashboard to GitHub
cd /d "%~dp0"

echo ============================================================
echo  Push this folder to your GitHub repository
echo ============================================================
echo.
set /p REPO_URL=Repository URL (e.g. https://github.com/ThisIsMialy/Taylors-Campus-EV-Charging-Dashboard.git): 
if "%REPO_URL%"=="" goto :cancel

where git >nul 2>&1
if errorlevel 1 (
    echo [ERROR] git was not found. Install Git for Windows from https://git-scm.com/download/win
    pause
    goto :cancel
)

set "CLONE=%TEMP%\taylor_ev_repo"
if exist "%CLONE%" rmdir /s /q "%CLONE%"

echo.
echo [1/4] Cloning the repository ...
git clone "%REPO_URL%" "%CLONE%"
if errorlevel 1 goto :failed

echo.
echo [2/4] Copying the project files ...
robocopy "%~dp0." "%CLONE%" /E /XD .git /XF push_to_github.bat /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 goto :failed

echo.
echo [3/4] Committing ...
pushd "%CLONE%"
git add -A
git -c user.name="Liu Zengjie" -c user.email="0399396@student.taylors.edu.my" commit -m "Taylor's Campus EV Charging Dashboard - ITS72604 final examination"
if errorlevel 1 echo (nothing new to commit)

echo.
echo [4/4] Pushing (a browser window may ask you to sign in to GitHub) ...
git push origin HEAD
if errorlevel 1 goto :push_failed

popd
echo.
echo ============================================================
echo  Done. Open: %REPO_URL%
echo ============================================================
pause
goto :eof

:push_failed
popd
:failed
echo.
echo [ERROR] The push failed. Check the message above.
echo Common fixes: sign in when the browser opens, or confirm the URL ends with .git
pause
goto :eof

:cancel
endlocal
