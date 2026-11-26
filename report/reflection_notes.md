# Reflection notes (kept as we go; section i of the report is written from these)

Dated, factual notes about what actually happened. Not polished.

## Phase 1

- **2026-11-26: starting question.** "Does rain delay, flatten or worsen Bengaluru's evening PM2.5 peak, and on which weekdays and months is the evening pollution rush worst?" Decision: when to issue evening pollution alerts, and whether rain-day rules need different timing.
- **2026-11-26: build environment.** The scaffold was written in a sandbox that could not reach api.openaq.org or archive-api.open-meteo.com (blocked by its network policy). So no source has been confirmed yet. The smoke test (`src/00_smoke_test.py`) has to be run on a teammate's laptop after M1. Lesson: "test that each API actually returns data" is a real step, not a formality.
- **2026-11-26: OpenAQ docs check.** The docs give the query-parameter spelling as `datetimeFrom` in one place, while the API reference uses `datetime_from`. To avoid trusting a silently ignored filter, both scripts check that the returned timestamps fall inside the requested range.
- **2026-11-26: Google Trends granularity.** For a 14-month range Trends returns weekly values, not hourly. So Trends can only add context at the week level. It cannot explain individual evenings.
- **2026-11-26: first real smoke test (teammate laptop, Arch Linux).** Open-Meteo PASS: 24/24 hours on 2025-10-01, and `boundary_layer_height` is available. OpenAQ: the key works and 25 locations were found, but the first monitor picked ('Peenya, Bengaluru - KSPCB', sensor 13852) had 0 hours on 2025-10-01. The empty result (not an error) suggests the date filter works and this sensor id is stale. That is our first "station ID change" case. The smoke test now only tries monitors whose first/last dates span the test day.
