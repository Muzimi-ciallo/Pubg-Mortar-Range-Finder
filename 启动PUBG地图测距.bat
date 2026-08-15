@echo off
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
    py -m pip install -r requirements.txt
    py map_distance_tool.py
) else (
    python -m pip install -r requirements.txt
    python map_distance_tool.py
)
pause
