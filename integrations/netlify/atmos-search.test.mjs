import test from 'node:test';
import assert from 'node:assert/strict';
import {createHandler, coordinates, region} from './atmos-search.mjs';

function fixture({fail = false, centerOnly = false} = {}) {
  const objects = new Map();
  const store = {
    async get(k) {return objects.get(k) ?? null;},
    async setJSON(k,v) {objects.set(k,v);},
  };
  let calls = 0;
  const fetchImpl = async (url) => {
    calls++;
    if (fail || (centerOnly && calls > 1)) throw new Error('provider offline');
    assert.equal(url.hostname,'api.open-meteo.com');
    return {ok:true,async json() {return {hourly:{time:['2026-11-01T00:00'],temperature_2m:[9]},daily:{time:[]}};}};
  };
  let clock = 100_000_000;
  const handler = createHandler({store,fetchImpl,now:()=>clock,
    allowedOrigins:['https://archer-atmos.netlify.app']});
  const query = (path='?lat=42.4818&lon=-114.4877') => new Request(`https://archer-atmos.netlify.app/api/atmos/inputs${path}`);
  return {handler,query,advance(ms){clock+=ms;},get calls(){return calls;},store};
}

test('global coordinate validation including antimeridian and poles',()=>{
  assert.deepEqual(coordinates('90','180'),[90,180]);
  assert.ok(region(90,179.5).every(p=>p.longitude>=-180 && p.longitude<=180));
  for (const pair of [['','0'],['NaN','0'],['91','0'],['0','181'],['Infinity','0']]) {
    assert.throws(()=>coordinates(...pair),RangeError);
  }
});

test('first search fetches at most five, next search uses the shared one-hour cache',async()=>{
  const f=fixture();
  const first=await (await f.handler(f.query())).json();
  assert.equal(first.status,'raw_model_inputs_not_calibrated');
  assert.equal(first.cache_status,'miss');
  assert.equal(first.regional_points_received,5);
  assert.equal(first.model_issue_time_utc,null);
  assert.equal(f.calls,5);
  f.advance(50_000);
  const second=await (await f.handler(f.query())).json();
  assert.equal(second.cache_status,'hit');
  assert.equal(second.cache_age_seconds,50);
  assert.equal(f.calls,5);
});

test('bad coordinates, over-budget days and disallowed origins are rejected without calls',async()=>{
  const f=fixture();
  assert.equal((await f.handler(f.query('?lat=91&lon=0'))).status,400);
  assert.equal((await f.handler(f.query('?lat=1&lon=1&days=17'))).status,400);
  const bad=new Request(f.query().url,{headers:{origin:'https://untrusted.test'}});
  assert.equal((await f.handler(bad)).status,403);
  assert.equal(f.calls,0);
});

test('partial region labels missing context; stale fallback does not masquerade as current',async()=>{
  const f=fixture({centerOnly:true});
  const r=await (await f.handler(f.query())).json();
  assert.equal(r.regional_points_received,1);
  assert.equal(r.regional_points_requested,5);
  f.advance(3_700_000);
  // The mock center fails on its second call; stale data is clearly marked.
  assert.equal((await (await f.handler(f.query())).json()).cache_status,'stale');
});

test('no cache service fails closed before requesting external API',async()=>{
  const f=fixture();
  f.store.get=async()=>{throw Error('offline');};
  const r=await f.handler(f.query());
  assert.equal(r.status,503);
  assert.equal(f.calls,0);
});

test('expired cache returns clearly marked stale content if provider fails',async()=>{
  const f=fixture();
  await f.handler(f.query());
  f.advance(3_700_000);
  // A malformed HTTP response simulates an upstream outage.
  const h=createHandler({store:f.store,now:()=>103_700_000,
    fetchImpl:async()=>{throw Error('unavailable');}});
  const res=await (await h(f.query())).json();
  assert.equal(res.cache_status,'stale');
  assert.match(res.warning,/Stale/);
});
