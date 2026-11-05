#!/usr/bin/env python3
"""Select up to 10,000 unique station sites from normalized multi-provider CSV inventories.

Input CSV columns: provider,station_id,country,latitude,longitude,elevation_m,
months_500plus,observations_2016_2025,name
Country uses US/CA/MX or Caribbean territory ISO-2 codes. No inferred elevation.
"""
import argparse,csv,json,math,pathlib,collections
CARIBBEAN=set("AG AI AW BB BL BM BQ BS CU CW DM DO GD GP HT JM KN KY LC MF MQ MS PR SX TC TT VC VG VI".split())
TARGETS={"US":6000,"CA":2500,"MX":1500}
FIELDS=["provider","station_id","country","latitude","longitude","elevation_m","months_500plus","observations_2016_2025","name","selection_role"]
def parse(row):
    try:
        s={k:row.get(k,"").strip() for k in ("provider","station_id","country","name")}
        s["country"]=s["country"].upper()
        for k in ("latitude","longitude","elevation_m"):s[k]=float(row[k])
        for k in ("months_500plus","observations_2016_2025"):s[k]=int(row[k])
        if not s["provider"] or not s["station_id"] or s["country"] not in (set(TARGETS)|CARIBBEAN):return None
        if not all(math.isfinite(s[k]) for k in ("latitude","longitude","elevation_m")):return None
        if s["elevation_m"]==-999.9 or not (-500<=s["elevation_m"]<=6500):return None
        if not (-90<=s["latitude"]<=90 and -180<=s["longitude"]<=180):return None
        if s["months_500plus"]<60 or s["observations_2016_2025"]<=0:return None
        return s
    except (KeyError,ValueError,TypeError):return None
def rank(s):
    return (-s["months_500plus"],-s["observations_2016_2025"],s["provider"],s["station_id"])
def dedup(items):
    # Proximity heuristic for duplicate physical sites (~0.5 km latitude; longitude adjusted).
    # Review colocated but genuinely distinct stations manually before final certification.
    seen=set();result=[]
    for s in sorted(items,key=rank):
        lat=s["latitude"];lon=s["longitude"];scale=max(.15,math.cos(math.radians(lat)))
        key=(round(lat/.0045),round(lon*scale/.0045))
        if key in seen:continue
        seen.add(key);result.append(s)
    return result
def spread(items,n):
    bins=collections.defaultdict(list)
    for s in items:bins[(math.floor(s["latitude"]),math.floor(s["longitude"]))].append(s)
    for b in bins.values():b.sort(key=rank)
    keys=sorted(bins);out=[]
    while keys and len(out)<n:
        remaining=[]
        for key in keys:
            if len(out)>=n:break
            if bins[key]:out.append(bins[key].pop(0))
            if bins[key]:remaining.append(key)
        keys=remaining
    return out
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",required=True,nargs="+",help="One or more normalized provider CSVs")
    p.add_argument("--out",default="station-map")
    a=p.parse_args();out=pathlib.Path(a.out);out.mkdir(parents=True,exist_ok=True)
    rows=[];rejected=0
    for path in a.input:
        with open(path,newline="",encoding="utf-8") as f:
            for r in csv.DictReader(f):
                s=parse(r)
                if s:rows.append(s)
                else:rejected+=1
    unique=dedup(rows);chosen=[];counts={}
    for country,n in TARGETS.items():
        subset=spread([s for s in unique if s["country"]==country],n)
        for s in subset:s["selection_role"]="primary"
        chosen.extend(subset);counts[country]=len(subset)
    shortage=sum(TARGETS[c]-counts[c] for c in ("CA","MX"))
    # Caribbean only fills CA/MX shortfalls, never US shortfall.
    carib=spread([s for s in unique if s["country"] in CARIBBEAN and s not in chosen],shortage)
    for s in carib:s["selection_role"]="caribbean_fallback"
    chosen+=carib
    with (out/"stations.csv").open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();w.writerows(chosen)
    features=[{"type":"Feature","geometry":{"type":"Point","coordinates":[s["longitude"],s["latitude"]]},"properties":{k:v for k,v in s.items() if k not in ("latitude","longitude")}} for s in chosen]
    (out/"stations.geojson").write_text(json.dumps({"type":"FeatureCollection","features":features}),encoding="utf-8")
    report={"selected":len(chosen),"primary_counts":counts,"caribbean_fallback":len(carib),"remaining_shortfall":10000-len(chosen),"rejected_rows":rejected,"unique_eligible_candidates":len(unique),"warning":"Coordinate-based deduplication is heuristic; confirm colocated sites and source provenance before final certification."}
    (out/"selection_report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(report,indent=2))
if __name__=="__main__":main()
