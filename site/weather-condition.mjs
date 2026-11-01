/**
 * WMO daily weather interpretation codes from Open-Meteo.
 * The daily code describes the most significant modeled condition, not the
 * probability that the entire day will have that condition.
 */
const conditions = new Map([
  [0,['Clear sky','clear']],
  [1,['Mostly clear','clear']],
  [2,['Partly cloudy','partly']],
  [3,['Overcast','cloudy']],
  [45,['Fog','fog']],
  [48,['Freezing fog','fog']],
  [51,['Light drizzle','rain']],
  [53,['Drizzle','rain']],
  [55,['Heavy drizzle','rain']],
  [56,['Freezing drizzle','rain']],
  [57,['Freezing drizzle','rain']],
  [61,['Light rain','rain']],
  [63,['Rain','rain']],
  [65,['Heavy rain','rain']],
  [66,['Freezing rain','rain']],
  [67,['Heavy freezing rain','rain']],
  [71,['Light snow','snow']],
  [73,['Snow','snow']],
  [75,['Heavy snow','snow']],
  [77,['Snow grains','snow']],
  [80,['Light showers','rain']],
  [81,['Rain showers','rain']],
  [82,['Heavy showers','rain']],
  [85,['Snow showers','snow']],
  [86,['Heavy snow showers','snow']],
  [95,['Thunderstorms','storm']],
  [96,['Thunderstorm with hail','storm']],
  [97,['Heavy thunderstorms','storm']],
  [99,['Thunderstorm with hail','storm']],
]);

export function describeWeather(code) {
  const value = Number.isInteger(code) ? conditions.get(code) : null;
  return value ? {label:value[0],kind:value[1]} :
    {label:'Condition unavailable',kind:'unknown'};
}

export function precipitationPercent(chance) {
  return Number.isFinite(chance) ? `${Math.round(Math.max(0,Math.min(1,chance))*100)}%` : '—';
}
