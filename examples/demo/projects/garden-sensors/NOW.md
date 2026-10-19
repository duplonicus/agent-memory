# Garden sensors — NOW

Updated: 2026-03-14 by Claude Code · s:7f3a91c2

## State
- Four ESP32 soil-moisture probes report every 10 minutes over MQTT to the broker on the home server.
- 30-day battery test started 2026-03-14 on probe 3 (2 x AA lithium).

## Where things live
- Firmware in firmware/, the Grafana dashboard JSON in dashboards/.

## Next
1. Read probe 3's battery voltage on 2026-04-13 and decide the sleep interval.
2. Waterproof the probe heads before the spring rain.

## Decisions (incl. things decided against)
- 2026-03-14, Sam: decided against solar panels for now; batteries first, solar only if the test shows under 3 months per pair.
- 2026-03-05, Sam: MQTT, not HTTP polling. The probes sleep between readings.

## Open threads (waiting on whom)
- Waiting on Ines: whether the shed has a spare outlet for the gateway. (review by 2026-03-21)
- Waiting on the battery test: the sleep interval. (review by 2026-04-13)

## Gotchas
- Probe 2 reads 8% high when the soil is frozen; ignore readings below 0 °C.
