#!/usr/bin/env bash
# Barcha servislarni bitta buyruq bilan ishga tushirish + boshqaruv sahifasi: http://127.0.0.1:8900
cd "$(dirname "$0")" && exec python3 services/control/control.py "$@"
