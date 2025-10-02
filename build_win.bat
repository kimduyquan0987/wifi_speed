@echo off
python -m venv venv
call venv\Scripts\activate
pip install -r requirements.txt
pip install pyinstaller
pyinstaller --onefile --hidden-import speedtest --hidden-import speedtest-cli wifi_speed.py
echo Done. See dist\wifi_speed.exe
pause
