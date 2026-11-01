import { fetchNumericalForecast } from './live-forecast.mjs';
import { parsePowerData, generateOutlook, toFahrenheit, toMph, daysAfter, isoDay } from './forecast.mjs';
import { describeWeather, precipitationPercent } from './weather-condition.mjs';

const locations = {
  'grand-view': {name:'Grand View, Idaho', lat:42.98961, lon:-116.09343},
  seattle: {name:'Seattle, Washington', lat:47.6062, lon:-122.3321},
  miami: {name:'Miami, Florida', lat:25.7617, lon:-80.1918},
  tokyo: {name:'Tokyo, Japan', lat:35.6762, lon:139.6503}
};
const $ = (id) => document.getElementById(id);
const all = (selector) => Array.from(document.querySelectorAll(selector));
const cache = new Map();
let currentLocation = locations['grand-view'];
let latestOutlook = null;
let selectedDays = 7;
let requestId = 0;

function displayCoord(lat, lon) {
  return `${Math.abs(lat).toFixed(4)}° ${lat >= 0 ? 'N':'S'}, ${Math.abs(lon).toFixed(4)}° ${lon >= 0 ? 'E':'W'}`;
}
function dayLabel(iso, options) { return new Date(`${iso}T12:00:00Z`).toLocaleDateString('en-US',{timeZone:'UTC',...options}); }
function fmt(value) { return Math.round(value).toLocaleString('en-US'); }
function setBusy(message) {
  $('run-state').textContent = `◉  ${message}`;
  $('run-cutoff').textContent = 'Requesting current numerical model inputs or an archival fallback';
  $('search-button').disabled = true;
  $('search-button').textContent = 'Loading…';
  $('forecast-error').hidden = true;
}
function setIdle() {
  $('search-button').disabled = false;
  $('search-button').innerHTML = 'Explore <span aria-hidden="true">↗</span>';
}
function setError(message) {
  $('forecast-error').hidden = false;
  $('forecast-error').textContent = `${message} No forecast has been generated for this request. You can search again or try a sample location.`;
  $('run-state').textContent = 'Archive unavailable';
  $('run-cutoff').textContent = 'No successful forecast run';
  latestOutlook = null;
  for (const id of ['high-value','low-value','rain-value','wind-value']) $(id).textContent = '--';
  $('temperature-chart').replaceChildren();
  $('daily-strip').replaceChildren();
}

function dateStamp(date) { return isoDay(date).replaceAll('-',''); }
async function loadHistory(location, issueAt) {
  // NASA POWER's daily point data is free historical/reanalysis data, never an outside forecast.
  const tile = `${(Math.round(location.lat*2)/2).toFixed(1)},${(Math.round(location.lon*2)/2).toFixed(1)}`;
  const end = dateStamp(daysAfter(issueAt,-1));
  const key = `${tile}:${end}`;
  if (cache.has(key)) return cache.get(key);
  const storedKey = `atmos.power.v1.${key}`;
  try {
    const saved = JSON.parse(sessionStorage.getItem(storedKey) || 'null');
    if (saved && Date.now()-saved.savedAt < 8*3600*1000 && saved.data) {
      const rows = parsePowerData(saved.data,issueAt);
      cache.set(key,rows);return rows;
    }
  } catch {} // Browsers may disable sessionStorage.
  const params = new URLSearchParams({parameters:'T2M_MAX,T2M_MIN,PRECTOTCORR,WS10M',community:'AG',latitude:String(location.lat),longitude:String(location.lon),start:'19810101',end,format:'JSON','time-standard':'UTC'});
  const url = `https://power.larc.nasa.gov/api/temporal/daily/point?${params}`;
  const controller = new AbortController();
  const timeout = setTimeout(()=>controller.abort(),45000);
  try {
    const response = await fetch(url,{signal:controller.signal});
    if (!response.ok) throw new Error(`NASA returned HTTP ${response.status}.`);
    const payload = await response.json();
    const rows = parsePowerData(payload,issueAt);
    cache.set(key,rows);
    try { sessionStorage.setItem(storedKey, JSON.stringify({savedAt:Date.now(),data:payload})); } catch {}
    return rows;
  } catch (error) {
    if (error.name==='AbortError') throw new Error('The historical data request timed out.');
    throw error;
  } finally { clearTimeout(timeout); }
}

