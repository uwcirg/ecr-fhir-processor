"""T033: input discovery & classification over test/input/ (coverage for T010)."""

import unittest

import process
from tests import REPO_ROOT

TEST_INPUT = REPO_ROOT / "test" / "input"


class ClassifyTest(unittest.TestCase):
    def test_collection_bundle(self):
        self.assertEqual(
            process.classify_resource({"resourceType": "Bundle", "type": "collection"}),
            process.KIND_COLLECTION)

    def test_message_bundle(self):
        self.assertEqual(
            process.classify_resource({"resourceType": "Bundle", "type": "message"}),
            process.KIND_MESSAGE)

    def test_measure_report(self):
        self.assertEqual(
            process.classify_resource({"resourceType": "MeasureReport"}),
            process.KIND_MEASURE_REPORT)

    def test_unknown(self):
        self.assertEqual(
            process.classify_resource({"resourceType": "Patient"}),
            process.KIND_UNKNOWN)
        self.assertEqual(
            process.classify_resource({"resourceType": "Bundle", "type": "document"}),
            process.KIND_UNKNOWN)


class DiscoveryTest(unittest.TestCase):
    def test_discovers_all_fixtures(self):
        files = process.discover_inputs(str(TEST_INPUT))
        self.assertEqual(len(files), 13)

    def test_measure_and_population_derived(self):
        files = process.discover_inputs(str(TEST_INPUT))
        bp = [f for f in files if f.measure == "controllable-bp"]
        self.assertTrue(bp)
        self.assertTrue(all(f.population in ("standard", "not-in-population") for f in bp))

    def test_measure_filter(self):
        only = process.discover_inputs(str(TEST_INPUT), measure_filter="controllable-bp")
        self.assertTrue(only)
        self.assertTrue(all(f.measure == "controllable-bp" for f in only))

    def test_every_fixture_classifies_known(self):
        import json
        for f in process.discover_inputs(str(TEST_INPUT)):
            with f.path.open(encoding="utf-8") as fh:
                data = json.load(fh)
            self.assertNotEqual(process.classify_resource(data), process.KIND_UNKNOWN,
                                f"{f.filename} classified as unknown")


if __name__ == "__main__":
    unittest.main()
