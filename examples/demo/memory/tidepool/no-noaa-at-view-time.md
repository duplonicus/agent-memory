---
name: no-noaa-at-view-time
description: tide charts must not call the NOAA API while a user waits
type: feedback
supersedes: noaa-cache-ttl
---

Tide predictions are computed locally from harmonic constants; the NOAA API only refreshes the constants, nightly.

**Why:** the API rate-limited the app at about 30 charts a minute in the first load test (2026-03-09).

**How to apply:** any new chart or widget gets its numbers from the harmonics module, never from a live API call.
