"""Causal, exclusion, and checkpoint math tests for global model."""
import csv
import gzip
import io
import tarfile
import tempfile
import unittest
from pathlib import Path
import numpy as np
from atmos.noaa_v3_global_pooled_model import (
    METRICS,HOLDOUT,NFEATURES,model_rows,samples,fit_shard,solve_global,
)

class GlobalModelTests(unittest.TestCase):
    def test_uses_no_future_or_unavailable_observations(self):
        n=250;start=500000
        data=np.full((n,8),np.nan,dtype=np.float32)
        data[:,0]=np.arange(n,dtype=np.float32)
        # Observation at target t=200 cannot enter 24h forecast issued t=176;
        # with 72h availability delay, latest usable time is t=104.
        _,ids,known,_,_=model_rows(start,data,43.5,-116.2,24,72)
        self.assertEqual(int(ids[200,0]),104)
        self.assertEqual(float(known[200,0]),104.)
        changed=data.copy();changed[200,0]=999999.
        x1=samples(start,data,43.5,-116.2,24)[0][0]
        x2=samples(start,changed,43.5,-116.2,24)[0][0]
        np.testing.assert_array_equal(x1,x2)
    def test_station_holdout_never_enters_fit_statistics(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);archive=root/"test.tar";metadata=root/"stations.csv"
            metadata.write_text("station_id,lat,lon\n"+HOLDOUT+",43.567,-116.241\n"
                                +"72698024229,45.596,-122.609\n")
            data=io.BytesIO()
            with gzip.GzipFile(fileobj=data,mode="wb") as gz:
                with io.TextIOWrapper(gz,encoding="utf-8",newline="") as f:
                    writer=csv.writer(f)
                    header=["station_id","hour_utc"]
                    for m in METRICS:
                        header.append(m)
                        qc={"temperature_c":"temperature_qc","dewpoint_c":"dewpoint_qc",
                            "wind_speed_mps":"wind_speed_qc","wind_direction_deg":"wind_direction_qc",
                            "sea_level_pressure_hpa":"sea_level_pressure_qc","visibility_m":"visibility_qc",
                            "precip_1h_mm":"precip_1h_qc"}.get(m)
                        if qc:header.append(qc)
                    writer.writerow(header)
                    for station in [HOLDOUT,"72698024229"]:
                        for h in range(240):
                            from datetime import datetime,timedelta,timezone
                            t=datetime(2006,1,1,tzinfo=timezone.utc)+timedelta(hours=h)
                            fields=[station,t.isoformat()]
                            for m in METRICS:
                                v=60.+h if station==HOLDOUT else 10.+h/10.
                                fields.append(str(v))
                                if m!="relative_humidity_pct":fields.append("1")
                            writer.writerow(fields)
            payload=data.getvalue()
            with tarfile.open(archive,"w") as tar:
                item=tarfile.TarInfo("normalized-shard-00.csv.gz")
                item.size=len(payload)
                tar.addfile(item,io.BytesIO(payload))
            output=root/"output"
            fit_shard(archive,0,metadata,output)
            self.assertTrue((output/"holdout-station.npz").exists())
            with np.load(output/"training-stats-shard-00.npz") as s:
                self.assertEqual(s["stations"].tolist(),["72698024229"])
                self.assertEqual(s["excluded"].tolist(),[HOLDOUT])
                self.assertGreater(int(s["counts"][0,0]),0)
    def test_ridge_checkpoint_coefficients_are_finite(self):
        gram=np.tile(np.eye(NFEATURES)[None,None,:,:],(8,3,1,1))*2000.
        rhs=np.ones((8,3,NFEATURES),dtype=float)
        cnt=np.full((8,3),2000,dtype=np.int64)
        w=solve_global(gram,rhs,cnt)
        self.assertEqual(w.shape,(8,3,NFEATURES))
        self.assertTrue(np.isfinite(w).all())

if __name__=="__main__":unittest.main()
