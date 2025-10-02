@echo off
python -m venv venv
call venv\Scripts\activate
pip install -r requirements.txt
pip install pyinstaller
pyinstaller --onefile --windowed --hidden-import=speedtest wifi_speed.py
echo Done. See dist\wifi_speed.exe
pause
