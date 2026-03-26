#!/bin/bash
# Set up library paths
export LD_LIBRARY_PATH=.:./build:$LD_LIBRARY_PATH
export PYTHONPATH=.:./sick-scan-api/api:$PYTHONPATHS
python3 main.py
