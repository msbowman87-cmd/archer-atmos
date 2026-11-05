"""Bounded real NOAA GOES-16 / Unidata NEXRAD archive extraction pilot.

Produces verified source hashes and station-aligned feature rows, but historical
distribution timestamps are *not* archived in the input products. The
available_at_utc fields are conservative research assumptions, identified as
such on every record and in the manifest. NOT suitable for certified backtests.
Only actual file values are emitted; unavailable sensors remain MISSING.
"""
import argparse
import csv
import hashlib
import json
import math
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

STATIONS = {
    "72681024131": ("Boise Air Terminal", "KCBX"),
    "72202012839": ("Miami International", "KAMX"),
}
GOES_BUCKET="noaa-goes16"
RADAR_BUCKET="unidata-nexrad-level2"
GOES_PRODUCTS=("ABI-L2-ACMC","ABI-L2-MCMIPC")
GOES_DELAY_MINUTES=15
RADAR_DELAY_MINUTES=15
CSV_FIELDS=("station_id","source","product_id","observed_at_utc",
            "available_at_utc","availability_provenance",
            "cloud_fraction","water_vapor_brightness_temperature_k",
            "max_reflectivity_dbz","radial_velocity_mps")


def filename_time(filename, part):
    # GOES filename _sYYYYJJJHHMMSSf, _e..., _c... (fraction ignored)
    m=re.search(r"_"+re.escape(part)+r"(\d{13,14})",filename)
    if not m:
        raise ValueError(f"GOES file missing {part} timestamp: {filename}")
    return datetime.strptime(m.group(1)[:13],"%Y%j%H%M%S").replace(tzinfo=timezone.utc)


def iso(t):
    return t.astimezone(timezone.utc).isoformat().replace("+00:00","Z")


def sha256(path):
    digest=hashlib.sha256()
    with open(path,"rb") as f:
        for block in iter(lambda:f.read(1024*1024),b""):
            digest.update(block)
    return digest.hexdigest()


def archive_client():
    import boto3
    from botocore import UNSIGNED
    from botocore.config import Config
    return boto3.client("s3",config=Config(signature_version=UNSIGNED,
                                           retries={"max_attempts":4,"mode":"standard"}))


def find_scene(client,bucket,prefix,when,radar=False):
    keys=[]
    paginator=client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket,Prefix=prefix):
        for obj in page.get("Contents",[]):
            key=obj["Key"]
            if key.endswith(("/","_MDM")):
                continue
            name=key.rsplit("/",1)[-1]
            try:
                time=(datetime.strptime(name[4:19],"%Y%m%d_%H%M%S").replace(
                      tzinfo=timezone.utc) if radar else filename_time(name,"s"))
            except ValueError:
                continue
            delta=abs((when-time).total_seconds())
            if delta<=1800:
                keys.append((delta,time,key,int(obj.get("Size",0))))
    if not keys:
        return None
    return min(keys,key=lambda v:(v[0],v[1]))


def download(client,bucket,key,cache,manifest):
    target=Path(cache)/key.rsplit("/",1)[-1]
    client.download_file(bucket,key,str(target))
    obj={"source_uri":f"s3://{bucket}/{key}",
         "sha256":sha256(target),"bytes":target.stat().st_size}
    manifest["downloaded_files"].append(obj)
    return target,obj["source_uri"]


def position(ds,lat,lon):
    from pyproj import CRS,Transformer
    proj=ds["goes_imager_projection"].attrs
    crs=CRS.from_proj4(
        f"+proj=geos +lon_0={proj['longitude_of_projection_origin']} "
        f"+h={proj['perspective_point_height']} "
        f"+a={proj['semi_major_axis']} +b={proj['semi_minor_axis']} "
        f"+sweep={proj.get('sweep_angle_axis','x')} +units=m +no_defs")
    mx,my=Transformer.from_crs("EPSG:4326",crs,always_xy=True).transform(lon,lat)
    if not math.isfinite(mx) or not math.isfinite(my):
        return None
    h=float(proj["perspective_point_height"])
    x=mx/h;y=my/h
    xs=ds["x"].values;ys=ds["y"].values
    if x<min(xs) or x>max(xs) or y<min(ys) or y>max(ys):
        return None
    import numpy as np
    return int(np.argmin(abs(ys-y))),int(np.argmin(abs(xs-x)))


