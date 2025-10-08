#!/bin/bash
# Upgrade pip first
pip install --upgrade pip

# Install packages with no cache to avoid build issues
pip install --no-cache-dir -r requirements.txt