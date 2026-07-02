"""RunSummary stratification by FHIR resource type (D8, _report_summary)."""

import unittest

import process


def _outcome(action, status):
    return process.FileOutcome("f.json", "collection-bundle", action, 1, status)


class ResourceTypeDerivationTest(unittest.TestCase):
    def test_derived_from_put_action(self):
        self.assertEqual(_outcome("PUT Observation/abc", "succeeded").resource_type,
                         "Observation")

    def test_id_with_dots_and_dashes_is_not_split(self):
        # FHIR ids may contain '-' and '.'; only the first '/' separates type from id.
        o = _outcome("PUT MeasureReport/a24a40a1-d202-43be", "failed")
        self.assertEqual(o.resource_type, "MeasureReport")

    def test_file_level_action_has_no_resource_type(self):
        self.assertIsNone(process.FileOutcome("f.json", "unknown", "skip", 0,
                                              "skipped").resource_type)

    def test_explicit_resource_type_preserved(self):
        o = process.FileOutcome("f.json", "k", "skip", 0, "skipped",
                                resource_type="Patient")
        self.assertEqual(o.resource_type, "Patient")


class ReportSummaryStratificationTest(unittest.TestCase):
    def _summary(self):
        s = process.RunSummary(read=1, submitted=3, succeeded=2, failed=1, skipped=0)
        s.outcomes = [
            _outcome("PUT Observation/a", "succeeded"),
            _outcome("PUT Observation/b", "failed"),
            _outcome("PUT Patient/c", "succeeded"),
            process.FileOutcome("bad.json", "unknown", "skip", 0, "skipped"),
        ]
        return s

    def test_per_type_lines_emitted(self):
        with self.assertLogs("ecr-fhir-processor", level="INFO") as cap:
            process._report_summary(self._summary(), dry_run=False)
        text = "\n".join(cap.output)
        self.assertIn("resources by type", text)
        self.assertIn("Observation", text)
        self.assertIn("submitted=2", text)  # 1 succeeded + 1 failed
        self.assertIn("Patient", text)
        # The type-less skipped file must not appear as its own type row.
        self.assertNotIn("None ", text)

    def test_totals_line_labels_units(self):
        with self.assertLogs("ecr-fhir-processor", level="INFO") as cap:
            process._report_summary(self._summary(), dry_run=False)
        text = "\n".join(cap.output)
        self.assertIn("read=1 input-files", text)
        self.assertIn("resources: submitted=3", text)


class RemediatedDeferredStratificationTest(unittest.TestCase):
    """Per-type and totals reporting of the storability statuses (FR-012, SC-006)."""

    def _summary(self):
        s = process.RunSummary(read=2, submitted=3, succeeded=1, remediated=1,
                               deferred=1, failed=0, skipped=0)
        s.outcomes = [
            _outcome("PUT Observation/a", "succeeded"),
            _outcome("PUT MeasureReport/b", "remediated"),
            _outcome("PUT MeasureReport/c", "deferred"),
        ]
        return s

    def test_per_type_row_reports_remediated_and_deferred(self):
        with self.assertLogs("ecr-fhir-processor", level="INFO") as cap:
            process._report_summary(self._summary(), dry_run=False)
        text = "\n".join(cap.output)
        self.assertIn("remediated=1", text)
        self.assertIn("deferred=1", text)
        # MeasureReport row carries both the remediated and deferred outcomes.
        mr_line = next(ln for ln in cap.output
                       if "MeasureReport" in ln and "submitted" in ln)
        self.assertIn("remediated=1", mr_line)
        self.assertIn("deferred=1", mr_line)

    def test_totals_line_includes_remediated_and_deferred(self):
        with self.assertLogs("ecr-fhir-processor", level="INFO") as cap:
            process._report_summary(self._summary(), dry_run=False)
        totals = next(ln for ln in cap.output if "input-files" in ln)
        self.assertIn("remediated=1", totals)
        self.assertIn("deferred=1", totals)


class RecordRemediationTest(unittest.TestCase):
    """`_record_remediation` records a transform regardless of PUT outcome (Gap 3)."""

    def test_succeeded_is_promoted_to_remediated(self):
        o = _outcome("PUT MeasureReport/a", "succeeded")
        process._record_remediation(o, 2, "pruned 2 mrp-2 stratum(s)")
        self.assertEqual(o.status, "remediated")
        self.assertEqual(o.remediations_applied, 2)
        self.assertIn("pruned 2 mrp-2 stratum(s)", o.detail)

    def test_failed_keeps_status_but_records_transform(self):
        # The core Gap 3 fix: a transform that ran but whose PUT failed on an independent
        # cause stays `failed` (urgent) yet is no longer invisible — the count + note stick.
        o = _outcome("PUT MeasureReport/b", "failed")
        o.detail = "HTTP 422: terminology-binding-error"
        process._record_remediation(o, 1, "pruned 1 mrp-2 stratum(s)")
        self.assertEqual(o.status, "failed")
        self.assertEqual(o.remediations_applied, 1)
        self.assertIn("pruned 1 mrp-2 stratum(s)", o.detail)
        self.assertIn("HTTP 422", o.detail)  # original failure detail preserved

    def test_zero_removed_is_a_noop(self):
        o = _outcome("PUT Patient/c", "succeeded")
        process._record_remediation(o, 0, "pruned 0 mrp-2 stratum(s)")
        self.assertEqual(o.status, "succeeded")
        self.assertEqual(o.remediations_applied, 0)
        self.assertEqual(o.detail, "")

    def test_accumulates_multiple_transforms(self):
        # A message Bundle can be touched by both the mrp-2 and trigger-code transforms.
        o = _outcome("PUT Bundle/d", "succeeded")
        process._record_remediation(o, 1, "pruned 1 mrp-2 stratum(s)")
        process._record_remediation(o, 1, "removed 1 empty trigger-code extension(s)")
        self.assertEqual(o.remediations_applied, 2)
        self.assertIn("mrp-2", o.detail)
        self.assertIn("trigger-code", o.detail)


class TransformedCounterTest(unittest.TestCase):
    """`transformed` surfaces applied transforms per-type and in totals (Gap 3)."""

    def _summary(self):
        # A MeasureReport transformed-and-stored (remediated) and one transformed-but-failed.
        stored = _outcome("PUT MeasureReport/a", "remediated")
        stored.remediations_applied = 1
        failed = _outcome("PUT MeasureReport/b", "failed")
        failed.remediations_applied = 1
        clean = _outcome("PUT Observation/c", "succeeded")
        s = process.RunSummary(read=2, submitted=3, succeeded=1, remediated=1, failed=1,
                               transformed=2)
        s.outcomes = [stored, failed, clean]
        return s

    def test_per_type_row_reports_transformed(self):
        with self.assertLogs("ecr-fhir-processor", level="INFO") as cap:
            process._report_summary(self._summary(), dry_run=False)
        mr_line = next(ln for ln in cap.output
                       if "MeasureReport" in ln and "submitted" in ln)
        # Both the remediated and the failed MeasureReport were transformed → transformed=2,
        # even though only one stored (remediated=1).
        self.assertIn("transformed=2", mr_line)
        self.assertIn("remediated=1", mr_line)
        self.assertIn("failed=1", mr_line)

    def test_totals_line_includes_transformed(self):
        with self.assertLogs("ecr-fhir-processor", level="INFO") as cap:
            process._report_summary(self._summary(), dry_run=False)
        totals = next(ln for ln in cap.output if "input-files" in ln)
        self.assertIn("transformed=2", totals)


if __name__ == "__main__":
    unittest.main()