function svg(tag, attrs, text) {
  const item = document.createElementNS('http://www.w3.org/2000/svg',tag);
  Object.entries(attrs || {}).forEach(([name,value])=>item.setAttribute(name,String(value)));
  if (text!==undefined) item.textContent = text;
  return item;
}
function weatherIcon(kind) {
  const icon=svg('svg',{viewBox:'0 0 48 48',class:'daily-weather-icon','aria-hidden':'true'});
  const add=(tag,attrs,label)=>icon.append(svg(tag,attrs,label));
  const sun=(cx,cy,r)=>{
    add('circle',{cx,cy,r,fill:'#ffdda0',stroke:'#e8a04b','stroke-width':2});
    for(let i=0;i<8;i++){
      const a=i*Math.PI/4;
      add('line',{x1:cx+Math.cos(a)*(r+3),y1:cy+Math.sin(a)*(r+3),
        x2:cx+Math.cos(a)*(r+7),y2:cy+Math.sin(a)*(r+7),
        stroke:'#e8a04b','stroke-width':2.2,'stroke-linecap':'round'});
    }
  };
  const cloud=()=>add('path',{d:'M12 34h23c4.6 0 7.5-3.2 7.5-7.2S39.5 20 35 20h-1.2c-1.3-6-5.7-9.7-11.5-9.7-6.4 0-10.5 4.4-11.7 10.2C6.3 21.1 4 24 4 27.5 4 31.3 7.2 34 12 34Z',
    fill:'#e7f1f7',stroke:'#6c93ab','stroke-width':2,'stroke-linejoin':'round'});
  if(kind==='clear') sun(24,24,9);
  else if(kind==='partly'){sun(17,16,7);cloud();}
  else if(kind==='unknown'){
    add('circle',{cx:24,cy:24,r:17,fill:'#edf3f6',stroke:'#a4b8c5','stroke-width':2});
    add('text',{x:24,y:32,'text-anchor':'middle',fill:'#688094','font-size':22,'font-weight':700},'?');
  }else{
    cloud();
    if(kind==='fog') for(const y of [39,44]) add('line',{x1:10,x2:39,y1:y,y2:y,stroke:'#83a4b8','stroke-width':2,'stroke-linecap':'round'});
    if(kind==='rain') for(const x of [15,26,37]) add('line',{x1:x+1,x2:x-2,y1:38,y2:44,stroke:'#429dce','stroke-width':2.7,'stroke-linecap':'round'});
    if(kind==='snow') for(const x of [15,26,37]){
      add('line',{x1:x,y1:37,x2:x,y2:45,stroke:'#429dce','stroke-width':2});
      add('line',{x1:x-3,y1:41,x2:x+3,y2:41,stroke:'#429dce','stroke-width':2});
    }
    if(kind==='storm')add('path',{d:'M27 32 19 42h6l-3 5 13-13h-7l4-5',fill:'#f7b44a',stroke:'#d89931','stroke-width':1.3,'stroke-linejoin':'round'});
  }
  return icon;
}
function renderChart(forecasts) {
  const target = $('temperature-chart');target.replaceChildren();
  target.setAttribute('aria-label', `${forecasts.length}-day high/low temperature outlook, UTC daily periods`);
  const width=900, height=218, left=32,right=10,top=19,bottom=32;
  const temps=forecasts.flatMap(row=>[toFahrenheit(row.hiC),toFahrenheit(row.loC)]);
  const lo=Math.floor((Math.min(...temps)-6)/10)*10, hi=Math.ceil((Math.max(...temps)+6)/10)*10;
  const X=i=>left+(width-left-right)*(i/Math.max(1,forecasts.length-1));
  const Y=v=>top+(height-top-bottom)*(hi-v)/Math.max(10,hi-lo);
  for(let t=lo;t<=hi;t+=10){const y=Y(t);target.append(svg('line',{x1:left,x2:width-right,y1:y,y2:y,stroke:'#e4eef3','stroke-dasharray':'4 7'}));target.append(svg('text',{x:0,y:y+4,fill:'#90a6b5','font-size':12,'font-family':'DM Sans'},String(t)));}
  const hiPoints=forecasts.map((r,i)=>`${X(i)},${Y(toFahrenheit(r.hiC))}`).join(' ');
  const loPoints=forecasts.map((r,i)=>`${X(i)},${Y(toFahrenheit(r.loC))}`).join(' ');
  target.append(svg('polyline',{points:hiPoints,fill:'none',stroke:'#f49c68','stroke-width':3,'stroke-linejoin':'round','stroke-linecap':'round'}));
  target.append(svg('polyline',{points:loPoints,fill:'none',stroke:'#4eaecc','stroke-width':3,'stroke-linejoin':'round','stroke-linecap':'round'}));
  const labelStep=forecasts.length>14?5:forecasts.length>7?2:1;
  forecasts.forEach((r,i)=>{
    const x=X(i),h=Y(toFahrenheit(r.hiC)),l=Y(toFahrenheit(r.loC));
    if (forecasts.length <= 14 || i % 2===0) {
      const topDot=svg('circle',{cx:x,cy:h,r:3,fill:'#f49c68'});
      topDot.append(svg('title',{},`${r.date}: high ${Math.round(toFahrenheit(r.hiC))}°F`));target.append(topDot);
      const lowDot=svg('circle',{cx:x,cy:l,r:3,fill:'#4eaecc'});
      lowDot.append(svg('title',{},`${r.date}: low ${Math.round(toFahrenheit(r.loC))}°F`));target.append(lowDot);
    }
    if(i%labelStep===0){target.append(svg('text',{x,y:height-9,'text-anchor':'middle',fill:'#8a9ead','font-size':11,'font-family':'DM Sans'},dayLabel(r.date,{month:'short',day:'numeric'})));}
  });
}
function showDayDetails(r) {
  const dialog=$('day-details');
  $('day-details-title').textContent=dayLabel(r.date,{weekday:'long',month:'long',day:'numeric',year:'numeric'});
  const condition=describeWeather(r.weatherCode);
  const live=Boolean(latestOutlook?.source);
  const fields=[
    ['Weather condition',condition.label],
    ['High temperature',Number.isFinite(r.hiC)?`${Math.round(toFahrenheit(r.hiC))} °F`:'Unavailable'],
    ['Low temperature',Number.isFinite(r.loC)?`${Math.round(toFahrenheit(r.loC))} °F`:'Unavailable'],
    [live?'Peak hourly precipitation chance':'Estimated wet-day chance',Number.isFinite(r.rainChance)?precipitationPercent(r.rainChance):'Unavailable'],
    ['Expected precipitation',Number.isFinite(r.precipMm)?`${(r.precipMm/25.4).toFixed(2)} in (${r.precipMm.toFixed(1)} mm)`:'Unavailable'],
    [live?'Maximum wind speed':'Estimated average wind',Number.isFinite(r.windMs)?`${Math.round(toMph(r.windMs))} mph`:'Unavailable'],
    ['Forecast lead',Number.isFinite(r.lead)?`Day ${r.lead}`:'Unavailable']
  ];
  const grid=$('day-details-grid');grid.replaceChildren();
  fields.forEach(([name,value])=>{const cell=document.createElement('div');cell.className='detail-cell';const a=document.createElement('span');a.textContent=name;const b=document.createElement('strong');b.textContent=value;cell.append(a,b);grid.append(cell)});
  $('day-details-note').textContent=live?'Daily weather code shows the most significant modeled condition; the percentage is the highest hourly precipitation chance, not a confidence score. Live numerical model inputs are not independently calibrated.':'Experimental historical-analog outlook, not a live numerical forecast. Sky conditions are unavailable; wet-day percentages are experimental estimates, not accuracy scores.';
  if(typeof dialog.showModal==='function')dialog.showModal();else dialog.hidden=false;
}
function renderDailyCards(forecasts) {
  const target=$('daily-strip');target.replaceChildren();
  target.style.gridTemplateColumns=`repeat(${Math.min(forecasts.length,7)},minmax(118px,1fr))`;
  const live=Boolean(latestOutlook?.source);
  forecasts.forEach(r=>{
    const day=dayLabel(r.date,{weekday:'long',month:'long',day:'numeric'});
    const condition=describeWeather(r.weatherCode);
    const hi=Number.isFinite(r.hiC)?`${fmt(toFahrenheit(r.hiC))}°`:'—';
    const lo=Number.isFinite(r.loC)?`${fmt(toFahrenheit(r.loC))}°`:'—';
    const wind=Number.isFinite(r.windMs)?`${fmt(toMph(r.windMs))} mph`:'—';
    const chance=precipitationPercent(r.rainChance);
    const card=document.createElement('button');card.type='button';card.className='daily-chip';
    card.setAttribute('aria-label',`${day}. ${condition.label}. High ${hi}, low ${lo}. ${live?'Peak hourly precipitation chance':'Estimated wet-day chance'} ${chance}. ${live?'Maximum':'Average'} wind ${wind}. View details.`);
    card.addEventListener('click',()=>showDayDetails(r));
    const date=document.createElement('strong');date.className='daily-chip-date';date.textContent=dayLabel(r.date,{weekday:'short',day:'numeric'});
    const sky=document.createElement('span');sky.className='daily-chip-sky';sky.append(weatherIcon(condition.kind));
    const name=document.createElement('span');name.className='daily-chip-condition';name.textContent=condition.label;
    const temps=document.createElement('span');temps.className='daily-chip-temperatures';
    const high=document.createElement('b');high.className='daily-chip-high';high.textContent=hi;
    const low=document.createElement('b');low.className='daily-chip-low';low.textContent=lo;
    temps.append(high,low);
    const likelihood=document.createElement('span');likelihood.className='daily-chip-likelihood';
    const pct=document.createElement('b');pct.textContent=chance;
    const pctLabel=document.createElement('small');pctLabel.textContent=live?'Peak precip':'Wet-day est.';
    likelihood.append(pct,pctLabel);
    const breeze=document.createElement('span');breeze.className='daily-chip-wind';breeze.textContent=`Wind ${wind} ${live?'max':'avg'}`;
    card.title=`${day}: ${condition.label}; high ${hi}, low ${lo}; ${live?'peak hourly precipitation':'estimated wet-day'} chance ${chance}; wind ${wind}`;
    card.append(date,sky,name,temps,likelihood,breeze);target.append(card);
  });
}
function renderOutlook() {
  if(!latestOutlook)return;
  const info=latestOutlook, first=info.forecasts[0];
  if(info.source && selectedDays>info.forecasts.length) selectedDays=14;
  $('high-value').textContent=fmt(toFahrenheit(first.hiC));
  $('low-value').textContent=fmt(toFahrenheit(first.loC));
  $('rain-value').textContent=fmt(first.rainChance*100);
  $('wind-value').textContent=fmt(toMph(first.windMs));
  $('high-footnote').textContent=`${dayLabel(first.date,{weekday:'short',month:'short',day:'numeric'})} · UTC day`;
  const rows=info.forecasts.slice(0,selectedDays);renderChart(rows);renderDailyCards(rows);
  $('rain-label').textContent=info.source?'PEAK PRECIP. CHANCE':'WET-DAY ESTIMATE';
  $('rain-footnote').textContent=info.source?'Highest hourly precipitation chance':'Estimated chance of ≥1 mm';
  $('wind-label').textContent=info.source?'MAX WIND':'AVERAGE WIND';
  $('wind-footnote').textContent=info.source?'10-meter daily maximum':'10-meter daily mean';
  $('daily-strip-note').textContent=info.source?'Icon: most significant modeled condition · %: highest hourly precipitation chance, not forecast confidence.':'Historical fallback: precipitation % is an experimental wet-day estimate; sky conditions are unavailable.';
  $('run-state').textContent=info.source ? '● Live numerical forecast ready' : '● History-based outlook ready';
  $('run-cutoff').textContent=info.source ? 'Live forecast model · Not independently verified by Atmos' : `Last available day: ${info.lastObservedDate} UTC · ${info.historicalDays.toLocaleString()} valid days`;
  $('forecast-data-status').textContent=info.source ? `${info.model} · Retrieved ${new Date(info.retrieved_at_utc || info.issueAt).toLocaleString()} · Model run time unavailable · Source: Open-Meteo` : `Atmos Analog 0.1 · Issued ${new Date(info.issueAt).toLocaleString()} · Archive ${info.historyStart}–${info.lastObservedDate} UTC`;
  all('[data-days]').forEach(button=>{const n=Number(button.dataset.days);const active=n===selectedDays;button.disabled=Boolean(info.source && n>info.forecasts.length);button.title=button.disabled?'30-day outlook is available only with the experimental historical fallback':'';button.classList.toggle('selected',active);button.setAttribute('aria-pressed',String(active));});
}
async function runForecast(location) {
  const thisRequest=++requestId;
  const issueAt=new Date(); // captured once; model and API use the same information cutoff
  currentLocation=location;
  $('place-name').textContent=location.name;
  $('place-coordinates').textContent=displayCoord(location.lat,location.lon);
  setBusy('Requesting live forecast');
  try {
    try {
      const live=await fetchNumericalForecast(location,issueAt);
      if(thisRequest!==requestId)return;
      latestOutlook=live;renderOutlook();return;
    } catch (liveError) {
      setBusy('Live forecast unavailable; loading experimental historical outlook');
    }
    const history=await loadHistory(location,issueAt);
    if(thisRequest!==requestId)return;
    const info=generateOutlook(history,issueAt,30);
    if(thisRequest!==requestId)return;
    latestOutlook=info;
    renderOutlook();
  }catch(error){if(thisRequest===requestId)setError(error.message || 'The historical API could not be reached.');}
  finally{if(thisRequest===requestId)setIdle();}
}
async function resolveLocation(query) {
  const coords=query.match(/^\s*(-?\d+(?:\.\d+)?)\s*[, ]\s*(-?\d+(?:\.\d+)?)\s*$/);
  if(coords){const lat=Number(coords[1]),lon=Number(coords[2]);if(lat<-90||lat>90||lon<-180||lon>180)throw new Error('Coordinates must be latitude −90 to 90 and longitude −180 to 180.');return {name:`Coordinates ${lat.toFixed(3)}, ${lon.toFixed(3)}`,lat,lon};}
  if(query.trim().length<2)throw new Error('Please enter a city name or coordinates.');
  const parts=query.split(',').map(s=>s.trim());
  const city=parts[0];
  const region=parts.slice(1).join(' ').toLowerCase();
  const regions={id:'idaho',or:'oregon',wa:'washington',ca:'california',fl:'florida',ny:'new york',tx:'texas',ut:'utah',nv:'nevada',az:'arizona',co:'colorado',mt:'montana',wy:'wyoming',ak:'alaska',hi:'hawaii',uk:'united kingdom'};
  const wanted=regions[region]||region;
  // A geocoding service supplies ONLY coordinates. It is not a weather/forecast provider.
  const url=`https://geocoding-api.open-meteo.com/v1/search?name=${encodeURIComponent(city)}&count=100&language=en&format=json`;
  const response=await fetch(url);
  if(!response.ok)throw new Error('Location lookup is currently unavailable.');
  const data=await response.json();
  const matches=data.results||[];
  const found=wanted ? matches.find(item=>[item.admin1,item.country,item.country_code].some(value=>String(value||'').toLowerCase()===wanted)) : matches[0];
  if(!found)throw new Error('No matching place was found. Try a larger nearby city or coordinates.');
  return {name:[found.name,found.admin1,found.country].filter(Boolean).join(', '),lat:found.latitude,lon:found.longitude};
}

$('location-form').addEventListener('submit',async event=>{
  event.preventDefault();
  const query=$('location-input').value;
  const button=$('search-button');button.disabled=true;button.textContent='Finding…';
  try {const place=await resolveLocation(query);await runForecast(place);$('forecast').scrollIntoView({behavior:'smooth'});}
  catch(error){setError(error.message);setIdle();$('forecast').scrollIntoView({behavior:'smooth'});}
});
all('[data-location]').forEach(button=>button.addEventListener('click',()=>{const location=locations[button.dataset.location];$('location-input').value=location.name;runForecast(location);$('forecast').scrollIntoView({behavior:'smooth'});}));
all('[data-days]').forEach(button=>button.addEventListener('click',()=>{selectedDays=Number(button.dataset.days);renderOutlook();}));
$('year').textContent=String(new Date().getFullYear());
runForecast(currentLocation);
