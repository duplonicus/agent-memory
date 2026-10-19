# How tide predictions work

## Harmonic constants
Each station has amplitude and phase for 37 constituents (M2, S2, K1, O1 ...). The height at time t is the sum of the constituent cosines plus the datum offset.

## Why local math
The NOAA API rate-limited the app at about 30 charts a minute during the first load test. Computing locally takes 2 ms per chart.

## Accuracy check
Six stations were compared against published NOAA predictions for March: all within 3 cm. The other 34 have not been checked.
