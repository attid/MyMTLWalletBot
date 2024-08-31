#!/bin/bash


# Find and remove all __pycache__ directories
find . -type d -name "__pycache__" -exec rm -rf {} +

# Find and remove all .log files
find . -type f -name "*.log" -exec rm -f {} +
