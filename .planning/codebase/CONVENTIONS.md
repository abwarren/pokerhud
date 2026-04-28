# Coding Conventions

**Analysis Date:** 2026-04-29

## Naming Patterns

**Files:**
- TypeScript source files: `kebab-case.ts` / `kebab-case.tsx` (e.g., `stats-calculator.ts`, `player-classifier.ts`, `site-detector.ts`)
- React components: `PascalCase.tsx` (e.g., `PlayerCard.tsx`, `MergeModal.tsx`, `Dashboard.tsx`)
- React pages: `PascalCase.tsx` in `pages/` directory (e.g., `Games.tsx`, `Players.tsx`)
- Type definition files: `lowercase.ts` in `types/` directory (e.g., `hand.ts`, `player.ts`, `stats.ts`)
- Python scripts: `snake_case.py` (e.g., `snapshot_server.py`, `tournament_scraper.py`)
- Python workers: `worker{N}_{description}.py` (e.g., `worker1_lobby_scraper.py`, `worker5_timeseries_ledger.py`)
- JavaScript scrapers: `kebab-case.js` (e.g., `pokerbet.js`, `pokerbet-scraper-simple.js`)
- Config files: standard naming (e.g., `vite.config.ts`, `tailwind.config.js`, `tsconfig.json`)

**Functions:**
- TypeScript: `camelCase` (e.g., `calculateVPIP`, `parseHandHistory`, `extractGameIdFromUrl`)
- Python: `snake_case` (e.g., `receive_snapshot`, `strip_html`, `get_db_connection`)
- React components: `PascalCase` function components (e.g., `function PlayerCard()`, `function Dashboard()`)
- Event handlers: `handle` + action (e.g., `handleLogin`, `handleLogout`)

**Variables:**
- TypeScript: `camelCase` for local variables and parameters (e.g., `preflopActions`, `playerName`, `cardString`)
- Constants/config: `UPPER_SNAKE_CASE` (e.g., `POKERBET_SELECTORS`, `PATTERNS`, `DB_CONFIG`, `PARTNER_ID`)
- React state: `camelCase` with descriptive names (e.g., `isAuthenticated`, `liveGames`, `loading`)
- Python: `snake_case` for variables (e.g., `snapshot_count`, `poker_keywords`)

**Types:**
- Interfaces: `PascalCase` with descriptive nouns (e.g., `UnifiedPlayer`, `HandActions`, `AggregateStats`)
- Type aliases: `PascalCase` (e.g., `PlayerType`, `ThreatLevel`, `ActionType`, `Street`)
- Union types: string literal unions (e.g., `'fold' | 'check' | 'call' | 'bet' | 'raise'`)
- Enums: Not used; prefer union types with string literals

## Code Style

**Formatting:**
- No ESLint or Prettier configuration detected
- Indentation: 2 spaces (TypeScript/TSX/JS), 4 spaces (Python)
- Semicolons: Used consistently in TypeScript
- Quotes: Single quotes for TypeScript imports and strings
- Trailing commas: Used in multi-line objects and arrays
- Line length: No enforced limit; lines typically stay under 120 characters

**Linting:**
- No dedicated linting tool (no `.eslintrc`, `.prettierrc`, `biome.json`)
- TypeScript `strict: true` serves as primary code quality enforcement
- `noUnusedLocals: true` and `noUnusedParameters: true` in tsconfig
- `noFallthroughCasesInSwitch: true` enabled

## TypeScript Configuration

**Strict mode enabled across all workspaces:**
- `strict: true`
- `noUnusedLocals: true`
- `noUnusedParameters: true`
- `noFallthroughCasesInSwitch: true`
- Target: `ES2020`
- Module: `ESNext` with `bundler` resolution
- JSX: `react-jsx` (automatic JSX transform)

## Import Organization

**Order (observed pattern):**
1. React imports (`import { useEffect, useState } from 'react'`)
2. Third-party libraries (`import { createClient } from '@supabase/supabase-js'`)
3. Path-aliased shared imports (`import type { UnifiedPlayer } from '@shared/types'`)
4. Relative imports (`import Login from './pages/Login'`)

**Path Aliases:**
- `@shared/*` maps to `../shared/*` (used in both extension and web workspaces)
- Configured in both `tsconfig.json` and `vite.config.ts` for runtime resolution

**Type-only imports:**
- Use `import type { ... }` for type-only imports (e.g., `import type { Hand, AggregateStats } from '../types'`)
- Inline dynamic type references with `import('./stats').AggregateStats` for circular-safe cross-references

## Error Handling

