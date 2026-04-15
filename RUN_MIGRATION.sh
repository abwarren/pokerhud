#!/bin/bash
# Run this script to link and push Supabase migrations

if [ -z "$1" ]; then
  echo "❌ Access token required!"
  echo ""
  echo "Usage: bash RUN_MIGRATION.sh YOUR_ACCESS_TOKEN"
  echo ""
  echo "Get your token from:"
  echo "https://supabase.com/dashboard/account/tokens"
  echo ""
  exit 1
fi

TOKEN="$1"

cd /opt/pokerhud

echo "🔗 Linking to Supabase project..."
npx supabase link --project-ref kzqrdtagpykoylhuqcyv --token "$TOKEN"

if [ $? -ne 0 ]; then
  echo "❌ Failed to link"
  exit 1
fi

echo ""
echo "✅ Linked successfully!"
echo ""
echo "🚀 Pushing migrations..."
npx supabase db push

if [ $? -ne 0 ]; then
  echo "❌ Failed to push migrations"
  exit 1
fi

echo ""
echo "============================================"
echo "✅ Migrations pushed successfully!"
echo "============================================"
echo ""
echo "Created tables:"
echo "  - tournaments"
echo "  - tournament_results"
echo "  - promotions"
echo "  - cash_tables"
echo "  - scrape_runs"
echo ""
echo "Next: Check your tables at:"
echo "https://supabase.com/dashboard/project/kzqrdtagpykoylhuqcyv/editor"
