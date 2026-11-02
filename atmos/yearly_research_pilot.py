"""One-year bounded research scale-up. Independent NOAA Global Hourly station readings.

Uses the same fixed 48-hour GFS lead and 72-hour *assumed* observation
availability as the exploratory pilot. Not publication-time verified.
"""
import csv,io,json,sys,time
from pathlib import Path
from urllib.parse import urlencode
from atmos import real_data_pilot as pilot

YEAR=2024
START="2024-01-01"
END="2024-12-31"
MAX_STATIONS=100
SOURCE="https://www.ncei.noaa.gov/pub/data/noaa/isd-history.csv"

def registry():
    data=pilot.download(SOURCE,3_000_000)
    rows=list(csv.DictReader(io.StringIO(data.decode('utf-8-sig'))))
    candidates=[]
    for x in rows:
        try:
            usaf=x["USAF"];wban=x["WBAN"]
            lat=float(x["LAT"]);lon=float(x["LON"])
            if not (-90<=lat<=90 and -180<=lon<=180):continue
            if not x.get("BEGIN","").isdigit() or not x.get("END","").isdigit():continue
            if x["BEGIN"]>"20240101" or x["END"]<"20241231":continue
            if usaf=="999999" or wban=="99999":continue
            code=usaf+wban
            if len(code)!=11:continue
            candidates.append((code,lat,lon))
        except (ValueError,KeyError):continue
    # A deterministic coarse lat-lon spatial sampling; not climate-stratified.
    cells={}
    for code,lat,lon in candidates:
        bucket=(int((lat+90)//10),int((lon+180)//15))
        cells.setdefault(bucket,[]).append((code,lat,lon))
    selected=[]
    for cell in sorted(cells):
        values=sorted(cells[cell])
        selected.append(values[0])
    return sorted(selected,key=lambda x:(x[1],x[2]))[:MAX_STATIONS]

def main():
    selected=registry()
    if len(selected)<MAX_STATIONS:raise RuntimeError("Insufficient eligible stations")
    pilot.YEAR=YEAR;pilot.START=START;pilot.END=END
    pilot.STATIONS=[(code,code,lat,lon) for code,lat,lon in selected]
    pilot.main()
    path=Path("pilot-results/manifest.json")
    result=json.loads(path.read_text())
    result["sampling"]="One station per occupied 10-degree latitude / 15-degree longitude bin, sorted by latitude"
    result["requested_stations"]=MAX_STATIONS
    result["one_year_requested"]=True
    result["limits"]=["Research-only: station publication time approximated as 72h",
      "Archived GFS previous_day2 uses approximate issue time, not confirmed cycle",
      "Station instant readings vs model near-surface temperature, not daily averages",
      "Coverage depends on successfully retrieved stations; no global skill claim"]
    path.write_text(json.dumps(result,indent=2)+"\n")
    if len(result["source_records"])<MAX_STATIONS:
        raise RuntimeError(f"Only {len(result['source_records'])} of {MAX_STATIONS} stations returned both sources; inspect artifact")
if __name__=="__main__":main()
