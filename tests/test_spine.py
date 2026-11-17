#!/usr/bin/env python3
"""Tests for the Chinese Correlation Spine. Plain stdlib unittest.

Run from the repo root:  python3 -m unittest discover -s tests -v
or:                     python3 tests/test_spine.py
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                ".."))
import spine  # noqa: E402


class TestEraConversion(unittest.TestCase):
    def test_jianan_later_han(self):
        m = spine.convert_era("Jian'an", 1)
        self.assertEqual(len(m), 1)
        self.assertEqual(m[0]["dynasty"], "Eastern Han")
        self.assertEqual(m[0]["ce"], 196)
        m25 = spine.convert_era("Jian'an", 25)
        self.assertEqual(m25[0]["ce"], 220)  # last Jian'an year

    def test_kumarajiva_hongshi_409(self):
        # Kumarajiva's Zhong Lun (MMK) was translated in Hongshi 11 = 409.
        m = spine.convert_era("Hongshi", 11)
        self.assertEqual(len(m), 1)
        self.assertEqual(m[0]["ce"], 409)

    def test_xuanzang_return_zhenguan_19(self):
        m = spine.convert_era("Zhenguan", 19)
        self.assertEqual(m[0]["ce"], 645)

    def test_kaiyuan_catalogue_730(self):
        m = spine.convert_era("Kaiyuan", 18)
        self.assertEqual(m[0]["ce"], 730)

    def test_lankavatara_yuanjia_20(self):
        m = spine.convert_era("Yuanjia", 20)
        self.assertEqual(m[0]["ce"], 443)

    def test_yongping_is_ambiguous(self):
        # Yongping is borne by Eastern Han, Western Jin AND Northern Wei.
        m = spine.convert_era("Yongping", 1)
        self.assertGreaterEqual(len(m), 3)
        ces = sorted(x["ce"] for x in m)
        self.assertEqual(ces, [58, 291, 508])

    def test_out_of_range_flagged(self):
        m = spine.convert_era("Zhenguan", 30)  # era lasted 23 years
        self.assertEqual(m[0]["ce"], 656)
        self.assertFalse(m[0]["in_range"])

    def test_unknown_era(self):
        self.assertEqual(spine.convert_era("NoSuchEra", 3), [])


class TestLookup(unittest.TestCase):
    def test_bhartrihari_returns_yijing_anchor(self):
        hits = spine.find_anchors("Bhartrihari")
        self.assertTrue(hits, "lookup Bhartrihari returned nothing")
        yijing = [r for r in hits if r["id"] == "bhartrihari-yijing-651"]
        self.assertEqual(len(yijing), 1)
        r = yijing[0]
        self.assertEqual(r["source_type"], "pilgrim")
        self.assertEqual(r["date_ce"], [651, 652])
        self.assertIn("forty years", r["event"])

    def test_diacritic_insensitive(self):
        # ASCII query must match the diacritic-bearing entity name.
        self.assertTrue(spine.find_anchors("nagarjuna"))
        self.assertTrue(spine.find_anchors("Samkhyakarika"))

    def test_nagarjuna_finds_mmk_taq(self):
        hits = spine.find_anchors("Nagarjuna")
        ids = {r["id"] for r in hits}
        self.assertIn("mulamadhyamakakarika-kumarajiva-409", ids)

    def test_derive_hard_taq(self):
        records = spine.find_anchors("Mulamadhyamakakarika")
        d = spine.derive_constraints(records)
        self.assertEqual(d["hard_taq"], 409)


class TestCorrect(unittest.TestCase):
    def test_wrong_traditional_date_flags_conflict(self):
        # The Indian tradition placing Bhartrihari in the 1st c. BCE
        # (brother of Vikramaditya) must conflict with Yijing's record.
        res = spine.correct("Bhartrihari", -100, -1)
        self.assertEqual(res["verdict"], "conflict")
        self.assertIsNone(res["corrected"])
        self.assertTrue(any("CONFLICT" in ln for ln in res["lines"]))

    def test_traditional_range_cut_by_taq(self):
        # A too-wide traditional range for the MMK is cut at the 409 TAQ.
        res = spine.correct("Mulamadhyamakakarika", 100, 500)
        self.assertEqual(res["verdict"], "corrected")
        self.assertEqual(res["corrected"], [100, 409])

    def test_agreeing_range_passes(self):
        res = spine.correct("Mulamadhyamakakarika", 150, 250)
        self.assertEqual(res["verdict"], "agrees")
        self.assertEqual(res["corrected"], [150, 250])

    def test_unknown_entity_no_data(self):
        res = spine.correct("Nonexistent Entity", 0, 100)
        self.assertEqual(res["verdict"], "no-data")


class TestLag(unittest.TestCase):
    def test_lag_command_runs(self):
        stats = spine.lag_stats()
        self.assertGreaterEqual(stats["n_solid"], 1)
        # Status must be one of the honest labels.
        self.assertIn(stats["status"],
                      ("insufficient", "provisional", "usable"))
        if stats["n_solid"] < spine.LAG_MIN_SOLID:
            self.assertEqual(stats["status"], "insufficient")
            self.assertIsNone(stats["median_midpoint"])
        else:
            self.assertIsNotNone(stats["median_midpoint"])
            lo, hi = stats["overall_range"]
            self.assertLessEqual(lo, hi)

    def test_nagarjuna_case_in_solid_set(self):
        solid, _ = spine.lag_cases()
        ids = {r["id"] for r in solid}
        self.assertIn("mulamadhyamakakarika-kumarajiva-409", ids)

    def test_contested_lags_excluded(self):
        # The Trimsika lag assumes the contested Vasubandhu date and
        # must NOT be in the solid set (circularity guard).
        solid, excluded = spine.lag_cases()
        self.assertIn("trimsika-xuanzang-659",
                      {r["id"] for r in excluded})
        self.assertNotIn("trimsika-xuanzang-659",
                         {r["id"] for r in solid})


class TestDataIntegrity(unittest.TestCase):
    def test_seed_size(self):
        anchors = spine.load_anchors()
        self.assertGreaterEqual(len(anchors), 30)

    def test_unique_ids_and_valid_ranges(self):
        anchors = spine.load_anchors()
        ids = [r["id"] for r in anchors]
        self.assertEqual(len(ids), len(set(ids)))
        for r in anchors:
            self.assertLessEqual(r["date_ce"][0], r["date_ce"][1])
            self.assertEqual(spine.validate_record(r, ()), [])


class TestValidation(unittest.TestCase):
    def test_add_rejects_bad_record(self):
        bad = {"id": "x", "indian_entity": "X"}  # missing most fields
        self.assertTrue(spine.validate_record(bad, ()))

    def test_add_rejects_bad_constraint(self):
        anchors = spine.load_anchors()
        r = dict(anchors[0])
        r["id"] = "brand-new-id"
        r["constraint_type"] = "WHENEVER"
        self.assertTrue(spine.validate_record(r, ()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
