#!/bin/bash
cd "$(dirname "$0")"

if [ ! -d "venv" ]; then
    python3 -m venv venv
    ./venv/bin/pip install -r requirements.txt
fi

./venv/bin/python experiment_runner.py --rates 1 2 5 10 15 --duration 30
