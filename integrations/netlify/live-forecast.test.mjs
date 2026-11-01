import test from 'node:test';
import assert from 'node:assert/strict';
import {fetchNumericalForecast} from './live-forecast.mjs';

test('site adapter preserves existing forecast format and labels retrieval time',async()=>{
  let calls=0;
  const fakeFetch=async path=>{
    calls++;
    assert.match(path,/^\/api\/atmos\/inputs\?/);
    assert.match(path,/days=16/);
    return {ok:true,async json(){return {
      status:'raw_model_inputs_not_calibrated',
      retrieved_at_utc:'2026-11-01T09:00:00Z',cache_status:'hit',
      regional_points_requested:5,regional_points_received:5,
      samples:[{data:{daily:{time:['2026-11-02','2026-11-03','2026-11-04'],
        temperature_2m_max:[10,11,12],temperature_2m_min:[1,2,3],
        precipitation_sum:[0,1,2],precipitation_probability_max:[20,30,40],
        wind_speed_10m_max:[5,6,7]}}}],
    };}};
  };
  const result=await fetchNumericalForecast({lat:0,lon:179.9},
    new Date('2026-11-01T12:00:00Z'),fakeFetch);
  assert.equal(calls,1);
  assert.equal(result.forecasts[0].windMs,5);
  assert.equal(result.forecasts[0].rainChance,0.2);
  assert.equal(result.model_issue_time_utc,null);
  assert.equal(result.retrieved_at_utc,'2026-11-01T09:00:00Z');
});

test('site adapter fails if weather data lacks required precipitation probability',async()=>{
  const fake=async()=>({ok:true,async json(){return {
    status:'raw_model_inputs_not_calibrated',retrieved_at_utc:'2026-11-01T09:00:00Z',
    samples:[{data:{daily:{time:['2026-11-02'],temperature_2m_max:[10],
      temperature_2m_min:[1],precipitation_sum:[0],wind_speed_10m_max:[5]}}}],
  };}});
  await assert.rejects(fetchNumericalForecast({lat:0,lon:0},
    new Date('2026-11-01T12:00:00Z'),fake),/Insufficient/);
});
