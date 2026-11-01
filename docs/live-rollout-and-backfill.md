# Atmos rollout: global inputs, shared cache, durable historical collection

Status: **code is staged in the research repository; the existing Netlify site
is hosted separately and is not deployed from this repository.** These files
cannot change the public site until its source/deployment connection is known.

## 1. Search-time weather inputs

Deploy `integrations/netlify/atmos-search.mjs` in the **existing Atmos Netlify
site's** `netlify/functions/atmos-search.mjs`, and add `@netlify/blobs` to that
site's package dependencies with a committed lockfile. Do not create a second
public Atmos site. The function is then served as:

```
GET /api/atmos/inputs?lat=42.4818&lon=-114.4877&days=16
```

The endpoint validates global latitude/longitude values, samples a 200 km
regional context (center plus four directions), requests 19 hourly and seven
daily Open-Meteo variables, and stores results in the **site-wide** Netlify
Blobs namespace `atmos-live-search-v1`, shared between function instances and
deployments. Cache lifetime is one hour for complete regional retrievals and
five minutes when any surrounding point is missing. If the provider goes down, previously
cached values less than six hours old may be returned with `cache_status=stale`
and an explicit warning; older entries are not served. A cache outage returns
HTTP 503 **without calling the weather provider**, to avoid uncontrolled
request amplification. The Netlify Blob region defaults to `us-east-2` and
can be pinned with `ATMOS_BLOB_REGION` (do not change it after data is stored
without migrating the blobs).

If a different origin must read the API, configure `ATMOS_ALLOWED_ORIGINS` as
comma-separated exact origins, for example `https://app.example.com`.
Same-origin requests from the Atmos site work without an allowlist. The feed
includes precipitation probability and wind in m/s to match the existing
Atmos UI. A client
can extract the center's hourly series using:

```js
const r = await fetch(`/api/atmos/inputs?lat=${encodeURIComponent(lat)}&lon=${encodeURIComponent(lon)}`);
if (!r.ok) throw new Error(`Weather inputs unavailable (${r.status})`);
const inputs = await r.json();
// This is an uncalibrated MODEL INPUT, not an approved Atmos forecast.
const temperature = inputs.samples[0].data.hourly.temperature_2m;
```

The actual public homepage currently imports `./live-forecast.mjs`. Replace
that file in its existing source with
`integrations/netlify/live-forecast.mjs` to preserve the site's daily forecast
data structure while routing the live request through `/api/atmos/inputs`.
In `app.js`, change the live-model status display from **“Issued”** to
**“Retrieved”** and explicitly note **“model run time not provided”**. The
`issueAt` field in this compatibility adapter represents retrieval time;
claiming it was a source forecast issuance would be inaccurate. The current
UI renders only a subset of the new atmospheric variables; add dedicated
pressure, cloud, upper-air and hourly panels in a later frontend change.

**Before accepting public traffic:** confirm the site's commercial/noncommercial
status and source rights, configure platform-level rate limiting/abuse controls,
perform a production smoke test at equatorial, polar and antimeridian locations,
monitor provider errors/cache hit rate, and preserve a clear research label.
Origin headers alone are not authentication or a rate limit. The provider's
response does not reliably contain the forecast issue timestamp; the endpoint
reports `model_issue_time_utc: null` instead of inventing a run time.

## 2. Permanent historical archive

The scheduled workflow `.github/workflows/atmos-archival-backfill.yml` is
deliberately **paused unless both source-use approval and an S3-compatible
archive are configured**. It does not silently begin large API downloads on a
public repository. Set GitHub Actions repository variables:

| Variable | Value |
| --- | --- |
| `ATMOS_NONCOMMERCIAL_RESEARCH_APPROVED` | `true` only after confirming this collection is noncommercial and within provider terms |
| `ATMOS_ARCHIVE_BUCKET` | Dedicated S3-compatible bucket name |
| `ATMOS_ARCHIVE_REGION` | Region, e.g. `us-east-1` for AWS S3 or `auto` for R2 |
| `ATMOS_ARCHIVE_ENDPOINT` | Optional full HTTPS S3-compatible endpoint; omit for AWS S3 |

And GitHub Actions repository **secrets** (never commit values or paste them
into public issue comments):

- `ATMOS_ARCHIVE_ACCESS_KEY_ID`
- `ATMOS_ARCHIVE_SECRET_ACCESS_KEY`

Use narrowly scoped credentials permitted to read/write only the archive bucket
prefix; review provider storage/egress costs and retention policies beforehand.
The workflow refuses to make forecast-provider calls when any required
configuration is missing. Initialize the durable archive cursor before the
first schedule with a text object containing `0` at
`s3://BUCKET/atmos/rich/v1/grid-5000/cursor.txt` (for example using
`printf '0' | aws s3 cp - s3://BUCKET/atmos/rich/v1/grid-5000/cursor.txt`).
If the cursor cannot be read, the workflow fails **before** making provider
calls. It advances by four only after all four collection lanes and object
uploads succeed; a failed run is retried from the same starting wave. Manual
wave overrides do not advance it. There is no live connected archive today.

Once enabled, the schedule runs daily at 03:23 UTC. It uses four bounded
lanes, two simultaneously, each collecting five five-location monthly shards:
**20 shards / 100 site-months / day**, up to about 74,400 hourly location
rows and 1.1 million variable values for a 31-day month. This is an initial
controlled rate, not a claim of full global training coverage. Historical
months from 2024 and 2025 are interleaved, and shard order is permuted so early
waves include locations across multiple latitudes. Full two-year, 5,000-point
coverage is 24,000 five-point shards and takes 1,200 scheduled days at the
initial rate; raising throughput requires a quota/cost review and possibly a
bulk meteorological archive instead of per-coordinate requests.

Each shard is collected as CSV, schema- and row-count-checked, deterministically
gzip-compressed, and accompanied by a JSON manifest with both raw-provider
response hashes and archive SHA-256 hashes, missingness, retrieval time,
location count, and model-derived source classification. Archives are written
under `s3://BUCKET/atmos/rich/v1/grid-5000/` and backed by temporary 30-day
GitHub Actions artifacts. Each wave is deterministic and may be re-run using
the workflow's `wave_start` manual input (a multiple of four). A partial-source failure causes the
job to fail after packaging, while preserving available evidence for retry.

**Important:** Open-Meteo historical/reanalysis values are model-derived, not
independent weather-station observations. They are appropriate for features
and climatology, not as ground truth for model skill claims. Separately obtain
real observations, paired model issue/valid times, station metadata, local
time cutoffs and holdout periods before enabling calibration in production.

## 3. Remaining dependencies for full production operation

1. Identify the **source repository or deployment access** for
   `https://archer-atmos.netlify.app/` so the function can be installed in the
   actual site and hooked to its location-search interface.
2. Choose/create a dedicated object-storage bucket and configure the above
   GitHub variables/secrets after cost and license review. Do not repurpose
   unrelated Supabase or user application databases.
3. Validate a manual archival wave and verify the stored objects and hashes,
   then allow the daily schedule to collect bounded worldwide samples.
4. Establish independent station validation, fixed-run provenance, forecast
   error statistics by geography and lead time, and acceptance gates before
   labeling raw provider data as an Atmos calibrated prediction.

The target worldwide geographic reach comes from a global forecast provider;
the 5,000/20,000 point research grid is a **validation and history sampling
cohort**, not a geographic limitation of search-time forecasts.
