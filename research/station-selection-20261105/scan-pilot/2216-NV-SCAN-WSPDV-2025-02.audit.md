# Buckhorn hourly wind speed, February 2025

On November 20, 2026, the USDA NRCS AWDB request for station 2216:NV:SCAN, hourly WSPDV, February 1–28 inclusive, returned HTTP 503. No observation payload was received. This period remains retryable. The request sequence stopped at the 503, so March was not requested in this pass. The January archive was re-read from GitHub and its decompressed SHA-256 matched the collection audit.

A later paced retry on November 20 returned 669 of 672 distinct populated provider hours before quality screening. Three hours are missing from this response. The gzip preserves the original provider JSON, including measurements and flags. The decompressed SHA-256 is `81d739a324c41f385a56f034d4af623e8fc3b7a0da29ae468a496543f4f7e646`. March through December remain open.
