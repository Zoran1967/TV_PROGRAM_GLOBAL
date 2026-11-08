#!/usr/bin/env bash
# Testovi projekta. Pokrece ih GitHub Actions (radni tok "Izgradnja APK").
set -euo pipefail

python -m pip install pytest
python -m compileall -q main.py app tests
python -m pytest -q tests
