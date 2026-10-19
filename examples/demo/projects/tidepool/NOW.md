# Tidepool — NOW

Updated: 2026-03-14 by Claude Code · s:9a7f3b11

## State
- Tide charts render from local harmonic math (no NOAA calls at view time); staging is live, production is not.
- Tests: 212 passing at commit 4e1d0aa.

## Where things live
- Code in src/, station constants in data/stations/, notes in state/.
- Staging runs on Marco's spare VPS.

## Next
1. Swap in the new palette once Priya sends it.
2. Production deploy after the palette lands.

## Decisions (incl. things decided against)
- 2026-03-09, Sam: predictions come from local harmonic constants, not the NOAA API at view time. The API rate-limited us at 30 charts a minute.
- 2026-03-10, Sam: decided against a native mobile app; the PWA covers offline charts.
- 2026-03-12, Sam: no user accounts in v1. Favourite stations live in local storage.

## Open threads (waiting on whom)
- Waiting on Priya: the colour-blind-safe palette for the tide bands. (review by 2026-03-20)
- Waiting on Marco: whether the VPS can take production traffic, or we move to a paid host. (review by 2026-04-01)
- Claimed, not verified: the harmonic math matches NOAA within 3 cm for all 40 stations (checked 6 of them).

## Gotchas
- Station times are stored in UTC; the chart converts to the station's zone, not the viewer's.
