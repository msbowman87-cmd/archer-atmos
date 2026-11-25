# Buckhorn SCAN 2216 location audit

Compared the provider coordinates (40.87959, -119.95340, 6,470 ft) with all 6,809 rows of the frozen station manifest. The nearest selected station was GHCNH:USI0000KSVE (Susanville Muni) at 76.621 km by great-circle distance (Earth radius 6,371 km). No selected station was inside the 500 m deduplication threshold, and the manifest contained no Buckhorn name or 2216-NV identifier. This check applies to the frozen inventory. It does not establish distinctness against unselected candidates or overlap among calibration records.

The station manifest came from research release `research-hourly-44014385072-1-w0041`, part 0009. The downloaded ZIP SHA-256, `2da3639e81631748e2ab085f891662578a75873482b6fb35108a8fb8850d22c6`, matched the release index. The extracted `stations.csv` SHA-256, `59c8b81c025dd752a2b76cadca8815805adcad04a6935274d524f24c1cb3ef06`, matched collection run 44049002889's frozen-input verification.

Buckhorn remains supplemental. The 2019 hourly TOBS provider response yielded no measurements, and the geographic check alone does not qualify its decade of coverage or establish ten overlapping calibration neighbors.
