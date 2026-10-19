---
name: probe-sleep
description: probes deep-sleep between readings; wake interval is the battery knob
type: project
review_by: 2026-04-13
contradicts: always-on-gateway-probe
---

Each probe deep-sleeps between readings. The wake interval (10 minutes today) is what sets battery life.

**Why:** a probe left awake drained a pair of AAs in four days.

**How to apply:** change the interval, not the radio power, when battery life is short.