**Patterns:**
- TypeScript async functions: try/catch with `console.error` and return `null` or fallback value
- Supabase calls: Check `error` property and return `null` on failure
- Parser: Wrap each line in try/catch, accumulate errors in `context.errors[]` array, continue parsing
- Python Flask routes: try/except with JSON error response (`return jsonify({'success': False, 'error': str(e)}), 400`)

**Example (TypeScript - Supabase call):**
```typescript
const { data, error } = await supabase.from('users').select('*').eq('id', userId).single();
if (error) {
  console.error('Error fetching user:', error);
  return null;
}
return data as User;
```

**Example (TypeScript - Parser resilience):**
```typescript
try {
  parseLine(line, context);
} catch (error) {
  context.errors.push(`Error parsing line ${i}: ${line} - ${error}`);
}
```

## Logging

**Framework:** `console` (browser + Node.js)

**Patterns:**
- Extension background: `console.log('PokerBet HUD: Background service worker started')`
- Parser diagnostics: `console.log('Parsed', count, 'hands, errors:', errors.length)`
- Python: `logging` module with named loggers and file handlers
- Python log format: `'%(asctime)s [MODULE] %(levelname)s - %(message)s'`
- Python Flask: `print()` for console output in dev, `logging` for production workers

## Comments

**When to Comment:**
- Section separators: Use `// ============================================` blocks for major code sections
- File headers: Block comments with purpose description (both TS and Python use docstrings/comments at top)
- Inline comments: Used to explain poker domain logic (e.g., "// BB who just checks doesn't VPIP")
- Constants: Inline comments explain stat meanings (e.g., `af: number; // Aggression factor`)

**Section Comment Pattern (TypeScript):**
```typescript
// ============================================
// MAIN PARSER FUNCTION
// ============================================
```

**Python Docstrings:**
```python
"""
Worker 1: Lobby Scraper
=======================
Scrapes PokerBet tournament lobby for available/upcoming tournaments.
Runs every 5 minutes to discover new tournaments.
"""
```

**JSDoc/TSDoc:**
- Used selectively on exported utility functions
- Brief `/** ... */` style (e.g., `/** Classify player type based on VPIP and PFR */`)
- Not enforced for all exports

## Function Design

**Size:**
- Utility functions: typically 10-40 lines
- Calculator functions: 30-80 lines (poker stat calculations are necessarily detailed)
- No enforced maximum, but functions are focused on single responsibilities

**Parameters:**
- TypeScript: Use typed parameters with interfaces for complex objects
- Helper functions accept `hands: Hand[]` and `playerName: string` consistently
- Props interfaces for React components: `interface DashboardProps { userId: string; onLogout: () => void; }`

**Return Values:**
- `null` for not-found / error cases (never `undefined` for explicit absence)
- Percentage stats returned as 0-100 numbers (not 0-1 fractions)
- Complex functions return typed objects (e.g., `{ flop: number; turn: number; river: number }`)

## Module Design

**Exports:**
- Named exports preferred over default exports for utility modules
- Default exports used for React components (`export default App`)
- Barrel files (`index.ts`) re-export all from sub-modules (`export * from './player'`)

**Barrel Files:**
- `pokerhud/shared/index.ts`: Re-exports all shared utilities and types
- `pokerhud/shared/types/index.ts`: Re-exports all type modules
- Used for clean import paths from `@shared/...`

## React Patterns

**Component Style:**
- Functional components only (no class components)
- Hooks for state (`useState`, `useEffect`, `useRef`)
- Props passed via typed interface
- Tailwind CSS for all styling (no CSS modules, no styled-components)

**State Management:**
- Local state with `useState` (no Redux/Zustand/Context API detected)
- `localStorage` for auth persistence in web app
- `chrome.storage.local` for extension state persistence
- Polling with `setInterval` for real-time data refresh

**CSS Approach:**
- Tailwind CSS with custom theme colors (`poker-bg-primary`, `poker-accent-green`, etc.)
- Dark theme only; consistent color palette across extension and web
- PostCSS + Autoprefixer configured in both workspaces

## Python Conventions

**Flask API Pattern:**
```python
app = Flask(__name__)
CORS(app)

@app.route('/api/endpoint', methods=['POST'])
def handler():
    data = request.get_json(silent=True) or {}
    # process...
    return jsonify({"ok": True})
```

**Worker Script Pattern:**
- Standalone `#!/usr/bin/env python3` scripts
- Module docstring describing purpose and schedule
- `DB_CONFIG` dict for database credentials
- `logging.basicConfig()` with file + stream handlers
- `if __name__ == '__main__':` entry point

---

*Convention analysis: 2026-04-29*
