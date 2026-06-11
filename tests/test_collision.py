"""T013 [US1]: (resourceType, id) collision guard (FR-019, D4b)."""

import unittest

import process


class CollisionTest(unittest.TestCase):
    def test_new_then_identical_is_dedup(self):
        tracker = process.CollisionTracker()
        res = {"resourceType": "Practitioner", "id": "b2360d5d", "name": "x"}
        self.assertEqual(tracker.check("Practitioner", "b2360d5d", res), "new")
        # Same key, identical content -> allowed dedup.
        self.assertEqual(tracker.check("Practitioner", "b2360d5d", dict(res)), "duplicate")

    def test_differing_content_raises(self):
        tracker = process.CollisionTracker()
        tracker.check("Patient", "p1", {"resourceType": "Patient", "id": "p1", "a": 1})
        with self.assertRaises(process.CollisionError):
            tracker.check("Patient", "p1", {"resourceType": "Patient", "id": "p1", "a": 2})

    def test_different_keys_independent(self):
        tracker = process.CollisionTracker()
        self.assertEqual(tracker.check("Patient", "p1", {"x": 1}), "new")
        self.assertEqual(tracker.check("Patient", "p2", {"x": 2}), "new")
        self.assertEqual(tracker.check("Condition", "p1", {"x": 3}), "new")

    def test_canonical_ignores_key_order(self):
        tracker = process.CollisionTracker()
        tracker.check("Patient", "p1", {"a": 1, "b": 2})
        # Same content, different insertion order -> still a duplicate, not a collision.
        self.assertEqual(tracker.check("Patient", "p1", {"b": 2, "a": 1}), "duplicate")


if __name__ == "__main__":
    unittest.main()
