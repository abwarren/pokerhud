#!/bin/bash
# Updates Supabase anon key in all config files

if [ -z "$1" ]; then
  echo "Usage: ./update_supabase_key.sh YOUR_ANON_KEY"
  echo ""
  echo "Get your key from:"
  echo "https://supabase.com/dashboard/project/kzqrdtagpykoylhuqcyv/settings/api"
  exit 1
fi

KEY="$1"

cd /opt/pokerhud/pokerhud

echo "Updating shared/utils/supabase.ts..."
sed -i "s|YOUR_ANON_KEY_HERE|$KEY|g" shared/utils/supabase.ts

echo "Updating check-migrations.js..."
sed -i "s|YOUR_ANON_KEY_HERE|$KEY|g" check-migrations.js

echo "✅ Configuration updated!"
echo ""
echo "Next steps:"
echo "1. cd /opt/pokerhud/pokerhud"
echo "2. npm run build:extension"
echo "3. Apply migrations to Supabase"
