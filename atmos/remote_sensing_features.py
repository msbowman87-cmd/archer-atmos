"""Leakage-safe satellite/radar feature adapter for Atmos.

Input is extracted, station-aligned observations, NOT raw imagery.
A remote sensor feature is usable only if its actual source availability
timestamp is no later than the forecast issue timestamp.
No imagery has yet been ingested into the model with this adapter.

Sources:
NCEI GOES ABI https://www.ncei.noaa.gov/products/goes-terrestrial-weather-abi-glm
NCEI NEXRAD https://www.ncei.noaa.gov/has/HAS.DsSelect
Missing radar is UNKNOWN, not zero precipitation or clear weather.
"""
import bisect
import csv
import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone

SOURCE_FEATURES = {
    "satellite": (
        "cloud_fraction", "cloud_top_temperature_k", "cloud_top_height_m",
        "water_vapor_brightness_temperature_k", "cloud_motion_u_mps",
        "cloud_motion_v_mps",
    ),
    "radar": (
        "max_reflectivity_dbz", "rain_rate_mm_h", "radial_velocity_mps",
        "echo_motion_u_mps", "echo_motion_v_mps",
    ),
}
MAX_AGE_HOURS = {"satellite": 3.0, "radar": 1.0}
SCALE_CENTER = {
    "cloud_fraction": (0., 1.),
    "cloud_top_temperature_k": (260., 60.),
    "cloud_top_height_m": (0., 15000.),
    "water_vapor_brightness_temperature_k": (260., 60.),
    "cloud_motion_u_mps": (0., 30.),
    "cloud_motion_v_mps": (0., 30.),
    "max_reflectivity_dbz": (0., 60.),
    "rain_rate_mm_h": (0., 50.),
    "radial_velocity_mps": (0., 40.),
    "echo_motion_u_mps": (0., 30.),
    "echo_motion_v_mps": (0., 30.),
}

def utc_timestamp(value):
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(
        str(value).replace("Z", "+00:00")
    )
    if parsed.tzinfo is None:
        raise ValueError("Remote sensing timestamps must be timezone-aware")
    return parsed.astimezone(timezone.utc)

@dataclass(frozen=True)
class RemoteSensingRecord:
    station_id: str
    source: str
    product_id: str
    observed_at_utc: datetime
    available_at_utc: datetime
    values: dict

    def __post_init__(self):
        if self.source not in SOURCE_FEATURES:
            raise ValueError("Expected satellite or radar source")
        if not self.station_id or not self.product_id:
            raise ValueError("Station ID and source product ID required")
        observed=utc_timestamp(self.observed_at_utc)
        available=utc_timestamp(self.available_at_utc)
        if available < observed:
            raise ValueError("Availability cannot precede observation")
        object.__setattr__(self,"observed_at_utc",observed)
        object.__setattr__(self,"available_at_utc",available)
        for key,value in self.values.items():
            if key not in SOURCE_FEATURES[self.source]:
                raise ValueError(f"Unexpected {self.source} feature {key}")
            if not isinstance(value,(int,float)) or not math.isfinite(value):
                raise ValueError(f"Non-finite {key}")
            if key=="cloud_fraction" and not 0.<=value<=1.:
                raise ValueError("Cloud fraction out of range")
            if key=="rain_rate_mm_h" and value<0.:
                raise ValueError("Radar rainfall rate cannot be negative")

class RemoteSensingStore:
    """As-of lookup for data with verifiable availability timestamps."""

    def __init__(self,records):
        grouped=defaultdict(list)
        for record in records:
            grouped[(record.station_id,record.source)].append(record)
        self._indexes={}
        for key,rows in grouped.items():
            rows.sort(key=lambda r:(r.available_at_utc,r.observed_at_utc))
            best=[]
            current=None
            for record in rows:
                # Choose latest observation among everything already received.
                if current is None or record.observed_at_utc>=current.observed_at_utc:
                    current=record
                best.append(current)
            self._indexes[key]=([r.available_at_utc for r in rows],best)

    @classmethod
    def from_csv(cls,path):
        records=[]
        with open(path,newline="",encoding="utf-8-sig") as handle:
            reader=csv.DictReader(handle)
            required={"station_id","source","product_id",
                      "observed_at_utc","available_at_utc"}
            if not required.issubset(reader.fieldnames or ()):
                raise ValueError("Remote-sensing CSV missing source provenance")
            for row in reader:
                source=row["source"].strip().lower()
                if source not in SOURCE_FEATURES:
                    raise ValueError("Unrecognized sensor")
                values={key:float(row[key]) for key in SOURCE_FEATURES[source]
                        if row.get(key) not in ("",None)}
                records.append(RemoteSensingRecord(
                    station_id=row["station_id"].strip(),source=source,
                    product_id=row["product_id"].strip(),
                    observed_at_utc=utc_timestamp(row["observed_at_utc"]),
                    available_at_utc=utc_timestamp(row["available_at_utc"]),
                    values=values))
        return cls(records)

    def latest(self,station_id,source,issued_at,max_age_hours=None):
        issue=utc_timestamp(issued_at)
        if source not in SOURCE_FEATURES:
            raise ValueError("Unrecognized source")
        items=self._indexes.get((station_id,source))
        if items is None:
            return None
        available,best=items
        idx=bisect.bisect_right(available,issue)-1
        if idx<0:
            return None
        record=best[idx]
        age_h=(issue-record.observed_at_utc).total_seconds()/3600.
        limit=MAX_AGE_HOURS[source] if max_age_hours is None else max_age_hours
        if age_h<0 or age_h>limit:
            return None
        return record

    def model_features(self,station_id,issued_at):
        """Normalized features and missingness indicators for each variable model.

        Shared INPUTS are permissible, but each weather variable retains
        separate fitted coefficients, losses and calibration parameters.
        """
        names,values=[],[]
        for source,columns in SOURCE_FEATURES.items():
            record=self.latest(station_id,source,issued_at)
            names.append(f"{source}_available")
            values.append(float(record is not None))
            for key in columns:
                names.extend((key,f"{key}_present"))
                v=record.values.get(key) if record is not None else None
                if v is None:
                    values.extend((0.,0.))
                else:
                    center,scale=SCALE_CENTER[key]
                    values.extend((max(-5.,min(5.,(v-center)/scale)),1.))
        return tuple(names),tuple(values)
