"""MeasureReport `mrp-2` stratum-prune transform (contracts/stratum-prune.md C1–C9).

The single content transform this feature introduces (Cause 2): remove every stratifier
`stratum` that has neither `value` nor `component` — malformed structure, not clinical
content — logging any population counts it carried. Non-fabricating, structure-only,
idempotent, and applied to nested MeasureReports inside a message/document Bundle too.
"""

import copy
import unittest

import process


def _stratum(value=None, component=None, populations=None):
    """Build a stratum with optional value/component and population counts."""
    s = {}
    if value is not None:
        s["value"] = value
    if component is not None:
        s["component"] = component
    if populations is not None:
        s["population"] = [
            {"code": {"coding": [{"system": "http://terminology.hl7.org/"
                                  "CodeSystem/measure-population", "code": code}]},
             "count": count}
            for code, count in populations
        ]
    s["measureScore"] = {"value": 0.5}
    return s


def _report(strata):
    """A minimal MeasureReport with one group + one stratifier holding `strata`."""
    return {
        "resourceType": "MeasureReport",
        "id": "mr-1",
        "status": "complete",
        "measureScore": {"value": 0.5},
        "group": [{
            "id": "g0",
            "population": [{"code": {"text": "numerator"}, "count": 1}],
            "stratifier": [{"code": [{"text": "strat"}], "stratum": list(strata)}],
        }],
    }


CONFORMING = _stratum(value={"text": "2186-5"}, populations=[("numerator", 3)])
MALFORMED = _stratum(populations=[("initial-population", 1), ("numerator", 7)])
COMPONENT = _stratum(component=[{"value": {"text": "x"}}], populations=[("denominator", 2)])


class PruneStrataTest(unittest.TestCase):
    # Scenario 1 / C1: removes the value+component-less stratum, resource mrp-2-clean.
    # When the removal empties the list the `stratum` property is deleted, not left as
    # `[]` (an empty array is itself a base-FHIR violation → new HL7 signature, FR-009).
    def test_removes_malformed_stratum(self):
        report = _report([MALFORMED])
        result = process.prune_measurereport_strata(report, "f.json")
        self.assertEqual(result.removed, 1)
        self.assertNotIn("stratum", report["group"][0]["stratifier"][0])

    # Scenario 2 / C2: conforming siblings (value or component) kept byte-identical.
    def test_preserves_conforming_siblings(self):
        conforming = copy.deepcopy(CONFORMING)
        component = copy.deepcopy(COMPONENT)
        report = _report([conforming, MALFORMED, component])
        result = process.prune_measurereport_strata(report, "f.json")
        self.assertEqual(result.removed, 1)
        kept = report["group"][0]["stratifier"][0]["stratum"]
        self.assertEqual(kept, [conforming, component])  # malformed gone, siblings intact

    # Scenario 3 / C3+C4: no-op on clean input → returns 0, deep-equal.
    def test_noop_on_clean_input(self):
        report = _report([CONFORMING, COMPONENT])
        baseline = copy.deepcopy(report)
        result = process.prune_measurereport_strata(report, "f.json")
        self.assertEqual(result.removed, 0)
        self.assertEqual(report, baseline)

    # Scenario 4 / C5: idempotent — a second call removes 0 and changes nothing.
    def test_idempotent(self):
        report = _report([CONFORMING, MALFORMED])
        process.prune_measurereport_strata(report, "f.json")
        after_first = copy.deepcopy(report)
        result = process.prune_measurereport_strata(report, "f.json")
        self.assertEqual(result.removed, 0)
        self.assertEqual(report, after_first)

    # Scenario 5 / C6: each removal logs a WARNING carrying the population counts.
    def test_warning_carries_population_counts(self):
        report = _report([MALFORMED])
        with self.assertLogs("ecr-fhir-processor", level="WARNING") as cap:
            process.prune_measurereport_strata(report, "src.json")
        text = "\n".join(cap.output)
        self.assertIn("7", text)                 # the distinctive numerator count
        self.assertIn("initial-population", text)
        self.assertIn(process.REMEDIATION_MRP2_STRATUM_PRUNE, text)
        self.assertIn("src.json", text)          # source attribution

    # C9: never fabricates — the transform only ever removes, never adds keys.
    def test_no_fabrication(self):
        report = _report([MALFORMED])
        process.prune_measurereport_strata(report, "f.json")
        # No stratum with value/component was invented to satisfy mrp-2; the emptied
        # `stratum` property is removed entirely rather than fabricated or left as [].
        self.assertNotIn("stratum", report["group"][0]["stratifier"][0])

    # C4 (corrected): a stratifier keeping ≥1 conforming stratum retains a non-empty
    # `stratum` list; only a fully-emptied list drops the property.
    def test_partial_removal_keeps_nonempty_stratum_property(self):
        conforming = copy.deepcopy(CONFORMING)
        report = _report([conforming, MALFORMED])
        process.prune_measurereport_strata(report, "f.json")
        self.assertEqual(report["group"][0]["stratifier"][0]["stratum"], [conforming])

    # Scenario 7 / C3: everything else on the MeasureReport is untouched.
    def test_everything_else_untouched(self):
        report = _report([CONFORMING, MALFORMED])
        baseline = copy.deepcopy(report)
        process.prune_measurereport_strata(report, "f.json")
        # Remove the malformed path from the baseline, then assert deep-equality.
        baseline["group"][0]["stratifier"][0]["stratum"] = [CONFORMING]
        self.assertEqual(report, baseline)


