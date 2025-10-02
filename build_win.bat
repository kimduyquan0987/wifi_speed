@echo off
REM build_win.bat - build wifi_speed.exe using pyinstaller
REM Usage: run in folder with wifi_speed.py

python -m venv venv
call venv\Scripts\activate
pip install -r requirements.txt
pip install pyinstaller
pyinstaller --onefile --windowed wifi_speed.py
echo Done. See dist\wifi_speed.exe
pause
