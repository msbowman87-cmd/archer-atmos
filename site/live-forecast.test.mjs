import test from 'node:test';
import assert from 'node:assert/strict';
import {fetchNumericalForecast} from './live-forecast.mjs';

const issueAt = new Date('2026-11-01T10:00:00Z');
const location = {lat:42.98961, lon:-116.09343};

function payload() {
  const time = ['2026-11-01','2026-11-02','2026-11-03','2026-11-04','2026-11-05'];
  return {status:'raw_model_inputs_not_calibrated',
    retrieved_at_utc:'2026-11-01T09:00:00.000Z',
    cache_status:'hit', regional_points_requested:5,regional_points_received:5,
    samples:[{data:{daily:{time,temperature_2m_max:[10,11,12,13,14],
      temperature_2m_min:[1,2,3,4,5],precipitation_sum:[0,1,2,3,4],
      precipitation_probability_max:[0,10,20,30,40],
      wind_speed_10m_max:[1,2,3,4,5]}}}],
  };
}

test('site uses relative same-origin backend and preserved forecast fields',async()=>{
  const requests=[];
  const result=await fetchNumericalForecast(location,issueAt,async url=>{
    requests.push(String(url));return {ok:true,json:async()=>payload()};
  });
  assert.equal(requests.length,1);
  assert.match(requests[0],/^\/api\/atmos\/inputs\?/);
  assert.equal(new URL(`https://archer-atmos.netlify.app${requests[0]}`).searchParams.get('days'),'16');
  assert.equal(result.forecasts.length,4);
  assert.equal(result.forecasts[0].rainChance,0.1);
  assert.equal(result.forecasts[0].lead,1);
  assert.equal(result.model_issue_time_utc,null);
  assert.equal(result.retrieved_at_utc,'2026-11-01T09:00:00.000Z');
  assert.equal(result.cache_status,'hit');
});

test('site rejects malformed, unavailable, or falsely calibrated backend payloads',async()=>{
  await assert.rejects(()=>fetchNumericalForecast(location,issueAt,
    async()=>({ok:false,status:503})),/503/);
  await assert.rejects(()=>fetchNumericalForecast(location,issueAt,
    async()=>({ok:true,json:async()=>({...payload(),status:'calibrated'})})),/incomplete/);
  await assert.rejects(()=>fetchNumericalForecast(location,issueAt,
    async()=>({ok:true,json:async()=>({...payload(),samples:[]})})),/incomplete/);
});