class PruneNestedTest(unittest.TestCase):
    # Scenario 6 / C7: a MeasureReport nested in a document Bundle inside a message
    # Bundle is pruned; the outer Bundle is otherwise unchanged.
    def test_nested_measurereport_pruned(self):
        report = _report([CONFORMING, MALFORMED])
        message = {
            "resourceType": "Bundle", "type": "message", "id": "msg-1",
            "entry": [
                {"resource": {"resourceType": "MessageHeader", "id": "mh"}},
                {"resource": {
                    "resourceType": "Bundle", "type": "document", "id": "doc-1",
                    "entry": [
                        {"resource": {"resourceType": "Composition", "id": "c"}},
                        {"resource": report},
                    ],
                }},
            ],
        }
        baseline = copy.deepcopy(message)
        result = process.prune_nested_measurereports(message, "msg.json")
        self.assertEqual(result.removed, 1)
        # The nested MeasureReport lost its malformed stratum …
        nested = message["entry"][1]["resource"]["entry"][1]["resource"]
        self.assertEqual(nested["group"][0]["stratifier"][0]["stratum"], [CONFORMING])
        # … and nothing else in the outer Bundle changed.
        baseline["entry"][1]["resource"]["entry"][1]["resource"][
            "group"][0]["stratifier"][0]["stratum"] = [CONFORMING]
        self.assertEqual(message, baseline)

    def test_no_measurereport_is_a_noop(self):
        message = {"resourceType": "Bundle", "type": "message", "id": "m",
                   "entry": [{"resource": {"resourceType": "Patient", "id": "p"}}]}
        baseline = copy.deepcopy(message)
        self.assertEqual(process.prune_nested_measurereports(message, "m.json").removed, 0)
        self.assertEqual(message, baseline)


if __name__ == "__main__":
    unittest.main()


def _multi_report(*groups):
    """A MeasureReport whose `group[i].stratifier` is `groups[i]` (a list of stratifiers)."""
    return {
        "resourceType": "MeasureReport", "id": "mr-multi", "status": "complete",
        "group": [{"id": f"g{i}", "stratifier": list(strats)}
                  for i, strats in enumerate(groups)],
    }


def _strat(strata=None, **extra):
    """A stratifier dict; `strata=None` omits the `stratum` key entirely."""
    s = dict(extra)
    if strata is not None:
        s["stratum"] = [copy.deepcopy(x) for x in strata]
    return s


