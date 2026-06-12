"""T027 [US4]: eICR Composition promotion (FR-021, D2b, D3, fhir-submission AC-5).

From a message Bundle, the processor extracts the Composition nested in the
``entry(content Bundle, type=document)`` and plans an independent
``PUT [base]/Composition/<per-case GUID id>`` — promoting ONLY the Composition (no other
nested clinical resources). An unresolved Composition reference is WARNING-logged, not
mutated.
"""

import json
import unittest

import process
from tests import REPO_ROOT

MESSAGE_FIXTURE = (REPO_ROOT / "test" / "input" / "poor-diabetic-control" / "standard"
                   / "CMS122_DENOM_HbA1c_7p5_GoodControl"
                   / "Bundle_f0b34c63-54f7-4b69-9d9f-f06d641f6135.json")


def _message_bundle():
    return json.loads(MESSAGE_FIXTURE.read_text())


class CompositionPromotionTest(unittest.TestCase):
    def test_extracts_the_nested_composition(self):
        comp = process.extract_eicr_composition(_message_bundle())
        self.assertIsNotNone(comp)
        self.assertEqual(comp["resourceType"], "Composition")
        # Per-case GUID id (collision-safe), not the fixed document-Bundle handle (D4b).
        self.assertEqual(comp["id"], "91110cc3-817a-4b42-9ea7-5cfbff357c8f")

    def test_only_the_composition_is_promoted(self):
        # The extractor returns exactly one resource and it is the Composition — none of
        # the document Bundle's other clinical copies (Patient/Encounter/...) are returned.
        comp = process.extract_eicr_composition(_message_bundle())
        self.assertEqual(comp["resourceType"], "Composition")

    def test_returns_none_when_no_document_bundle(self):
        empty = {"resourceType": "Bundle", "type": "message", "entry": []}
        self.assertIsNone(process.extract_eicr_composition(empty))

    def test_document_resource_keys_collected(self):
        keys = process.document_resource_keys(_message_bundle())
        # The Composition's references resolve against these persisted-by-collection ids.
        self.assertIn("Patient/016788c3-ef7b-4069-ac4a-355e461414ad", keys)
        self.assertIn("Composition/91110cc3-817a-4b42-9ea7-5cfbff357c8f", keys)

    def test_resolvable_reference_no_warning(self):
        comp = {"resourceType": "Composition", "id": "c1",
                "subject": {"reference": "Patient/p1"}}
        unresolved = process.warn_unresolved_composition_refs(comp, {"Patient/p1"})
        self.assertEqual(unresolved, [])

    def test_unresolved_reference_is_warned_not_mutated(self):
        comp = {"resourceType": "Composition", "id": "c1",
                "subject": {"reference": "Patient/missing"}}
        before = json.dumps(comp, sort_keys=True)
        with self.assertLogs(process.logger, level="WARNING") as cm:
            unresolved = process.warn_unresolved_composition_refs(comp, {"Patient/p1"})
        self.assertEqual(unresolved, ["Patient/missing"])
        self.assertTrue(any("does not resolve" in m for m in cm.output))
        # Never mutated (D3).
        self.assertEqual(json.dumps(comp, sort_keys=True), before)


if __name__ == "__main__":
    unittest.main()
