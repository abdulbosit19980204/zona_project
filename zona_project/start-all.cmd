@echo off
REM Barcha servislarni bitta buyruq bilan ishga tushirish + boshqaruv sahifasi: http://127.0.0.1:8900
cd /d "%~dp0"
py -3 services\control\control.py %*
