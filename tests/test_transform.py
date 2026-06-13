"""T012 [US1]: collection -> independent per-resource PUT plan (D2, FR-020/FR-022).

Rewritten for the constitution v1.1.0 model: a collection Bundle yields one independent
PUT per contained resource (no atomic ``transaction`` Bundle).
"""

import unittest

import process


class PlanCollectionPutsTest(unittest.TestCase):
    def _collection(self):
        return {
            "resourceType": "Bundle",
            "type": "collection",
            "entry": [
                {"fullUrl": "urn:x", "resource": {"resourceType": "Patient", "id": "p1"}},
                {"resource": {"resourceType": "Condition", "id": "c1"}},
            ],
        }

    def test_one_put_unit_per_resource(self):
        units = process.plan_collection_puts(self._collection())
        self.assertEqual(len(units), 2)
        self.assertTrue(all(isinstance(u, process.PutUnit) for u in units))

    def test_put_urls_and_ids_retained(self):
        units = process.plan_collection_puts(self._collection())
        self.assertEqual(units[0].url, "Patient/p1")
        self.assertEqual(units[1].url, "Condition/c1")
        self.assertEqual(units[0].resource_id, "p1")
        self.assertEqual(units[0].resource["id"], "p1")

    def test_no_transaction_bundle_produced(self):
        # The planner returns a plain list of units — never a Bundle of any type, and
        # certainly never type="transaction" (FR-020, FR-022, D2).
        result = process.plan_collection_puts(self._collection())
        self.assertIsInstance(result, list)
        self.assertNotIsInstance(result, dict)

    def test_resource_shared_by_reference(self):
        # Stamping the unit's resource must be reflected in the source bundle (the
        # pipeline stamps via the unit before PUTting).
        bundle = self._collection()
        units = process.plan_collection_puts(bundle)
        units[0].resource["_marker"] = True
        self.assertTrue(bundle["entry"][0]["resource"]["_marker"])

    def test_source_bundle_type_unchanged(self):
        src = self._collection()
        process.plan_collection_puts(src)
        self.assertEqual(src["type"], "collection")
        self.assertNotIn("request", src["entry"][0])

    def test_missing_id_raises(self):
        bad = {"resourceType": "Bundle", "type": "collection",
               "entry": [{"resource": {"resourceType": "Patient"}}]}
        with self.assertRaises(ValueError):
            process.plan_collection_puts(bad)


if __name__ == "__main__":
    unittest.main()