def patch_mean(ds,var,row,col,allowed_quality=None,cloud=False):
    import numpy as np
    a=ds[var]
    if not {"x","y"}.issubset(a.dims):
        raise ValueError(f"Unknown GOES {var} projection/dimensions")
    sy=slice(max(0,row-2),min(a.sizes["y"],row+3))
    sx=slice(max(0,col-2),min(a.sizes["x"],col+3))
    values=np.asarray(a.isel(y=sy,x=sx).values,dtype=float)
    if allowed_quality and allowed_quality in ds:
        quality=np.asarray(ds[allowed_quality].isel(y=sy,x=sx).values)
        values=np.where(quality==0,values,np.nan)
    if cloud:
        values=np.where(np.isin(values,[0.,1.]),values,np.nan)
    else:
        values=np.where(np.isfinite(values),values,np.nan)
    valid=values[np.isfinite(values)]
    return float(np.mean(valid)) if len(valid)>=3 else None


def goes_features(files,station):
    import xarray as xr
    lat,lon=station
    results={}
    for product,(path,uri) in files.items():
        with xr.open_dataset(path,engine="netcdf4",mask_and_scale=True,
                             decode_times=False) as ds:
            pos=position(ds,lat,lon)
            if pos is None:
                continue
            row,col=pos
            if product=="ABI-L2-ACMC" and "BCM" in ds:
                val=patch_mean(ds,"BCM",row,col,"DQF",cloud=True)
                if val is not None:
                    results["cloud_fraction"]=val
            if product=="ABI-L2-MCMIPC" and "CMI_C08" in ds:
                val=patch_mean(ds,"CMI_C08",row,col,"DQF_C08")
                if val is not None and 100.<val<400.:
                    results["water_vapor_brightness_temperature_k"]=val
    return results


def radar_features(path,lat,lon):
    import numpy as np
    import pyart
    import netCDF4
    radar=pyart.io.read_nexrad_archive(str(path))
    if not radar.nsweeps:
        return {},None
    # Source end-of-scan time, not filename start, prevents scan-time lookahead.
    times=np.asarray(radar.time["data"],dtype=float)
    if not len(times):
        return {},None
    end=netCDF4.num2date(float(np.nanmax(times)),radar.time["units"],
                        only_use_cftime_datetimes=False,
                        only_use_python_datetimes=True)
    end=end.replace(tzinfo=timezone.utc) if end.tzinfo is None else end.astimezone(timezone.utc)
    glat,glon,galt=radar.get_gate_lat_lon_alt(0)
    dist_km=np.hypot(111.2*(glat-lat),
                     111.2*math.cos(math.radians(lat))*(glon-lon))
    neighborhood=(dist_km<=15.)
    results={}
    start_ray=int(radar.sweep_start_ray_index["data"][0])
    end_ray=int(radar.sweep_end_ray_index["data"][0])+1
    for name,field in (("reflectivity","max_reflectivity_dbz"),
                       ("velocity","radial_velocity_mps")):
        if name not in radar.fields:
            continue
        data=np.ma.asarray(radar.fields[name]["data"][start_ray:end_ray,:])
        if data.shape!=neighborhood.shape:
            continue
        selected=np.ma.masked_invalid(data)
        values=selected[neighborhood].compressed()
        if len(values)>=1:
            if name=="reflectivity":
                results[field]=float(np.max(values))
            else:
                results[field]=float(np.median(values))
    return results,end


