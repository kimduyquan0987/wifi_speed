@echo off
REM build_win.bat - build wifi_speed.exe using pyinstaller
REM Usage: run in folder with wifi_speed.py

python -m venv venv
call venv\Scripts\activate
pip install -r requirements.txt
pip install speedtest-cli
pip install pyinstaller
pyinstaller --onefile --windowed --hidden-import=speedtest --collect-submodules speedtest wifi_speed.py
echo Done. See dist\wifi_speed.exe
pause