class PruneCountsTest(unittest.TestCase):
    """008 contract R1–R4: removed / kept / emptied counts (scenarios 1–5, 8)."""

    def test_emptied_stratifier_and_untouched_sibling(self):  # scenario 1
        report = _multi_report([_strat([MALFORMED]), _strat([CONFORMING, COMPONENT])])
        self.assertEqual(process.prune_measurereport_strata(report, "f.json"),
                         process.StratumPruneResult(removed=1, kept=2, emptied=1))

    def test_partial_removal_does_not_empty(self):  # scenario 2
        report = _multi_report([_strat([CONFORMING, MALFORMED, COMPONENT])])
        self.assertEqual(process.prune_measurereport_strata(report, "f.json"),
                         process.StratumPruneResult(removed=1, kept=2, emptied=0))

    def test_pre_empty_stratifiers_not_counted(self):  # scenario 3 / FR-003
        report = _multi_report([_strat(None), _strat([]), _strat([MALFORMED])])
        result = process.prune_measurereport_strata(report, "f.json")
        self.assertEqual(result, process.StratumPruneResult(removed=1, kept=0, emptied=1))
        # The input `stratum: []` is left exactly as it was (prune logic unchanged).
        self.assertEqual(report["group"][0]["stratifier"][1], {"stratum": []})

    def test_clean_report_counts_kept_only(self):  # scenario 4
        report = _multi_report([_strat([CONFORMING, COMPONENT])])
        self.assertEqual(process.prune_measurereport_strata(report, "f.json"),
                         process.StratumPruneResult(removed=0, kept=2, emptied=0))

    def test_idempotent_counts(self):  # scenario 5
        report = _multi_report([_strat([MALFORMED]), _strat([CONFORMING, MALFORMED])])
        first = process.prune_measurereport_strata(report, "f.json")
        second = process.prune_measurereport_strata(report, "f.json")
        self.assertEqual(first, process.StratumPruneResult(removed=2, kept=1, emptied=1))
        self.assertEqual(second, process.StratumPruneResult(removed=0, kept=1, emptied=0))

    def test_nested_results_are_summed(self):  # scenario 8
        direct = _multi_report([_strat([MALFORMED]), _strat([CONFORMING])])
        nested = _multi_report([_strat([CONFORMING, MALFORMED, COMPONENT])])
        message = {
            "resourceType": "Bundle", "type": "message", "id": "msg",
            "entry": [
                {"resource": direct},
                {"resource": {"resourceType": "Bundle", "type": "document", "id": "doc",
                              "entry": [{"resource": nested}]}},
            ],
        }
        self.assertEqual(process.prune_nested_measurereports(message, "msg.json"),
                         process.StratumPruneResult(removed=2, kept=3, emptied=1))

    def test_result_addition(self):
        a = process.StratumPruneResult(1, 2, 1)
        b = process.StratumPruneResult(3, 4, 0)
        self.assertEqual(a + b, process.StratumPruneResult(4, 6, 1))
        self.assertEqual(process.StratumPruneResult() + a, a)


class StratifierLabelTest(unittest.TestCase):
    """008 contract R6 (scenario 7): id → code=… → text=… → #index, never empty."""

    CODE = [{"coding": [{"system": "s", "code": "plan", "display": "SDE Payer"}]}]

    def test_id_wins(self):
        self.assertEqual(process._stratifier_label(
            {"id": "stratifier-payer", "code": self.CODE}, 1), "stratifier-payer")

    def test_first_coding_code(self):
        self.assertEqual(process._stratifier_label({"code": self.CODE}, 1), "code=plan")

    def test_text_when_no_coding_code(self):
        stratifier = {"code": [{"coding": [{"system": "s"}], "text": "SDE Payer"}]}
        self.assertEqual(process._stratifier_label(stratifier, 1), "text=SDE Payer")

    def test_lone_dict_code_tolerated(self):
        self.assertEqual(process._stratifier_label({"code": self.CODE[0]}, 1), "code=plan")

    def test_index_fallback(self):
        self.assertEqual(process._stratifier_label({}, 3), "#3")
        self.assertEqual(process._stratifier_label({"id": "", "code": []}, 0), "#0")


class PruneWarningLocationTest(unittest.TestCase):
    """008 contract R5 (scenario 6): each WARNING names its group index + stratifier."""

    def test_each_warning_names_its_stratifier(self):
        report = _multi_report(
            [_strat([MALFORMED], id="strat-a")],
            [_strat([CONFORMING, MALFORMED], code=[{"text": "strat-b"}])],
        )
        with self.assertLogs("ecr-fhir-processor", level="WARNING") as cap:
            process.prune_measurereport_strata(report, "src.json")
        self.assertEqual(len(cap.records), 2)
        first, second = cap.output
        self.assertIn("group[0] stratifier strat-a", first)
        self.assertIn("group[1] stratifier text=strat-b", second)
        for line in cap.output:
            self.assertTrue(line.startswith("WARNING:"))
            self.assertIn(process.REMEDIATION_MRP2_STRATUM_PRUNE, line)
            self.assertIn("src.json", line)
            self.assertIn("numerator=7", line)


class CleanReportSilenceTest(unittest.TestCase):
    """008 FR-007 (scenario 4): a report needing no prune logs no WARNING."""

    def test_no_warning_for_clean_report(self):
        report = _multi_report([_strat([CONFORMING, COMPONENT], id="s")])
        with self.assertNoLogs("ecr-fhir-processor", level="WARNING"):
            process.prune_measurereport_strata(report, "f.json")
