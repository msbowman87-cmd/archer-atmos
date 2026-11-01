# Existing Atmos site: staged GitHub-to-Netlify rollout

As of 2026-11-01, the public website is
`https://archer-atmos.netlify.app/`, Netlify project `archer-atmos`, project ID
`a2908bb3-c9b3-4ca2-a8b0-ff394e1bdc6b`. It uses **Netlify Drop** for
deployment; GitHub commits alone cannot update the existing production site.
The latest manual production deployment observed before this change was
`6ae607f04d236732fd99ba2b` (2026-10-31).

## What is staged

* `site/` contains the live site's current HTML, CSS, chart and historical
  fallback sources, including its existing look and location search.
* `site/live-forecast.mjs` now requests **the same site's**
  `/api/atmos/inputs`, instead of calling the weather provider directly.
* `netlify/functions/atmos-search.mjs` serves that route via a site-wide
  Netlify Blobs cache. It fetches a center and at most four regional points,
  19 hourly variables and seven daily variables, for up to 16 days. Raw
  third-party model outputs are **not** independently calibrated Atmos forecasts.
* Netlify build uses `site` as publish directory. The functions, dependency
  code, and research files are deliberately outside that public directory.
* `npm run test:site` checks the staged browser adapter and source syntax.
  The UI disables its 30-day selection for the shorter live-model forecast;
  that range remains available with the historical fallback.

## Launch checklist (owner approval required)

1. Review and merge the staged site PR, after its offline tests pass.
2. In the **existing** Netlify project, connect the GitHub repository
   `msbowman87-cmd/archer-atmos` with base directory as repository root,
   publish directory `site`, and functions directory `netlify/functions`.
   Confirm before authorizing repository access or altering the production
   deployment method. A Git connection can trigger an immediate production build.
3. Confirm that the project remains on a **no-paid-upgrade** configuration and
   that usage/spend limits, especially Functions and Blobs, are acceptable.
   A public cache is not an absolute free-usage guarantee; unique-coordinate
   searches still call the upstream provider up to five times on a cache miss.
   Open-Meteo's public free API is **non-commercial use only** and requires
   attribution; do not activate this version for subscriptions, advertisements,
   commercial promotion, or undisclosed commercial research without arranging
   a properly licensed feed or replacing it with eligible public NOAA data.
4. Test `/api/atmos/inputs?lat=42.98961&lon=-116.09343&days=16` on a
   non-production preview first. Check `status`, `regional_points_received`,
   the daily outlook, and cache hit on a repeated request.
5. Only then allow the Git-backed branch to publish as production. Verify a
   second location outside the US and monitor usage and failed requests.

## Rollback

Keep the existing known-good Netlify Drop production deploy
`6ae607f04d236732fd99ba2b` available in Netlify deploy history. If the
new service cannot fetch/cache weather data or there are unexpected usage
charges, republish that deploy through Netlify's deploy list and disable
automatic deploys until corrected. Do not assume the historic Drop build
has the new `/api/atmos/inputs` route.

## Limits and provenance

The Open-Meteo Forecast API is a third-party model provider; check the exact
license/terms before using a commercial service. Netlify Blobs is a managed
service, not unlimited free storage. Forecast source issue time is currently
unknown and the website labels the backend timestamp as **retrieved**, not
**issued**. Independent worldwide station verification, calibration, and
durable backfill storage remain separate, unfinished research tasks.
