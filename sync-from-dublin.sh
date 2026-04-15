#!/bin/bash
# Sync Dublin -> local (excludes .git, venv, node_modules)
rsync -avz --delete \
  --exclude '.git' \
  --exclude 'venv' \
  --exclude 'node_modules' \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  --exclude 'Scrapegraph-ai' \
  --exclude 'pokerhud' \
  -e "ssh -i /home/ploxyz.pem" \
  ubuntu@52.16.14.220:/opt/pokerhud/ /opt/pokerhud/
echo "✅ Synced from Dublin"
