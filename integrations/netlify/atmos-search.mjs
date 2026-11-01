/**
 * Copy into the existing Netlify site's `netlify/functions/atmos-search.mjs`.
 * Requires `@netlify/blobs` in the site's package.json. Raw source inputs only.
 */
import { createHash } from 'node:crypto';

export const HOURLY = [
  'temperature_2m', 'relative_humidity_2m', 'dew_point_2m',
  'pressure_msl', 'surface_pressure', 'cloud_cover', 'precipitation',
  'rain', 'snowfall', 'wind_speed_10m', 'wind_direction_10m',
  'wind_gusts_10m', 'shortwave_radiation', 'visibility', 'cape',
  'temperature_850hPa', 'relative_humidity_700hPa',
  'wind_speed_500hPa', 'geopotential_height_500hPa',
];
export const DAILY = [
  'temperature_2m_max', 'temperature_2m_min', 'precipitation_sum',
  'precipitation_probability_max', 'snowfall_sum',
  'wind_speed_10m_max', 'wind_gusts_10m_max',
];

const PROVIDER = 'https://api.open-meteo.com/v1/forecast';
const CACHE_TTL_MS = 60 * 60 * 1000;
const STALE_LIMIT_MS = 6 * 60 * 60 * 1000;

export function coordinates(latText, lonText) {
  if (!latText || !lonText) throw new RangeError('lat and lon are required');
  const lat = Number(latText);
  const lon = Number(lonText);
  if (!Number.isFinite(lat) || !Number.isFinite(lon) || lat < -90 ||
      lat > 90 || lon < -180 || lon > 180) {
    throw new RangeError('lat must be -90..90 and lon must be -180..180');
  }
  return [Number(lat.toFixed(4)), Number(lon.toFixed(4))];
}

export function region(lat, lon, radiusKm = 200) {
  const latDelta = radiusKm / 111.2;
  const lonDelta = radiusKm / (111.2 * Math.max(0.1, Math.cos(lat * Math.PI / 180)));
  const wrap = (v) => ((v + 180) % 360 + 360) % 360 - 180;
  const candidates = [[lat, lon], [Math.min(90, lat + latDelta), lon],
    [Math.max(-90, lat - latDelta), lon], [lat, wrap(lon + lonDelta)],
    [lat, wrap(lon - lonDelta)]];
  const seen = new Set();
  return candidates.map(([a,b]) => [Number(a.toFixed(4)),Number(b.toFixed(4))])
    .filter(([a,b]) => {
      const id = `${a},${b}`;
      if (seen.has(id)) return false;
      seen.add(id);
      return true;
    }).map(([latitude,longitude]) => ({latitude,longitude}));
}

function jsonResponse(payload, status = 200, headers = {}) {
  return new Response(JSON.stringify(payload), {status, headers: {
    'Content-Type': 'application/json; charset=utf-8',
    'Cache-Control': 'no-store', 'Vary': 'Origin', ...headers,
  }});
}

async function fetchPoint(point, days, fetchImpl) {
  const url = new URL(PROVIDER);
  for (const [key,value] of Object.entries({
    ...point, timezone: 'UTC', forecast_days: String(days),
    wind_speed_unit: 'ms', hourly: HOURLY.join(','), daily: DAILY.join(','),
  })) url.searchParams.set(key, value);
  const response = await fetchImpl(url, {
    headers: {'User-Agent': 'ArcherAtmosResearch/0.6'},
    signal: AbortSignal.timeout(15000),
  });
  if (!response.ok) throw new Error('Forecast provider HTTP error');
  const data = await response.json();
  if (!data || data.error || !Array.isArray(data.hourly?.time) ||
      !Array.isArray(data.hourly?.temperature_2m) ||
      data.hourly.time.length !== data.hourly.temperature_2m.length) {
    throw new Error('Forecast provider returned invalid hourly data');
  }
  return {point, data};
}

