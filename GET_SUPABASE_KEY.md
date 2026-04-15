# Get Your Supabase API Key

## Step 1: Get Your Anon Key

1. Go to: https://supabase.com/dashboard/project/kzqrdtagpykoylhuqcyv/settings/api

2. Look for **Project API keys** section

3. Copy the **anon / public** key (starts with `eyJ...`)

## Step 2: Update the Configuration

Once you have the key, run this command (replace YOUR_KEY with the actual key):

```bash
cd /opt/pokerhud/pokerhud

# Update shared/utils/supabase.ts
sed -i "s|YOUR_ANON_KEY_HERE|YOUR_KEY|g" shared/utils/supabase.ts

# Update check-migrations.js
sed -i "s|YOUR_ANON_KEY_HERE|YOUR_KEY|g" check-migrations.js

# Rebuild extension
npm run build:extension
```

## OR: Tell me the key and I'll update it for you

Just paste the anon key here and I'll update everything.

---

**Your Project:**
- URL: https://kzqrdtagpykoylhuqcyv.supabase.co
- Dashboard: https://supabase.com/dashboard/project/kzqrdtagpykoylhuqcyv
- API Settings: https://supabase.com/dashboard/project/kzqrdtagpykoylhuqcyv/settings/api
