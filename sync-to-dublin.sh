#!/bin/bash
# Sync local -> Dublin (excludes .git, venv, node_modules)
rsync -avz --delete \
  --exclude '.git' \
  --exclude 'venv' \
  --exclude 'node_modules' \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  -e "ssh -i /home/ploxyz.pem" \
  /opt/pokerhud/ ubuntu@52.16.14.220:/opt/pokerhud/
echo "✅ Synced to Dublin"
