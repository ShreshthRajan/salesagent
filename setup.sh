#!/bin/bash

# Create virtual environment using python3
/opt/homebrew/bin/python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Install dependencies
venv/bin/pip install -r requirements.txt

# Install playwright browsers
venv/bin/playwright install

# Create necessary directories
mkdir -p logs