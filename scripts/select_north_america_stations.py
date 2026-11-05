#!/usr/bin/env python3
"""Build an auditable North American GHCNh station candidate map.
Usage: python scripts/select_north_america_stations.py --station-list ghcnh-station-list.txt --inventory ghcnh-inventory.txt --out output
Inventory is required: never certify 10-year hourly coverage from station coordinates alone.
"""
import argparse,csv,json,math,pathlib,collections
def stations(path):
    with open(path,encoding="utf-8",errors="replace") as f:
        for line in f:
            sid=line[:11].strip()
            if sid[:2] not in {"US","CA","MX"}: continue
            try: lat=float(line[12:20]);lon=float(line[21:30]);elev=float(line[31:37])
            except ValueError: continue
            if not (math.isfinite(lat) and math.isfinite(lon) and math.isfinite(elev)): continue
            if elev == -999.9 or not (-500 <= elev <= 6500): continue
            if not (-170<=lon<=-52 and 14<=lat<=84): continue
            yield {"id":sid,"country":sid[:2],"latitude":lat,"longitude":lon,"elevation_m":elev,"name":line[41:71].strip()}
def inventory(path):
    coverage=collections.defaultdict(lambda:[0,0])
    with open(path,encoding="utf-8",errors="replace") as f:
        for line in f:
            parts=line.split()
            if len(parts)<14:continue
            sid=parts[0]
            try:year=int(parts[1]);counts=[int(x) for x in parts[2:14]]
            except ValueError:continue
            if 2016<=year<=2025:
                coverage[sid][0]+=sum(max(0,x) for x in counts)
                coverage[sid][1]+=sum(x>=500 for x in counts)
    return coverage
def select(items,quota):
    # Greedy grid spread with quality-first sorting within 1-degree cells.
    bins=collections.defaultdict(list)
    for s in items:
        bins[(int(math.floor(s["latitude"])),int(math.floor(s["longitude"])))].append(s)
    for b in bins.values():b.sort(key=lambda s:(-s["months_500plus"],-s["observations_2016_2025"],s["id"]))
    keys=sorted(bins)
    selected=[]
    while keys and len(selected)<quota:
        remaining=[]
        for key in keys:
            if len(selected)>=quota:break
            if bins[key]:selected.append(bins[key].pop(0))
            if bins[key]:remaining.append(key)
        keys=remaining
    return selected
def main():
    p=argparse.ArgumentParser();p.add_argument("--station-list",required=True);p.add_argument("--inventory",required=True);p.add_argument("--out",default="station-map");a=p.parse_args()
    out=pathlib.Path(a.out);out.mkdir(parents=True,exist_ok=True)
    cover=inventory(a.inventory);data=[]
    for s in stations(a.station_list):
        obs,months=cover[s["id"]]
        s.update(observations_2016_2025=obs,months_500plus=months)
        # 10-year candidate threshold: >= 60 months with >=500 observations.
        if months>=60:data.append(s)
    targets={"US":6000,"CA":2500,"MX":1500}
    selected=[]
    for country,target in targets.items():
        selected+=select([s for s in data if s["country"]==country],target)
    fields=["id","country","latitude","longitude","elevation_m","name","observations_2016_2025","months_500plus"]
    with (out/"stations.csv").open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(selected)
    geo={"type":"FeatureCollection","features":[{"type":"Feature","geometry":{"type":"Point","coordinates":[s["longitude"],s["latitude"]]},"properties":{k:v for k,v in s.items() if k not in ("latitude","longitude")}} for s in selected]}
    (out/"stations.geojson").write_text(json.dumps(geo,separators=(",",":")),encoding="utf-8")
    counts=collections.Counter(s["country"] for s in selected)
    report={"selected":len(selected),"country_counts":dict(counts),"targets":targets,"eligible":len(data),"criteria":"at least 60 months with >=500 observations per month during 2016-2025; not a guarantee of complete 10-year hourly records","shortfall":{k:v-counts[k] for k,v in targets.items()}}
    (out/"selection_report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(report,indent=2))
if __name__=="__main__":main()
