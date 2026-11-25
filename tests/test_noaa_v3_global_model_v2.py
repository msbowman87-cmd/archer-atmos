"""Safeguard tests for Atmos V2 event-specific forecasts and station exclusion."""
import csv
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import numpy as np
from atmos import noaa_v3_global_model_v2 as model
from atmos import noaa_v3_global_pooled_model as base


class V2ModelTests(unittest.TestCase):
    def setUp(self):
        self.x=np.zeros((3,base.NFEATURES),dtype=float)
        self.x[:,0]=1.0
        self.ordinary=np.zeros((8,3,base.NFEATURES),dtype=float)
        self.special=np.zeros((4,3,base.NFEATURES),dtype=float)

    def test_precipitation_zero_inflated_and_wet_probability(self):
        prior=np.array([0.,1.,2.])
        outcome,_,info=model.forecast_candidates(7,0,self.x,prior,self.ordinary,self.special)
        np.testing.assert_array_equal(outcome,np.zeros(3))
        np.testing.assert_array_equal(info["wet_probability"],np.zeros(3))
        self.special[0,0,0]=0.8
        self.special[1,0,0]=0.2
        outcome,_,info=model.forecast_candidates(7,0,self.x,prior,self.ordinary,self.special)
        self.assertTrue((outcome>0).all())
        self.assertTrue((info["wet_probability"]==0.8).all())

    def test_visibility_requires_low_visibility_evidence(self):
        prior=np.array([16000.,10000.,500.])
        self.ordinary[6,0,0]=-1.
        revised,old,info=model.forecast_candidates(6,0,self.x,prior,self.ordinary,self.special)
        np.testing.assert_array_equal(revised,prior)
        self.assertTrue((old<prior).all())
        self.special[2,0,0]=0.7
        self.special[3,0,0]=0.6
        revised,_,info=model.forecast_candidates(6,0,self.x,prior,self.ordinary,self.special)
        self.assertTrue((revised<=prior).all())
        self.assertGreater(revised[2],0)
        self.assertTrue((info["low_visibility_probability"]==0.7).all())

    def test_excluded_stations_contribute_no_model_stats(self):
        names=[*model.HOLDOUTS,"99999999999"]
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            metadata=root/"stations.csv"
            with metadata.open("w",newline="") as f:
                w=csv.writer(f)
                w.writerow(["station_id","lat","lon","name"])
                for name in names:
                    w.writerow([name,43.,-116.,name])
            dt=datetime(2006,1,1,tzinfo=timezone.utc)
            def fake_stations(altered):
                stations={}
                for name in names:
                    observations=[]
                    for i in range(180):
                        t=int(((dt+timedelta(hours=i))-base.EPOCH).total_seconds()//3600)
                        vals=np.array([15.,5.,65.,3.,90.,1011.,10000.,0.0],dtype=np.float32)
                        if name in model.HOLDOUTS and altered: vals[:]+=1000.
                        if name=="99999999999": vals[7]=0.2 if i%5==0 else 0.
                        observations.append((t,vals))
                    stations[name]=observations
                return stations
            with patch.object(base,"read_shard",return_value=fake_stations(False)):
                model.fit_shard("unused.tar",0,metadata,root/"original")
            with patch.object(base,"read_shard",return_value=fake_stations(True)):
                model.fit_shard("unused.tar",0,metadata,root/"altered")
            with np.load(root/"original"/"training-stats-shard-00.npz") as a:
                with np.load(root/"altered"/"training-stats-shard-00.npz") as b:
                    self.assertEqual(a["stations"].tolist(),["99999999999"])
                    self.assertEqual(set(a["excluded"].tolist()),set(model.HOLDOUTS))
                    for key in ("gram","rhs","counts","special_gram","special_rhs","special_counts"):
                        np.testing.assert_array_equal(a[key],b[key])

    def test_ridge_estimates_finite(self):
        n=base.NFEATURES
        g=np.stack([np.eye(n)*5000 for _ in range(3)])
        rhs=np.ones((3,n))
        c=np.array([5000,5000,5000])
        weights=model.ridge(g,rhs,c)
        self.assertEqual(weights.shape,(3,n))
        self.assertTrue(np.isfinite(weights).all())


if __name__=="__main__":
    unittest.main()
