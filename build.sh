#!/usr/bin/env bash
# Runs on every deploy: install, collect static files, apply migrations, refresh demo data.
set -o errexit
pip install -r requirements.txt
python manage.py collectstatic --no-input
python manage.py migrate --no-input
python manage.py seed
