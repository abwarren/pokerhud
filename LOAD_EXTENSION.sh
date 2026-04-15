#!/bin/bash
# Single task: Get Chrome extension loaded

echo "============================================"
echo "PokerBet HUD - Load Extension"
echo "============================================"
echo ""

DIST_DIR="/opt/pokerhud/pokerhud/extension/dist"

# Check if dist exists
if [ ! -d "$DIST_DIR" ]; then
  echo "❌ Error: $DIST_DIR does not exist"
  exit 1
fi

# Check if manifest exists
if [ ! -f "$DIST_DIR/manifest.json" ]; then
  echo "❌ Error: manifest.json not found in $DIST_DIR"
  exit 1
fi

echo "✅ Found extension files:"
ls -lh "$DIST_DIR"/{manifest.json,content.js,background.js} 2>/dev/null

echo ""
echo "============================================"
echo "LOAD THIS FOLDER IN CHROME:"
echo "============================================"
echo ""
echo "$DIST_DIR"
echo ""
echo "Steps:"
echo "1. Open: chrome://extensions/"
echo "2. Toggle 'Developer mode' ON (top-right)"
echo "3. Click 'Load unpacked'"
echo "4. Paste this path: $DIST_DIR"
echo "5. Click 'Select'"
echo ""
echo "============================================"
