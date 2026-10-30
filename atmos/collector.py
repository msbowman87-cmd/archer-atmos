"""Bounded NOAA GFS collector for global point samples; research only."""
import argparse, hashlib, json, math, time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
BASE="https://nomads.ncep.noaa.gov/cgi-bin/filter_gfs_0p25.pl"
def point(lat,lon):
    if not all(map(math.isfinite,(lat,lon))) or not (-90<=lat<=90 and -180<=lon<=180): raise ValueError("Invalid coordinates")
    return round(lat,6),round(((lon+180)%360)-180,6)
def subset(lat,lon):
    lat,lon=point(lat,lon)
    a=max(-90,min(lat-.5,89));b=max(-180,min(lon-.5,179))
    return dict(leftlon=b,rightlon=b+1,bottomlat=a,toplat=a+1)
def url_for(date,cycle,step,lat,lon):
    datetime.strptime(date,"%Y%m%d")
    if cycle not in ("00","06","12","18") or step not in range(0,73,3): raise ValueError("Unsupported run")
    p={"file":f"gfs.t{cycle}z.pgrb2.0p25.f{step:03d}","dir":f"/gfs.{date}/{cycle}/atmos","subregion":""}
    p.update({f"var_{v}":"on" for v in ("TMP","UGRD","VGRD","APCP","RH","TCDC","PRMSL")})
    p.update({f"lev_{v}":"on" for v in ("2_m_above_ground","10_m_above_ground","surface","entire_atmosphere","mean_sea_level")})
    p.update(subset(lat,lon))
    return BASE+"?"+urlencode(p)
def collect(locations,date,cycle,steps,output,max_requests=12):
    if not isinstance(locations,list) or not locations or len(locations)*len(steps)>max_requests or not 1<=max_requests<=48: raise ValueError("Request budget exceeded")
    issued=datetime.strptime(date+cycle,"%Y%m%d%H").replace(tzinfo=timezone.utc)
    out=Path(output);(out/"raw").mkdir(parents=True,exist_ok=True);records=[]
    for i,loc in enumerate(locations):
        lat,lon=point(float(loc["lat"]),float(loc["lon"]))
        for step in steps:
            valid=issued+timedelta(hours=step)
            if valid<=datetime.now(timezone.utc): raise ValueError("Forecast valid time is already past")
            url=url_for(date,cycle,step,lat,lon)
            target=out/"raw"/f"gfs_{date}{cycle}_{i:02d}_f{step:03d}.grib2"
            if target.exists(): raise FileExistsError("Immutable capture exists")
            for attempt in range(3):
                try:
                    with urlopen(Request(url,headers={"User-Agent":"ArcherAtmosResearch/0.3"}),timeout=65) as response:
                        data=response.read(4000001)
                    if len(data)>4000000 or not data.startswith(b"GRIB") or not data.endswith(b"7777"): raise ValueError("Invalid GRIB response")
                    target.write_bytes(data);break
                except Exception:
                    if attempt==2: raise
                    time.sleep(5*(attempt+1))
            records.append(dict(name=loc.get("name",f"Point {i+1}"),latitude=lat,longitude=lon,issued_at=issued.isoformat(),valid_at=valid.isoformat(),retrieved_at=datetime.now(timezone.utc).isoformat(),sha256=hashlib.sha256(data).hexdigest(),source_url=url,calibrated=False,independently_verified=False))
    (out/"manifest.json").write_text(json.dumps({"status":"Research only; not weather alerts","captures":records},indent=2))
    return len(records)
def main():
    p=argparse.ArgumentParser()
    for flag,default in (("--locations","examples/global_sample.json"),("--cycle","00"),("--steps","24,27"),("--output","capture")):p.add_argument(flag,default=default)
    p.add_argument("--date",required=True);p.add_argument("--max-requests",type=int,default=12)
    a=p.parse_args();steps=[int(s) for s in a.steps.split(",")]
    if len(steps)!=len(set(steps)) or not steps or any(s not in range(0,73,3) for s in steps):p.error("Invalid steps")
    print(json.dumps({"captured":collect(json.loads(Path(a.locations).read_text()),a.date,a.cycle,steps,a.output,a.max_requests)}))
if __name__=="__main__":main()
