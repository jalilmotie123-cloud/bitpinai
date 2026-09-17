@echo off
timeout /t 30 /nobreak
cd /d D:\BitpinAI
start "Bitpin Scanner" "C:\Users\it\AppData\Local\Programs\Python\Python38\python.exe" scanner_v2.py
start "Bitpin Collector" "C:\Users\it\AppData\Local\Programs\Python\Python38\python.exe" matches_collector_clean.py
