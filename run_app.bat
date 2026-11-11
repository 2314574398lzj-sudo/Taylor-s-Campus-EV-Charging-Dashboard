@echo off
title ITS72604 - Smart Campus Energy ^& EV Fleet Dashboard
cd /d "%~dp0"

echo ============================================================
echo  ITS72604 Smart Campus Energy ^& EV Fleet Dashboard
echo  Starting the Streamlit application ...
echo  Address: http://localhost:8501   (closes when this window closes)
echo ============================================================
echo.

rem --- 1) system Python with Streamlit already installed ---------
py -3 -c "import streamlit" >nul 2>&1
if %errorlevel%==0 (
    echo [launcher] using system Python
    py -3 -m streamlit run app.py --browser.gatherUsageStats false
    goto :end
)

python -c "import streamlit" >nul 2>&1
if %errorlevel%==0 (
    echo [launcher] using python on PATH
    python -m streamlit run app.py --browser.gatherUsageStats false
    goto :end
)

rem --- 2) runtime bundled with the submission build --------------
set "PY=C:\Users\86131\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
set "PYTHONPATH=C:\Users\86131\Documents\deepseek-harness\default-workspace\.pylibs"
set "STREAMLIT_GLOBAL_DEVELOPMENT_MODE=false"
if exist "%PY%" (
    echo [launcher] using the bundled Python runtime
    "%PY%" -m streamlit run app.py --global.developmentMode false --browser.gatherUsageStats false
    goto :end
)

echo.
echo [ERROR] Python with Streamlit was not found on this computer.
echo Install once with:
echo     py -3 -m pip install -r requirements.txt
echo then double-click this file again.
echo.
pause

:end
