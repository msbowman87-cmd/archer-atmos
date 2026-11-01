/**
 * Live weather-model inputs for the existing public Atmos interface.
 * Netlify maintains a shared short-lived cache and regional samples;
 * these provider models are not yet independently calibrated by Atmos.
 */
export async function fetchNumericalForecast(location, issueAt = new Date(), fetchImpl = fetch) {
  const query = new URLSearchParams({lat:String(location.lat),lon:String(location.lon),days:'16'});
  const response = await fetchImpl(`/api/atmos/inputs?${query}`);
  if (!response.ok) throw new Error(`Atmos weather-input service returned ${response.status}`);
  const payload = await response.json();
  if (payload.status !== 'raw_model_inputs_not_calibrated' ||
      !Array.isArray(payload.samples) || payload.samples.length === 0) {
    throw new Error('Atmos provider input response is incomplete');
  }
  const daily = payload.samples[0].data?.daily;
  if (!daily || !Array.isArray(daily.time)) {
    throw new Error('Live daily forecast input is missing');
  }
  const today = issueAt.toISOString().slice(0,10);
  const forecasts = daily.time.map((date,i) => ({
    date,
    weatherCode:Number.isInteger(daily.weather_code?.[i]) ? daily.weather_code[i] : null,
    hiC:daily.temperature_2m_max?.[i],
    loC:daily.temperature_2m_min?.[i],
    precipMm:daily.precipitation_sum?.[i],
    rainChance:daily.precipitation_probability_max?.[i] / 100,
    windMs:daily.wind_speed_10m_max?.[i],
    lead:Math.round((Date.parse(`${date}T00:00:00Z`)-
      Date.parse(`${today}T00:00:00Z`))/86400000),
  })).filter(row => row.date > today &&
    [row.hiC,row.loC,row.precipMm,row.rainChance,row.windMs].every(Number.isFinite));
  if (forecasts.length < 3) throw new Error('Insufficient valid future daily inputs');
  return {
    model:'Open-Meteo numerical inputs (center point; regional context collected)',
    issueAt:payload.retrieved_at_utc, // UI compatibility only; not the model issue time.
    model_issue_time_utc:null,
    retrieved_at_utc:payload.retrieved_at_utc,
    experimental:false,
    source:'Open-Meteo via Atmos shared-cache data acquisition (uncalibrated)',
    cache_status:payload.cache_status,
    regional_points_requested:payload.regional_points_requested,
    regional_points_received:payload.regional_points_received,
    forecasts,
  };
}