/** Tests inject an in-memory blob store, clock, and HTTP transport. */
export function createHandler({store, fetchImpl = fetch, now = () => Date.now(),
                               allowedOrigins = []}) {
  if (!store || typeof store.get !== 'function' || typeof store.setJSON !== 'function') {
    throw new TypeError('A durable shared blob store is required');
  }
  return async function handler(request) {
    const origin = request.headers.get('origin');
    const allowed = origin && (origin === new URL(request.url).origin || allowedOrigins.includes(origin));
    if (origin && !allowed) return jsonResponse({error: 'Origin not allowed'}, 403);
    const cors = allowed ? {'Access-Control-Allow-Origin': origin} : {};
    if (request.method === 'OPTIONS') return new Response(null, {
      status: 204, headers: {...cors, 'Access-Control-Allow-Methods': 'GET, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type', 'Vary': 'Origin'},
    });
    if (request.method !== 'GET') return jsonResponse({error:'GET only'}, 405, cors);

    const url = new URL(request.url);
    let lat, lon, days;
    try {
      [lat,lon] = coordinates(url.searchParams.get('lat'), url.searchParams.get('lon'));
      const daysText = url.searchParams.get('days') || '16';
      if (!/^(?:[1-9]|1[0-6])$/.test(daysText)) throw new RangeError('days must be 1..16');
      days = Number(daysText);
    } catch (error) {
      return jsonResponse({error:error.message}, 400, cors);
    }

    const id = createHash('sha256').update(`v1:${lat}:${lon}:${days}:200`).digest('hex');
    const key = `inputs/v1/${id}`;
    const stamp = now();
    let cached;
    try {
      cached = await store.get(key, {type:'json'});
    } catch {
      return jsonResponse({error:'Shared cache unavailable; provider request not attempted'}, 503, cors);
    }
    const age = cached ? stamp - cached.saved_at_ms : NaN;
    const ttl = cached?.ttl_ms ?? CACHE_TTL_MS;
    if (Number.isFinite(age) && age >= 0 && age < ttl && cached.result) {
      return jsonResponse({...cached.result, cache_status:'hit', cache_age_seconds:Math.floor(age/1000)}, 200, cors);
    }

    try {
      const points = region(lat,lon);
      const attempts = await Promise.allSettled(points.map(p => fetchPoint(p,days,fetchImpl)));
      if (attempts[0].status !== 'fulfilled') throw new Error('Center forecast unavailable');
      const samples = attempts.filter(r => r.status === 'fulfilled').map(r => r.value);
      const result = {
        status:'raw_model_inputs_not_calibrated',
        warning:samples.length === points.length
          ? 'Provider model inputs only; not a verified or corrected Atmos forecast'
          : 'Regional context incomplete; these are uncalibrated provider model inputs',
        requested_location:{latitude:lat,longitude:lon},
        region_radius_km:200, forecast_days:days,
        retrieved_at_utc:new Date(stamp).toISOString(), model_issue_time_utc:null,
        source:'Open-Meteo Forecast API (verify license before commercial use)',
        regional_points_requested:points.length,regional_points_received:samples.length,
        samples,
      };
      await store.setJSON(key, {saved_at_ms:stamp,
        ttl_ms:samples.length === points.length ? CACHE_TTL_MS : 300_000,result});
      return jsonResponse({...result,cache_status:'miss',cache_age_seconds:0},200,cors);
    } catch {
      if (Number.isFinite(age) && age >= ttl &&
          age < STALE_LIMIT_MS && cached?.result) {
        return jsonResponse({...cached.result, cache_status:'stale',
          cache_age_seconds:Math.floor(age/1000),
          warning:'Stale model inputs; upstream unavailable. Do not treat as a current forecast.'},200,cors);
      }
      return jsonResponse({error:'Weather inputs unavailable; try again later',
        status:'provider_unavailable'},502,{...cors,'Retry-After':'60'});
    }
  };
}

export default async function handler(request) {
  // The package is resolved from the existing Netlify site on deployment.
  const {getStore} = await import('@netlify/blobs');
  const store = getStore('atmos-live-search-v1',
    {region:process.env.ATMOS_BLOB_REGION || 'us-east-2'});
  const origins = (process.env.ATMOS_ALLOWED_ORIGINS || '').split(',')
    .map(s => s.trim()).filter(Boolean);
  return createHandler({store,allowedOrigins:origins})(request);
}

export const config = {path:'/api/atmos/inputs'};
