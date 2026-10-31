# PokerHUD — Collector #1 Project Charter

**Status:** Controlling project objective  
**Scope:** PokerBet only  
**Priority:** Absolute — no other work is authorized until the collector passes validation.

## 1. Primary objective

Build and prove a reliable PokerBet data collector that continuously discovers and captures all tournament and table data that is technically accessible to the authorized collection session.

The deliverable is a clean, consistent, timestamped historical dataset. The collector is the entire project until this objective is achieved.

## 2. Priority rule

Nothing unrelated to collecting, preserving, validating, or recovering PokerBet data may be built, improved, or maintained during this phase.

Explicitly out of scope:
- HUDs, overlays, dashboards, and frontend work
- Player statistics, poker analytics, and reports unrelated to collection validation
- AI, machine learning, player modelling, and advice
- Equity calculations and bot/remote-control functionality
- SunBet or other poker-site integrations
- Duplicate backends, legacy services, and unrelated infrastructure

Existing code may be reused only when it directly supports the PokerBet collector. Do not rewrite working components without evidence that the change is necessary.

## 3. Core definitions

These terms define what the collector is expected to find and preserve.

| Term | Definition |
|---|---|
| **Tournament** | A PokerBet scheduled or running poker event, identified by its stable source identifier wherever available. |
| **Table** | A live poker table associated with a tournament. A table must have a stable source identifier where available and must be linked to its tournament. |
| **Player observation** | A timestamped observation of a player at a table, including the source-provided identity, seat, stack, and other available fields. |
| **Hand** | One poker hand played at a table, identified by a source hand ID where available or by a documented, deterministic fallback. |
| **Action** | A player action within a hand, such as fold, check, call, bet, raise, or all-in, including its order and available amount. |
| **Table snapshot** | A timestamped representation of the table at a particular observation: seats, players, stacks, blinds, ante, pot, board, hand state, and other exposed fields. |
| **Tournament snapshot** | A timestamped observation of tournament status and available lifecycle fields, such as entries, remaining players, tables, blinds, level, and prize pool. |
| **Raw event** | The original source response or captured source payload, preserved before parsing or transformation. |
| **Normalized record** | A structured representation derived from raw data, with its source, identifiers, capture time, parser version, and data-quality status. |
| **Dataset** | The accumulated raw events and normalized records, with relationships between sites, tournaments, tables, hands, players, and actions. |
| **Coverage gap** | An expected observation or record that could not be collected, with the reason recorded where known. |

## 4. Collection requirements

The collector must:

1. Discover all tournaments exposed by PokerBet to the collection session.
2. Discover all accessible tables for those tournaments.
3. Monitor accessible tables continuously for as long as they remain available.
4. Capture every available hand and its exposed actions.
5. Capture player, seat, stack, blind, ante, pot, board, and table-state information wherever exposed.
6. Capture tournament and table lifecycle changes.
7. Timestamp every observation and retain source identifiers.
8. Preserve original raw payloads before parsing.
9. Normalize data without losing the original source representation.
10. Detect and record failed captures, missing fields, interruptions, and coverage gaps.
11. Recover after process or network interruptions without silently losing history.
12. Prevent duplicate logical records while retaining meaningful repeated observations over time.

The collector must not fabricate values, infer unavailable actions as facts, or silently discard malformed or incomplete source data.

## 5. Data integrity principles

- **Raw before parse:** preserve the original payload before transformation.
- **Traceability:** every normalized record must be traceable to its source capture.
- **Time awareness:** distinguish event time from collection time.
- **Stable identity:** use source IDs wherever available; document fallback identity rules.
- **Honest completeness:** unknown or unavailable fields remain unknown.
- **Visible failures:** failed requests, parser errors, gaps, and restarts must be measurable.
- **Idempotent processing:** replaying the same source event must not create duplicate logical entities.
- **Durability:** collected history must survive process restarts and application upgrades.

## 6. Proof required before this phase is complete

A running process or a successful test suite is not sufficient proof.

The collector must demonstrate:

- Tournament discovery against the live PokerBet source.
- Table discovery and tournament-to-table relationships.
- Consistent collection across multiple tables.
- Hand and action capture wherever the source exposes them.
- Correct player, seat, and stack observations.
- Durable raw-payload preservation.
- Correct normalized records and source traceability.
- Duplicate handling and restart recovery.
- Measured uptime, capture failures, missing observations, and coverage gaps.
- Reconciliation against what was actually visible and accessible at the source.

Run a minimum 24-hour uninterrupted validation period after the core pipeline is stable. Produce an evidence report with discovered tournaments, discovered tables, monitored tables, captured hands and actions, uptime, failures, duplicates, and unexplained gaps.

**Scope limitation:** “All” means all data technically exposed and accessible to the authorized collection session. Do not claim complete platform-wide coverage unless it has been independently demonstrated. Any source-side restriction must be documented as a coverage limitation.

## 7. Cleanup rule

Repository cleanup is subordinate to the collector objective.

Before removing anything:
1. Inventory the file and its dependencies.
2. Determine whether it contributes to PokerBet discovery, table capture, hand capture, storage, validation, or recovery.
3. Preserve and test any required functionality.
4. Remove unrelated or duplicate functionality only after confirming it is not required.
5. Keep the repository focused on the collector and its tests.

Do not delete historical data, credentials/configuration required for authorized collection, or useful raw fixtures as part of source cleanup. Secrets must not be committed.

## 8. Completion gate

**No other product work begins until Collector #1 has passed the validation requirements in this charter and the evidence has been reviewed.**

After that gate is met, the next project priority must be explicitly approved. This document defines the objective; it does not authorize unrelated implementation.

---
