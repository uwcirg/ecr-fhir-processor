"""T021 [US2]: provenance stamping (D4, provenance-metadata contract)."""

import unittest

import process

VERSION = "v1.2.3"
TS = "2026-06-09T14:03:22+00:00"
SRC = "CMS165_bulk_dial_high_00042.json"


class ProvenanceTest(unittest.TestCase):
    def _systems(self, meta):
        return {t["system"]: t for t in meta["tag"]}

    def test_three_tags_and_source(self):
        meta = process.stamp(None, VERSION, TS, SRC)
        systems = self._systems(meta)
        self.assertIn(process.SYSTEM_PROCESSED_BY, systems)
        self.assertIn(process.SYSTEM_PROCESSED_ON, systems)
        self.assertIn(process.SYSTEM_SOURCE_FILE, systems)
        by = systems[process.SYSTEM_PROCESSED_BY]
        self.assertEqual(by["code"], process.PROCESSOR_IDENTITY)
        self.assertEqual(by["version"], VERSION)
        self.assertEqual(systems[process.SYSTEM_PROCESSED_ON]["code"], TS)
        self.assertEqual(systems[process.SYSTEM_SOURCE_FILE]["code"], SRC)
        self.assertEqual(meta["source"], f"{process.SYSTEM_PROCESSED_BY}#{VERSION}")

    def test_idempotent_restamp_replaces_own_tags(self):
        meta = process.stamp(None, VERSION, TS, SRC)
        # Re-stamp with a new run -> still exactly three own tags (INV-2).
        meta2 = process.stamp(meta, "v2", "2026-06-10T00:00:00+00:00", "other.json")
        own = [t for t in meta2["tag"] if t["system"] in process.OWN_TAG_SYSTEMS]
        self.assertEqual(len(own), 3)
        systems = self._systems(meta2)
        self.assertEqual(systems[process.SYSTEM_PROCESSED_BY]["version"], "v2")
        self.assertEqual(systems[process.SYSTEM_SOURCE_FILE]["code"], "other.json")

    def test_preserves_foreign_tags_and_profile(self):
        existing = {
            "profile": ["http://hl7.org/fhir/us/ecr/StructureDefinition/eicr-composition"],
            "tag": [{"system": "http://other.example/system", "code": "keep-me"}],
        }
        meta = process.stamp(existing, VERSION, TS, SRC)
        self.assertEqual(meta["profile"],
                         ["http://hl7.org/fhir/us/ecr/StructureDefinition/eicr-composition"])
        foreign = [t for t in meta["tag"] if t["system"] == "http://other.example/system"]
        self.assertEqual(len(foreign), 1)
        self.assertEqual(foreign[0]["code"], "keep-me")

    def test_stamp_resource_creates_meta(self):
        res = {"resourceType": "Patient", "id": "p1"}
        process.stamp_resource(res, VERSION, TS, SRC)
        self.assertIn("meta", res)
        self.assertEqual(len(res["meta"]["tag"]), 3)


if __name__ == "__main__":
    unittest.main()
