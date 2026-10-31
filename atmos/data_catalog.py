"""Inventory of source families for Atmos research; catalog only, not bulk download.

Each source requires independent access, licensing and time-availability review.
"""
SOURCES=[
 {"id":"iem_asos","provider":"Iowa Environmental Mesonet","domain":"surface observations","url":"https://mesonet.agron.iastate.edu/","variables":["temperature","dew_point","wind","visibility","pressure","precipitation"],"priority":"P0","status":"pilot"},
 {"id":"noaa_isd","provider":"NOAA NCEI","domain":"global station observations","url":"https://www.ncei.noaa.gov/products/land-based-station/integrated-surface-database","variables":["temperature","dew_point","wind","pressure","visibility","precipitation"],"priority":"P0","status":"evaluate"},
 {"id":"ghcn_daily","provider":"NOAA NCEI","domain":"daily observations","url":"https://www.ncei.noaa.gov/products/land-based-station/global-historical-climatology-network-daily","variables":["temperature_max","temperature_min","precipitation","snow"],"priority":"P0","status":"evaluate"},
 {"id":"igra","provider":"NOAA NCEI","domain":"radiosondes upper air","url":"https://www.ncei.noaa.gov/products/weather-balloon/integrated-global-radiosonde-archive","variables":["pressure","temperature","humidity","wind_profile"],"priority":"P1","status":"evaluate"},
 {"id":"era5","provider":"ECMWF Copernicus","domain":"reanalysis predictors only","url":"https://cds.climate.copernicus.eu/","variables":["atmospheric_fields","soil","radiation"],"priority":"P1","status":"evaluate"},
 {"id":"gfs","provider":"NOAA NCEP","domain":"issued numerical forecasts","url":"https://www.ncei.noaa.gov/products/weather-climate-models/global-forecast","variables":["forecast_fields","ensemble_inputs"],"priority":"P0","status":"evaluate"},
 {"id":"gefs","provider":"NOAA NCEP","domain":"ensemble forecast","url":"https://www.ncei.noaa.gov/products/weather-climate-models/global-ensemble-forecast","variables":["probabilistic_fields"],"priority":"P0","status":"evaluate"},
 {"id":"ecmwf_open_data","provider":"ECMWF","domain":"numerical forecast","url":"https://www.ecmwf.int/en/forecasts/datasets/open-data","variables":["forecast_fields"],"priority":"P0","status":"evaluate"},
 {"id":"mrms","provider":"NOAA NSSL","domain":"radar precipitation","url":"https://www.nssl.noaa.gov/projects/mrms/","variables":["precipitation_rate","radar_quality"],"priority":"P1","status":"evaluate"},
 {"id":"goes","provider":"NOAA NESDIS","domain":"geostationary satellite","url":"https://www.goes.noaa.gov/","variables":["clouds","water_vapor","convection"],"priority":"P1","status":"evaluate"},
 {"id":"storm_events","provider":"NOAA NCEI","domain":"hazard verification","url":"https://www.ncei.noaa.gov/stormevents/","variables":["hail","tornado","flood","wind_damage"],"priority":"P0","status":"evaluate"},
 {"id":"spc","provider":"NOAA SPC","domain":"severe weather reports","url":"https://www.spc.noaa.gov/climo/reports/","variables":["tornado","hail","wind"],"priority":"P1","status":"evaluate"},
 {"id":"usgs_3dep","provider":"USGS","domain":"terrain predictors","url":"https://www.usgs.gov/3d-elevation-program","variables":["elevation","slope","aspect"],"priority":"P1","status":"evaluate"},
 {"id":"noaa_tides","provider":"NOAA CO-OPS","domain":"coastal conditions","url":"https://tidesandcurrents.noaa.gov/","variables":["water_level","coastal_wind","water_temperature"],"priority":"P2","status":"evaluate"},
]
REQUIRED_FIELDS=["source_id","station_or_grid_id","latitude","longitude","elevation_m",
 "variable","value","unit","valid_start_utc","valid_end_utc","issued_at_utc",
 "retrieved_at_utc","quality_flag","license_reference","raw_checksum"]
def validate_record(record):
    missing=[k for k in REQUIRED_FIELDS if k not in record]
    if missing:raise ValueError("Missing provenance fields: "+",".join(missing))
    if record["valid_start_utc"]>=record["valid_end_utc"]:
        raise ValueError("Invalid valid interval")
    if not record["source_id"] or not record["variable"] or not record["unit"]:
        raise ValueError("Missing source, variable or unit")
    return True