def extract(metadata,out,day="2018-06-01",hour=18,stations=None):
    stations = STATIONS if stations is None else stations
    date=datetime.strptime(day,"%Y-%m-%d").replace(tzinfo=timezone.utc)
    date=date.replace(hour=hour)
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    cache=out/"raw-cache";cache.mkdir(exist_ok=True)
    locations={}
    with open(metadata,newline="",encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            if row["station_id"] in stations:
                locations[row["station_id"]]=(float(row["lat"]),float(row["lon"]))
    if set(locations)!=set(stations):
        raise ValueError(f"Stations missing metadata: {set(stations)-set(locations)}")
    client=archive_client()
    doy=date.timetuple().tm_yday
    manifest={
        "status":"pilot_archive_extraction",
        "date_utc":iso(date),
        "satellite_bucket":GOES_BUCKET,"radar_bucket":RADAR_BUCKET,
        "availability_verified":False,
        "assumed_delays_minutes":{"satellite_after_creation":GOES_DELAY_MINUTES,
                                   "radar_after_scan_end":RADAR_DELAY_MINUTES},
        "downloaded_files":[],"selection":{},"station_extraction":{}
    }
    sat={}
    for product in GOES_PRODUCTS:
        prefix=f"{product}/{date:%Y}/{doy:03d}/{hour:02d}/"
        pick=find_scene(client,GOES_BUCKET,prefix,date)
        if pick is None:
            manifest["selection"][product]={"found":False,"prefix":prefix}
            continue
        path,uri=download(client,GOES_BUCKET,pick[2],cache,manifest)
        sat[product]=(path,uri)
        manifest["selection"][product]={"found":True,"uri":uri,
            "scan_start_utc":iso(filename_time(path.name,"s")),
            "scan_end_utc":iso(filename_time(path.name,"e")),
            "created_utc":iso(filename_time(path.name,"c"))}
    output_rows=[]
    if sat:
        obs=max(filename_time(p.name,"e") for p,_ in sat.values())
        created=max(filename_time(p.name,"c") for p,_ in sat.values())
        satellite_available=created+timedelta(minutes=GOES_DELAY_MINUTES)
        for station_id in stations:
            features=goes_features(sat,locations[station_id])
            if features:
                output_rows.append({
                    "station_id":station_id,"source":"satellite",
                    "product_id":";".join(uri for _,uri in sat.values()),
                    "observed_at_utc":iso(obs),
                    "available_at_utc":iso(satellite_available),
                    "availability_provenance":"ASSUMED_GOES_CREATION_PLUS_15_MINUTES",
                    **features,
                })
            manifest["station_extraction"].setdefault(station_id,{})["satellite"]=features
    for station_id,(name,radar_site) in stations.items():
        prefix=f"{date:%Y/%m/%d}/{radar_site}/"
        pick=find_scene(client,RADAR_BUCKET,prefix,date,radar=True)
        if pick is None:
            manifest["selection"][radar_site]={"found":False,"prefix":prefix}
            continue
        path,uri=download(client,RADAR_BUCKET,pick[2],cache,manifest)
        lat,lon=locations[station_id]
        features,end=radar_features(path,lat,lon)
        manifest["selection"][radar_site]={"found":True,"uri":uri,
              "scan_end_utc":iso(end) if end else None}
        manifest["station_extraction"].setdefault(station_id,{})["radar"]=features
        if features and end:
            output_rows.append({
                "station_id":station_id,"source":"radar","product_id":uri,
                "observed_at_utc":iso(end),
                "available_at_utc":iso(end+timedelta(minutes=RADAR_DELAY_MINUTES)),
                "availability_provenance":"ASSUMED_NEXRAD_SCAN_END_PLUS_15_MINUTES",
                **features,
            })
    with open(out/"station-sensing-pilot.csv","w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=CSV_FIELDS,extrasaction="raise")
        w.writeheader();w.writerows(output_rows)
    count={kind:sum(r["source"]==kind for r in output_rows)
           for kind in ("satellite","radar")}
    from atmos.remote_sensing_features import RemoteSensingStore
    store=RemoteSensingStore.from_csv(out/"station-sensing-pilot.csv")
    issued=date+timedelta(minutes=50)
    usable={}
    for station_id in stations:
        for kind in ("satellite","radar"):
            usable[f"{station_id}|{kind}"]=bool(store.latest(
                station_id,kind,issued,max_age_hours=3.0))
    summary={
        "records":len(output_rows),"by_source":count,
        "stations_attempted":len(stations),
        "forecast_issue_scenario_utc":iso(issued),
        "source_availability_assumed_not_verified":True,
        "usable_at_scenario_issue":usable,
        "matched_training_hours":0,
        "historical_accuracy_calculated":False,
        "reason":"One-scan extraction validates actual source alignment only; no paired multi-hour training/evaluation yet",
    }
    (out/"source-manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
    (out/"coverage.json").write_text(json.dumps(summary,indent=2)+"\n")
    print(json.dumps(summary,indent=2))
    return summary


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--metadata",required=True)
    p.add_argument("--output",required=True)
    p.add_argument("--date",default="2018-06-01")
    p.add_argument("--hour",default=18,type=int)
    a=p.parse_args()
    result=extract(a.metadata,a.output,a.date,a.hour)
    if result["by_source"]["satellite"]<1 or result["by_source"]["radar"]<1:
        raise RuntimeError("Pilot incomplete: required at least one real satellite and radar measurement")


if __name__=="__main__":
    main()
