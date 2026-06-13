"""T028 [US4]: TypeFilter selection (FR-023, D10, cli contract).

``--only-types`` keeps only the listed FHIR resourceTypes; ``--skip-types`` excludes them;
the ``measure-report`` kind alias is accepted; the two flags are mutually exclusive.
Excluded resources are counted ``skipped`` (verified end-to-end via the pipeline).
"""

import unittest

import process


class TypeFilterTest(unittest.TestCase):
    def test_default_allows_everything(self):
        tf = process.build_type_filter(None, None)
        self.assertTrue(tf.allows("Patient"))
        self.assertTrue(tf.allows("MeasureReport"))

    def test_only_types_keeps_only_listed(self):
        tf = process.build_type_filter("MeasureReport", None)
        self.assertTrue(tf.allows("MeasureReport"))
        self.assertFalse(tf.allows("Patient"))

    def test_skip_types_excludes_listed(self):
        tf = process.build_type_filter(None, "MeasureReport,Observation")
        self.assertFalse(tf.allows("MeasureReport"))
        self.assertFalse(tf.allows("Observation"))
        self.assertTrue(tf.allows("Patient"))

    def test_measure_report_alias_accepted(self):
        tf = process.build_type_filter(None, "measure-report")
        self.assertFalse(tf.allows("MeasureReport"))
        tf_only = process.build_type_filter("measure-report", None)
        self.assertTrue(tf_only.allows("MeasureReport"))
        self.assertFalse(tf_only.allows("Patient"))

    def test_whitespace_tolerated(self):
        tf = process.build_type_filter(None, " Patient , Observation ")
        self.assertFalse(tf.allows("Patient"))
        self.assertFalse(tf.allows("Observation"))

    def test_mutually_exclusive(self):
        with self.assertRaises(ValueError):
            process.build_type_filter("Patient", "Observation")

    def test_excluded_resource_counted_skipped_in_pipeline(self):
        pipe = process.Pipeline(
            config=process.RunConfig(software={}, server={}, ig_versions={},
                                     paths=dict(process.DEFAULT_PATHS), raw={}),
            version="v1",
            timestamp=process.processing_timestamp(),
            run_date="2026-06-12",
            dry_run=True,
            output_dir="/tmp/unused",
            write_mirror=False,
            client=None,
            type_filter=process.build_type_filter(None, "MeasureReport"),
        )
        outcomes = pipe.process({"resourceType": "MeasureReport", "id": "m1"},
                                process.KIND_MEASURE_REPORT, "MeasureReport_m1.json", "m")
        self.assertEqual(len(outcomes), 1)
        self.assertEqual(outcomes[0].status, "skipped")


if __name__ == "__main__":
    unittest.main()
