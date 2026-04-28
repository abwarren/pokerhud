# Testing Patterns

**Analysis Date:** 2026-04-29

## Test Framework

**Runner:**
- Jest (configured in `pokerhud/jest.config.js`)
- Preset: `ts-jest` for TypeScript support
- Test environment: `node`
- Note: Jest and ts-jest are NOT installed in `node_modules` — the config exists but dependencies are missing

**Assertion Library:**
- Jest built-in `expect` (imported from `@jest/globals`)

**E2E Framework:**
- Playwright (referenced in `package.json` scripts as `test:e2e`)
- Not installed — no Playwright config file or dependencies found

**Run Commands:**
```bash
npm test              # Run all Jest tests (pokerhud/ workspace root)
npm run test:e2e      # Playwright tests (not configured)
```

## Test File Organization

**Location:**
- Separate `tests/` directory at workspace root: `pokerhud/tests/`
- Pattern: Tests are NOT co-located with source files

**Naming:**
- `{module}.test.ts` (e.g., `parser.test.ts`, `stats.test.ts`)

**Structure:**
```
pokerhud/
├── tests/
│   ├── parser.test.ts     # Tests for shared/utils/parser.ts
│   └── stats.test.ts      # Tests for shared/utils/stats-calculator.ts + player-classifier.ts
├── jest.config.js         # Jest configuration
└── shared/                # Source modules being tested
```

## Test Structure

**Suite Organization:**
```typescript
import { describe, it, expect } from '@jest/globals';
import { parseCards, parseAction, parseHandHistory } from '../shared/utils/parser';

describe('PokerNow Parser', () => {
  describe('parseCards', () => {
    it('should parse cards with unicode suits', () => {
      const cards = parseCards('[2♠, Q♥, Q♠]');
      expect(cards).toHaveLength(3);
      expect(cards[0]).toEqual({ rank: '2', suit: '♠' });
    });
  });
});
```

**Patterns:**
- Nested `describe` blocks for grouping related functionality
- `it('should ...')` for test case descriptions (behavior-driven naming)
- Direct imports from `@jest/globals` (not relying on global Jest)
- No setup/teardown (`beforeEach`/`afterEach`) — tests are stateless
- Each test creates its own input data inline

## Module Name Mapping

**Path aliases in tests:**
```javascript
// jest.config.js
moduleNameMapper: {
  '^@shared/(.*)$': '<rootDir>/shared/$1'
}
```

This mirrors the `@shared/*` alias used in production code via tsconfig paths.

## Test Coverage

**Current test files (2 files):**
1. `pokerhud/tests/parser.test.ts` — Tests card parsing, action parsing, URL extraction, hand history parsing
2. `pokerhud/tests/stats.test.ts` — Tests player classification (TAG/LAG/LP/Unknown) and threat level calculation

**What is tested:**
- Card string parsing (unicode suits and letter suits)
- Action line parsing (fold, bet, raise, post blind)
- Game ID extraction from URLs
- Complete hand history parsing from log lines
- Player type classification thresholds
- Threat level calculation from aggregate stats

**What is NOT tested:**
- Extension content scripts (DOM scraping, site detection)
- Background service worker message handling
- Supabase client operations
- React components (no component tests)
- Python scripts (no Python test framework)
- Stats calculator individual functions (calculateVPIP, calculatePFR, etc.)
- Auth utilities
- Alias detection
- Hand advisor / AI integration
- Import processor

**Coverage enforcement:** None (no coverage thresholds configured, no CI pipeline)

## Mocking

**Framework:** Not used

**Current approach:**
- All tests use pure function testing — no external dependencies to mock
- Parser tests use inline string data as input
- Stats tests use manually constructed `AggregateStats` objects
- No network calls, no database calls, no Chrome API calls in test paths

**What would need mocking (if coverage expands):**
- `chrome.storage.local` — for extension popup/background tests
- `@supabase/supabase-js` — for data layer tests
- `fetch` / `openrouter` — for AI service tests
- DOM APIs — for content script observer tests

## Fixtures and Factories

**Test Data:**
```typescript
// Inline fixture — hand history log lines
const logLines = [
  '-- starting hand #355 (id: 4axrao1nqq06) (Pot Limit Omaha Hi) (dealer: Tanush) --',
  'Player stacks: #2 Amay jsr (505.06) | #3 Tanush (1031.50) | #5 AK 2.0 (1217.37)',
  'AK 2.0 posts a small blind of 1.00',
  // ...
  '-- ending hand #355 --'
];

// Inline fixture — stats object
const stats: AggregateStats = {
  vpip: 22,
  pfr: 18,
  three_bet: 8,
  hands: 100
} as AggregateStats;
```

**Location:**
- No separate fixtures directory
- All test data is defined inline within test files
- Type assertions (`as AggregateStats`) used to avoid providing all fields for partial test objects

## Integration Test Scripts

**Ad-hoc integration tests (NOT part of test suite):**
- `pokerhud/test_pokernow_integration.js` — Runs against live Supabase to test user/game/player CRUD
- `pokerhud/test_tournaments.js` — Queries Supabase for tournament data
- `pokerhud/flask_api_test.py` — Standalone Flask server to test extension snapshot receipt
- `pokerhud/test_server.py` — Minimal Flask snapshot receiver for manual testing

These are NOT automated tests — they are manual verification scripts that hit real databases.

## Test Types

**Unit Tests:**
- Located in `pokerhud/tests/`
- Test pure utility functions (parser, classifier)
- No external dependencies
- Fast, deterministic, stateless

**Integration Tests:**
- No formal integration test framework
- Manual scripts in project root that hit live Supabase
- No test database or fixtures infrastructure

**E2E Tests:**
- Playwright mentioned in `package.json` scripts but NOT implemented
- No test configuration or test files for E2E

## Common Patterns

**Parsing Tests:**
```typescript
it('should parse cards with unicode suits', () => {
  const cards = parseCards('[2♠, Q♥, Q♠]');
  expect(cards).toHaveLength(3);
  expect(cards[0]).toEqual({ rank: '2', suit: '♠' });
});
```

**Classification Tests:**
```typescript
it('should classify TAG player', () => {
  const stats: AggregateStats = {
    vpip: 22, pfr: 18, three_bet: 8, hands: 100
  } as AggregateStats;
  
  const type = classifyPlayerType(stats);
  expect(type).toBe('TAG');
});
```

**Edge Case Tests:**
```typescript
it('should return Unknown for low sample', () => {
  const stats: AggregateStats = {
    vpip: 30, pfr: 20, three_bet: 8, hands: 15
  } as AggregateStats;
  
  const type = classifyPlayerType(stats);
  expect(type).toBe('Unknown');
});
```

## Gaps and Recommendations

**Critical gaps:**
- Jest/ts-jest not installed — tests cannot currently run (`npm test` will fail)
- No CI pipeline — tests are never automatically executed
- Only 2 test files covering 2 of 8+ shared utility modules
- No component tests for React UI
- No Python test framework for workers/scrapers
- No test database setup for integration tests

**Test infrastructure needed to run existing tests:**
```bash
# Install missing dependencies
npm install --save-dev jest ts-jest @jest/globals @types/jest
```

**Module path resolution:**
- Tests import from relative paths (`../shared/utils/parser`)
- `moduleNameMapper` in jest config provides `@shared/*` alias support

---

*Testing analysis: 2026-04-29*
