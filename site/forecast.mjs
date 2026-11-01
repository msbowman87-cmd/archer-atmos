// Archer Atmos Analog 0.1 — an experimental independent, single-location model.
// This is NOT the globally trained research model and must not be used for alerts.
// Nothing at or after issueAt is eligible as forecast input.
const DAY_MS = 86_400_000;
const MAX_AGE_DAYS = 45;

export function isoDay(date) { return date.toISOString().slice(0, 10); }
export function startOfUtcDay(date) { return new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate())); }
export function daysAfter(date, delta) { return new Date(startOfUtcDay(date).getTime() + delta * DAY_MS); }
function isValid(value) { return Number.isFinite(value) && value > -900; }
function clamp(value, min, max) { return Math.min(max, Math.max(min, value)); }
function mean(values) { return values.reduce((sum, value) => sum + value, 0) / values.length; }
function std(values) { if (values.length < 2) return 0; const m = mean(values); return Math.sqrt(mean(values.map(v => (v-m)**2))); }
function doy(date) { return Math.floor((Date.UTC(2000, date.getUTCMonth(), date.getUTCDate()) - Date.UTC(2000, 0, 1)) / DAY_MS); }
function seasonDistance(a, b) { const delta = Math.abs(doy(a) - doy(b)); return Math.min(delta, 366 - delta); }

export function parsePowerData(payload, issueAt = new Date()) {
  const p = payload?.properties?.parameter;
  if (!p || !p.T2M_MAX || !p.T2M_MIN || !p.PRECTOTCORR || !p.WS10M) {
    throw new Error('NASA returned incomplete weather history. Please try again later.');
  }
  const rows = [];
  for (const stamp of Object.keys(p.T2M_MAX).sort()) {
    const date = new Date(`${stamp.slice(0,4)}-${stamp.slice(4,6)}-${stamp.slice(6,8)}T00:00:00Z`);
    const hi = Number(p.T2M_MAX[stamp]);
    const lo = Number(p.T2M_MIN[stamp]);
    const precip = Number(p.PRECTOTCORR[stamp]);
    const wind = Number(p.WS10M[stamp]);
    if (!Number.isFinite(date.getTime()) || date >= startOfUtcDay(issueAt)) continue;
    if (![hi,lo,precip,wind].every(isValid)) continue;
    if (hi < lo || hi > 70 || lo < -100 || precip < 0 || wind < 0) continue;
    rows.push({date, hi, lo, precip, wind});
  }
  if (rows.length < 365 * 5) throw new Error('There is not enough complete historical weather data at this location.');
  return rows;
}

function historicalSeason(rows, date, radius = 17) {
  const samples = rows.filter(row => seasonDistance(row.date, date) <= radius);
  if (samples.length < 100) throw new Error('The available archive does not cover this season well enough.');
  const highs = samples.map(row => row.hi);
  const lows = samples.map(row => row.lo);
  const rain = samples.map(row => row.precip);
  return {
    hi: mean(highs), lo: mean(lows), precip: mean(rain),
    rainChance: mean(rain.map(v => v >= 1 ? 1 : 0)),
    wind: mean(samples.map(row => row.wind)),
    highSpread: std(highs), lowSpread: std(lows), sampleDays: samples.length
  };
}

export function generateOutlook(history, issueAt = new Date(), horizon = 30) {
  if (!Array.isArray(history) || history.length < 365 * 5) throw new Error('A minimum of five years of weather history is required.');
  if (!Number.isInteger(horizon) || horizon < 1 || horizon > 30) throw new Error('Forecast horizon must be 1–30 days.');
  const cutoff = startOfUtcDay(issueAt);
  const safe = history.filter(row => row.date < cutoff).sort((a,b)=>a.date-b.date);
  if (safe.length < 365 * 5) throw new Error('Not enough observations existed before the forecast issue time.');
  const latest = safe[safe.length - 1];
  const gap = Math.round((cutoff.getTime() - latest.date.getTime()) / DAY_MS);
  if (gap > MAX_AGE_DAYS) throw new Error('The newest weather observation is too old for a useful outlook.');
  const recent = safe.slice(-Math.min(10, safe.length));
  const recentBase = recent.map(row => historicalSeason(safe.filter(s => s.date.getUTCFullYear() < row.date.getUTCFullYear()), row.date));
  const hiAnomaly = mean(recent.map((row, i) => row.hi - recentBase[i].hi));
  const loAnomaly = mean(recent.map((row, i) => row.lo - recentBase[i].lo));
  const windAnomaly = mean(recent.map((row, i) => row.wind - recentBase[i].wind));
  const recentWetRate = mean(recent.map(row => row.precip >= 1 ? 1 : 0));
  const baseWetRate = mean(recentBase.map(base => base.rainChance));
  const results = [];
  for (let lead = 1; lead <= horizon; lead++) {
    const date = daysAfter(issueAt, lead);
    const seasonal = historicalSeason(safe, date);
    const leadSinceLastMeasurement = lead + Math.max(0, gap - 1);
    // Seasonal anomaly persistence decays with lead and missing observations.
    const anomalyWeight = 0.65 * Math.exp(-leadSinceLastMeasurement / 6.5);
    const rainAnomalyWeight = 0.28 * Math.exp(-leadSinceLastMeasurement / 5);
    let hi = seasonal.hi + hiAnomaly * anomalyWeight;
    let lo = seasonal.lo + loAnomaly * anomalyWeight;
    if (lo > hi) [hi, lo] = [lo, hi];
    const rainChance = clamp(seasonal.rainChance + (recentWetRate - baseWetRate) * rainAnomalyWeight, 0, 1);
    const rainMeanWhenWet = seasonal.rainChance > 0.01 ? seasonal.precip / seasonal.rainChance : 0;
    results.push({
      lead, date: isoDay(date), hiC: hi, loC: lo,
      rainChance, precipMm: Math.max(0, rainMeanWhenWet * rainChance),
      windMs: Math.max(0, seasonal.wind + windAnomaly * anomalyWeight),
      highHistoricalSpreadC: seasonal.highSpread,
      lowHistoricalSpreadC: seasonal.lowSpread,
      historicalSampleDays: seasonal.sampleDays
    });
  }
  return {
    model: 'Archer Atmos Analog 0.1', issueAt: issueAt.toISOString(),
    lastObservedDate: isoDay(latest.date), historyStart: isoDay(safe[0].date),
    historicalDays: safe.length, gapDays: gap, experimental: true, forecasts: results
  };
}

export function toFahrenheit(c) { return c * 9/5 + 32; }
export function toMph(ms) { return ms * 2.2369363; }
