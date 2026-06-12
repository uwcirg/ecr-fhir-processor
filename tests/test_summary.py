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
        self.assertIn("resources by type:", text)
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


if __name__ == "__main__":
    unittest.main()
