# Independent Forecast Validation

Use independently sourced station observations, not model-derived reanalysis. Compare authentic forecasts with issue dates against observations by station and valid date. Report temperature and precipitation MAE by lead time: days 1-7, 8-14, 15-30. Do not apply model corrections before out-of-sample validation.

Required forecast CSV columns: station_id,date,issue_date,forecast_temp_max_c,forecast_precip_mm.
Required observation CSV columns: station_id,date,observed_temp_max_c,observed_precip_mm.

This is a validation specification, not a claim of measured skill.