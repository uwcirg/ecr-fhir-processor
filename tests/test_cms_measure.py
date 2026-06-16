"""003 [US2/US3]: CMS-measure derivation, stamping, idempotency, disagreement warning.

Covers:
- T006: cms_measure_from_filename derivation table (data-model §1, contract C-2/C-3).
- T007: stamp() adds exactly one cms-measure tag; idempotent re-stamp keeps one; other
  systems' tags and meta.profile survive (INV-CMS-2/3, contract C-5/C-6).
- T008: directory/filename disagreement warns only concrete-vs-different-concrete (FR-007, §4).
- T012 (US3): re-attribution on rename flips unknown -> CMS<n> in place, no duplicate tag.
"""

import tempfile
import unittest
from pathlib import Path

import process

VERSION = "v1.2.3"
TS = "2026-06-09T14:03:22+00:00"
SYS = "https://uwcirg.github.io/ecr-fhir-processor/CodeSystem/cms-measure"


# --------------------------------------------------------------------------- #
# T006: derivation (data-model §1)
# --------------------------------------------------------------------------- #


class DerivationTest(unittest.TestCase):
    CASES = [
        ("CMS165_bulk_nip_late_htn_00500.json", "CMS165"),
        ("CMS165_bulk_dial_high_00042.json", "CMS165"),
        ("CMS2_bulk_num_adult_svc_00028.json", "CMS2"),
        ("CMS122_DENOM_HbA1c_7p5_GoodControl.json", "CMS122"),
        ("cms165_x.json", "CMS165"),          # case-normalized
        ("CMS165.json", "CMS165"),            # digits terminated by '.'
        ("CMSX_x.json", "unknown"),           # CMS not followed by a digit
        ("CMSReport_x.json", "unknown"),      # non-numeric after CMS
        ("patient_export_2026.json", "unknown"),  # no CMS prefix (production shape)
    ]

    def test_derivation_table(self):
        for filename, expected in self.CASES:
            with self.subTest(filename=filename):
                self.assertEqual(process.cms_measure_from_filename(filename), expected)

    def test_codes_are_normalized_uppercase(self):
        # C-2/SC-005: never mixed case, never a raw fragment.
        self.assertEqual(process.cms_measure_from_filename("cms122_lower.json"), "CMS122")


# --------------------------------------------------------------------------- #
# T007: stamp() adds exactly one cms-measure tag; idempotent; additive
# --------------------------------------------------------------------------- #


def _cms_tags(meta):
    return [t for t in meta["tag"] if t["system"] == process.SYSTEM_CMS_MEASURE]


class StampCmsTagTest(unittest.TestCase):
    def test_adds_exactly_one_cms_tag_with_derived_code(self):
        meta = process.stamp(None, VERSION, TS, "CMS165_bulk_dial_high_00042.json")
        cms = _cms_tags(meta)
        self.assertEqual(len(cms), 1)
        self.assertEqual(cms[0]["system"], SYS)
        self.assertEqual(cms[0]["code"], "CMS165")
        self.assertEqual(cms[0]["display"], "controllable-bp")

    def test_unknown_filename_yields_unknown_sentinel(self):
        meta = process.stamp(None, VERSION, TS, "patient_export_2026.json")
        cms = _cms_tags(meta)
        self.assertEqual(len(cms), 1)
        self.assertEqual(cms[0]["code"], "unknown")
        self.assertEqual(cms[0]["display"], "unknown measure")

    def test_idempotent_restamp_keeps_exactly_one(self):
        meta = process.stamp(None, VERSION, TS, "CMS165_x.json")
        meta2 = process.stamp(meta, "v2", "2026-06-10T00:00:00+00:00", "CMS122_y.json")
        cms = _cms_tags(meta2)
        self.assertEqual(len(cms), 1)
        self.assertEqual(cms[0]["code"], "CMS122")
        self.assertEqual(cms[0]["display"], "poor-diabetic-control")

    def test_preserves_foreign_tags_and_profile(self):
        existing = {
            "profile": ["http://hl7.org/fhir/us/ecr/StructureDefinition/eicr-composition"],
            "tag": [{"system": "http://other.example/system", "code": "keep-me"}],
        }
        meta = process.stamp(existing, VERSION, TS, "CMS165_x.json")
        self.assertEqual(meta["profile"],
                         ["http://hl7.org/fhir/us/ecr/StructureDefinition/eicr-composition"])
        foreign = [t for t in meta["tag"] if t["system"] == "http://other.example/system"]
        self.assertEqual(len(foreign), 1)
        self.assertEqual(foreign[0]["code"], "keep-me")
        # Original provenance tags also still present alongside the new cms tag.
        self.assertEqual(len(_cms_tags(meta)), 1)


# --------------------------------------------------------------------------- #
# T012 (US3): re-attribution on rename
# --------------------------------------------------------------------------- #


class ReattributionTest(unittest.TestCase):
    def test_rename_reattributes_in_place_no_duplicate(self):
        res = {"resourceType": "Patient", "id": "p1"}
        # First run: prefix-less filename -> unknown.
        process.stamp_resource(res, VERSION, TS, "export_noprefix.json")
        self.assertEqual(_cms_tags(res["meta"])[0]["code"], "unknown")
        # Rename to the CMS convention and re-process the same resource dict.
        process.stamp_resource(res, "v2", "2026-06-10T00:00:00+00:00",
                               "CMS2_reattributed.json")
        cms = _cms_tags(res["meta"])
        self.assertEqual(len(cms), 1)            # SC-004: no duplicate tag
        self.assertEqual(cms[0]["code"], "CMS2")


# --------------------------------------------------------------------------- #
# T008: directory/filename disagreement warning (FR-007, data-model §4)
# --------------------------------------------------------------------------- #


def _write(directory, slug, filename):
    sub = Path(directory) / slug
    sub.mkdir(parents=True, exist_ok=True)
    (sub / filename).write_text("{}", encoding="utf-8")


class DisagreementWarningTest(unittest.TestCase):
    def test_concrete_vs_different_concrete_warns(self):
        with tempfile.TemporaryDirectory() as d:
            # filename CMS122 under controllable-bp (CMS165) -> mismatch.
            _write(d, "controllable-bp", "CMS122_misfiled.json")
            with self.assertLogs(process.logger, level="WARNING") as cm:
                process.discover_inputs(d)
            joined = " ".join(cm.output)
            self.assertIn("CMS122", joined)
            self.assertIn("controllable-bp", joined)

    def test_concrete_matching_directory_does_not_warn(self):
        with tempfile.TemporaryDirectory() as d:
            _write(d, "controllable-bp", "CMS165_ok.json")
            with self.assertNoLogs(process.logger, level="WARNING"):
                process.discover_inputs(d)

    def test_unknown_filename_does_not_warn(self):
        with tempfile.TemporaryDirectory() as d:
            _write(d, "controllable-bp", "patient_export.json")
            with self.assertNoLogs(process.logger, level="WARNING"):
                process.discover_inputs(d)

    def test_unmapped_directory_slug_does_not_warn(self):
        with tempfile.TemporaryDirectory() as d:
            _write(d, "some-other-folder", "CMS165_x.json")
            with self.assertNoLogs(process.logger, level="WARNING"):
                process.discover_inputs(d)


if __name__ == "__main__":
    unittest.main()
