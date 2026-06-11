"""T012 [US1]: collection -> transaction transform (D2, fhir-submission contract)."""

import unittest

import process


class TransformTest(unittest.TestCase):
    def _collection(self):
        return {
            "resourceType": "Bundle",
            "type": "collection",
            "entry": [
                {"fullUrl": "urn:x", "resource": {"resourceType": "Patient", "id": "p1"}},
                {"resource": {"resourceType": "Condition", "id": "c1"}},
            ],
        }

    def test_type_becomes_transaction(self):
        out = process.transform_collection_to_transaction(self._collection())
        self.assertEqual(out["type"], "transaction")

    def test_each_entry_gets_put_request(self):
        out = process.transform_collection_to_transaction(self._collection())
        self.assertEqual(out["entry"][0]["request"],
                         {"method": "PUT", "url": "Patient/p1"})
        self.assertEqual(out["entry"][1]["request"],
                         {"method": "PUT", "url": "Condition/c1"})

    def test_ids_retained_and_fullurl_preserved(self):
        out = process.transform_collection_to_transaction(self._collection())
        self.assertEqual(out["entry"][0]["resource"]["id"], "p1")
        self.assertEqual(out["entry"][0]["fullUrl"], "urn:x")
        self.assertNotIn("fullUrl", out["entry"][1])

    def test_source_bundle_not_mutated(self):
        src = self._collection()
        process.transform_collection_to_transaction(src)
        self.assertEqual(src["type"], "collection")
        self.assertNotIn("request", src["entry"][0])

    def test_missing_id_raises(self):
        bad = {"resourceType": "Bundle", "type": "collection",
               "entry": [{"resource": {"resourceType": "Patient"}}]}
        with self.assertRaises(ValueError):
            process.transform_collection_to_transaction(bad)


if __name__ == "__main__":
    unittest.main()
