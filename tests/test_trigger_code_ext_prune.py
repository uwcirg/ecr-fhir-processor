"""eICR trigger-code empty-sub-extension prune (Cause 4; contracts/trigger-code-ext-prune.md).

Cause 4 content transform: remove every child of an `eicr-trigger-code-flag-extension`
that carries neither a `value[x]` nor nested `extension` (a url-only shell that violates
base-FHIR `ext-1`) — in the sample data an empty `triggerCodeValueSetVersion`. The
`triggerCode`/`triggerCodeValueSet` siblings (the clinical payload) are preserved.
Non-fabricating, structure-only, idempotent, and applied to the Composition nested in a
message/document Bundle too.
"""

import copy
import unittest

import process

FLAG_URL = process.TRIGGER_CODE_FLAG_EXTENSION_URL


def _flag_ext(*children):
    return {"url": FLAG_URL, "extension": list(children)}


VALUE_SET = {"url": "triggerCodeValueSet", "valueString": "urn:oid:2.16.840.1.114222.4.11.7508"}
EMPTY_VERSION = {"url": "triggerCodeValueSetVersion"}  # url-only shell → violates ext-1
REAL_VERSION = {"url": "triggerCodeValueSetVersion", "valueString": "20220924"}
TRIGGER_CODE = {"url": "triggerCode",
                "valueCoding": {"system": "http://loinc.org", "code": "73832-8"}}


def _composition(flag_extension):
    """A Composition whose section[0].entry[0] carries `flag_extension`."""
    return {
        "resourceType": "Composition", "id": "comp-1", "status": "final",
        "section": [{
            "code": {"text": "trigger section"},
            "entry": [{
                "extension": [flag_extension],
                "reference": "Observation/obs-1",
            }],
        }],
    }


class PruneTriggerCodeExtTest(unittest.TestCase):
    # C1: removes the value/child-less sub-extension; resource becomes ext-1-clean.
    def test_removes_empty_sub_extension(self):
        comp = _composition(_flag_ext(VALUE_SET, EMPTY_VERSION, TRIGGER_CODE))
        removed = process.prune_empty_trigger_code_extensions(comp, "f.json")
        self.assertEqual(removed, 1)
        kept = comp["section"][0]["entry"][0]["extension"][0]["extension"]
        self.assertEqual([c["url"] for c in kept],
                         ["triggerCodeValueSet", "triggerCode"])

    # C2: the clinical siblings (triggerCode, triggerCodeValueSet) survive byte-identical.
    def test_preserves_clinical_siblings(self):
        vs, tc = copy.deepcopy(VALUE_SET), copy.deepcopy(TRIGGER_CODE)
        comp = _composition(_flag_ext(vs, EMPTY_VERSION, tc))
        process.prune_empty_trigger_code_extensions(comp, "f.json")
        kept = comp["section"][0]["entry"][0]["extension"][0]["extension"]
        self.assertEqual(kept, [vs, tc])

    # C1: a populated version (valueString present) is NOT removed.
    def test_keeps_populated_version(self):
        comp = _composition(_flag_ext(VALUE_SET, REAL_VERSION, TRIGGER_CODE))
        baseline = copy.deepcopy(comp)
        removed = process.prune_empty_trigger_code_extensions(comp, "f.json")
        self.assertEqual(removed, 0)
        self.assertEqual(comp, baseline)

    # C3/C4: no-op on a resource with no trigger-code flag extension; nothing fabricated.
    def test_noop_without_flag_extension(self):
        comp = _composition({"url": "http://example.org/other-ext", "valueString": "x"})
        baseline = copy.deepcopy(comp)
        self.assertEqual(process.prune_empty_trigger_code_extensions(comp, "f.json"), 0)
        self.assertEqual(comp, baseline)

    # C5: idempotent — a second call removes 0 and changes nothing.
    def test_idempotent(self):
        comp = _composition(_flag_ext(VALUE_SET, EMPTY_VERSION, TRIGGER_CODE))
        process.prune_empty_trigger_code_extensions(comp, "f.json")
        after_first = copy.deepcopy(comp)
        removed = process.prune_empty_trigger_code_extensions(comp, "f.json")
        self.assertEqual(removed, 0)
        self.assertEqual(comp, after_first)

    # C6: each removal logs a WARNING naming the sub-extension + source, keyed to Cause 4.
    def test_warning_names_removed_sub_extension(self):
        comp = _composition(_flag_ext(VALUE_SET, EMPTY_VERSION, TRIGGER_CODE))
        with self.assertLogs("ecr-fhir-processor", level="WARNING") as cap:
            process.prune_empty_trigger_code_extensions(comp, "src.json")
        text = "\n".join(cap.output)
        self.assertIn("triggerCodeValueSetVersion", text)
        self.assertIn(process.REMEDIATION_TRIGGER_CODE_EXT_PRUNE, text)
        self.assertIn("src.json", text)

    # C4: never fabricates — an empty extension is removed, never given a value to "fix" it.
    def test_no_fabrication(self):
        comp = _composition(_flag_ext(VALUE_SET, EMPTY_VERSION, TRIGGER_CODE))
        process.prune_empty_trigger_code_extensions(comp, "f.json")
        kept = comp["section"][0]["entry"][0]["extension"][0]["extension"]
        # No triggerCodeValueSetVersion was invented with a fabricated valueString.
        self.assertNotIn("triggerCodeValueSetVersion", [c["url"] for c in kept])


class PruneNestedInBundleTest(unittest.TestCase):
    # C7: a Composition nested in a document Bundle inside a message Bundle is cleaned; the
    # rest of the message Bundle is otherwise unchanged.
    def test_walks_into_message_bundle(self):
        comp = _composition(_flag_ext(VALUE_SET, EMPTY_VERSION, TRIGGER_CODE))
        message = {
            "resourceType": "Bundle", "type": "message", "id": "msg-1",
            "entry": [
                {"resource": {"resourceType": "MessageHeader", "id": "mh"}},
                {"resource": {
                    "resourceType": "Bundle", "type": "document", "id": "doc-1",
                    "entry": [{"resource": comp}],
                }},
            ],
        }
        removed = process.prune_empty_trigger_code_extensions(message, "msg.json")
        self.assertEqual(removed, 1)
        nested = message["entry"][1]["resource"]["entry"][0]["resource"]
        kept = nested["section"][0]["entry"][0]["extension"][0]["extension"]
        self.assertEqual([c["url"] for c in kept],
                         ["triggerCodeValueSet", "triggerCode"])


class HelperTest(unittest.TestCase):
    def test_extension_carries_nothing(self):
        self.assertTrue(process._extension_carries_nothing({"url": "x"}))
        self.assertFalse(process._extension_carries_nothing({"url": "x", "valueString": "v"}))
        self.assertFalse(
            process._extension_carries_nothing({"url": "x", "extension": [{"url": "y"}]}))
        # An empty child list still counts as "no children".
        self.assertTrue(process._extension_carries_nothing({"url": "x", "extension": []}))


if __name__ == "__main__":
    unittest.main()
