# USCRN candidate distance audit

I downloaded the [collection checkpoint artifact](https://github.com/msbowman87-cmd/archer-atmos/actions/runs/42261055783/artifacts/13556821353). Its SHA-256 matched the GitHub artifact digest. The extracted 6,809-row stations.csv matched frozen manifest SHA-256 `59c8b81c025dd752a2b76cadca8815805adcad04a6935274d524f24c1cb3ef06`.

Using the coordinates in [the candidate evidence](uscrn-hourly-candidate-evidence.md), I compared each candidate against every manifest row using great-circle distance with a 6,371 km Earth radius. Neither the bare WBAN nor its USW000 form appeared as a station ID. All three had a selected neighbor within the existing 500 m conservative exclusion radius.

| Candidate WBAN | Closest selected station | Distance |
| --- | --- | ---: |
| 04130 | USC00247292, ST. MARY | 386.6 m |
| 04990 | USC00397662, SIOUX FALLS EROS CTR | 498.5 m |
| 94075 | USC00055881, NEDERLAND 5 NNW | 449.5 m |

No candidates were admitted. The distances establish proximity under the current selection rule. They do not establish that instruments are physically identical. Additional archive products at these sites could be evaluated as supplemental observations without counting the sites again.
