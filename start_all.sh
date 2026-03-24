#!/bin/bash
echo "🚀 Štartujem Kraken HFT Systém..."
PYTHON_BIN="/opt/homebrew/opt/python@3.11/bin/python3.11"
$PYTHON_BIN dashboard.py &
sleep 3
$PYTHON_BIN live_production_master.py
