import test from 'node:test';
import assert from 'node:assert/strict';
import {describeWeather,precipitationPercent} from './weather-condition.mjs';

test('WMO codes render clear, cloudy, wet, snow and severe conditions without invented confidence',()=>{
  assert.deepEqual(describeWeather(0),{label:'Clear sky',kind:'clear'});
  assert.deepEqual(describeWeather(2),{label:'Partly cloudy',kind:'partly'});
  assert.deepEqual(describeWeather(3),{label:'Overcast',kind:'cloudy'});
  assert.deepEqual(describeWeather(45),{label:'Fog',kind:'fog'});
  assert.deepEqual(describeWeather(65),{label:'Heavy rain',kind:'rain'});
  assert.deepEqual(describeWeather(75),{label:'Heavy snow',kind:'snow'});
  assert.deepEqual(describeWeather(95),{label:'Thunderstorms',kind:'storm'});
});

test('unknown and historical-analog days never receive fictional sky conditions',()=>{
  assert.deepEqual(describeWeather(null),{label:'Condition unavailable',kind:'unknown'});
  assert.equal(describeWeather(999).kind,'unknown');
  assert.equal(describeWeather(undefined).kind,'unknown');
});

test('probability displays are bounded and missing values remain unavailable',()=>{
  assert.equal(precipitationPercent(0.936),'94%');
  assert.equal(precipitationPercent(1.5),'100%');
  assert.equal(precipitationPercent(-1),'0%');
  assert.equal(precipitationPercent(NaN),'—');
});
