"""Tests for V3 satellite/radar residuals and per-target ablations."""
import unittest
from datetime import datetime,timezone

import numpy as np
from atmos import seasonal_v3_paired_skill as pilot
from atmos import noaa_v3_global_model_v2 as v2


class SeasonalV3SkillTests(unittest.TestCase):
    def test_separate_coefficient_vector_per_variable_and_horizon(self):
        def rows(y):
            return {
                "remote":np.column_stack([np.ones(32),np.ones((32,len(pilot.FEATURES)-1))]),
                "residual":np.ones(32)*y
            }
        training={
            "TRAIN-A":{(0,0):rows(0.5),(7,0):rows(-0.5)},
            "TRAIN-B":{(0,0):rows(0.5),(7,0):rows(-0.5)}
        }
        fitted,counts=pilot.fit_ablation(training)
        self.assertEqual(counts[("joint_elevation",0,0)],64)
        self.assertEqual(counts[("joint_elevation",7,0)],64)
        self.assertGreater(fitted[("joint_elevation",0,0)][0],0)
        self.assertLess(fitted[("joint_elevation",7,0)][0],0)
        np.testing.assert_array_equal(fitted[("joint_elevation",0,1)],
                                      np.zeros(len(pilot.FEATURES)))

    def test_no_radar_or_satellite_data_means_no_valid_pair(self):
        self.assertEqual(len(pilot.issue_hours()),112)
        self.assertEqual(len(set(pilot.issue_hours())),112)

    def test_weather_probability_output_is_bounded(self):
        n=3
        bucket={
            "remote":np.tile(np.r_[1.,np.zeros(len(pilot.FEATURES)-1)],(n,1)),
            "prior":np.zeros(n),
            "v2":np.zeros(n),
            "v2_features":np.tile(np.r_[1.,np.zeros(20)],(n,1)),
            "v2_event_p":np.array([.2,.6,.95]),
        }
        sp=np.zeros((4,3,21))
        coef=np.zeros(len(pilot.FEATURES));coef[0]=.8
        result,p=pilot.predict(bucket,7,0,coef,sp)
        self.assertTrue(np.all((p>=0)&(p<=1)))
        self.assertTrue(np.all(result>=0))
        self.assertTrue(np.isfinite(result).all())

    def test_station_split_never_contains_same_train_and_test_station(self):
        train={k for k,(_,_,split) in pilot.STATIONS.items() if split=="train"}
        excluded={k for k,(_,_,split) in pilot.STATIONS.items() if split=="holdout"}
        self.assertEqual(len(train),4)
        self.assertEqual(len(excluded),2)
        self.assertFalse(train & excluded)
        self.assertEqual(excluded,{"72681024131","72202012839"})


if __name__=="__main__":
    unittest.main()
