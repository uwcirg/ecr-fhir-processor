"""Three-state storability exit code + deferral mechanism (contracts/run-accounting.md).

The run distinguishes all-stored (incl. remediated) → 0, completed-with-deferrals, and
unexpected-error, with unexpected error dominating a deferral (precedence). The `deferred`
outcome is produced by an isolation mechanism (never fabrication, FR-007).
"""

import unittest

import process
from fhir_common import (
    EXIT_COMPLETED_WITH_DEFERRALS,
    EXIT_SUCCESS,
    EXIT_UNEXPECTED_ERROR,
)


def _summary(**counts):
    return process.RunSummary(**counts)


class ExitCodeStateMachineTest(unittest.TestCase):
    def test_all_stored_including_remediated_is_success(self):
        # remediated never changes the code — a fully-remediated-and-stored run exits 0.
        self.assertEqual(_summary(succeeded=5, remediated=3).exit_code, EXIT_SUCCESS)

    def test_deferral_without_failure_is_deferrals_code(self):
        s = _summary(succeeded=4, remediated=1, deferred=2)
        self.assertEqual(s.exit_code, EXIT_COMPLETED_WITH_DEFERRALS)
        self.assertNotEqual(s.exit_code, EXIT_UNEXPECTED_ERROR)  # distinct value

    def test_unexpected_failure_is_error_code(self):
        self.assertEqual(_summary(succeeded=4, failed=1).exit_code, EXIT_UNEXPECTED_ERROR)

    def test_failure_dominates_deferral_precedence(self):
        # An unexpected failure alongside a deferral still exits with the error code.
        s = _summary(succeeded=1, deferred=2, failed=1)
        self.assertEqual(s.exit_code, EXIT_UNEXPECTED_ERROR)

    def test_exit_constants_are_distinct(self):
        vals = {EXIT_SUCCESS, EXIT_UNEXPECTED_ERROR, EXIT_COMPLETED_WITH_DEFERRALS}
        self.assertEqual(len(vals), 3)
        self.assertEqual(EXIT_SUCCESS, 0)  # backward-compatible success value


class DeferralMechanismTest(unittest.TestCase):
    """The Pipeline can isolate a resource type as `deferred` (not submitted) rather than
    fabricate content — the mechanism that yields EXIT_COMPLETED_WITH_DEFERRALS (FR-007)."""

    def _pipeline(self, deferrals):
        return process.Pipeline(
            config=process.RunConfig(software={}, server={}, ig_versions={},
                                     paths=dict(process.DEFAULT_PATHS), raw={}),
            version="v1",
            timestamp=process.processing_timestamp(),
            run_date="2026-07-02",
            dry_run=True,
            output_dir="/tmp/unused",
            write_mirror=False,
            client=None,
            deferrals=frozenset(deferrals),
        )

    def test_deferred_type_is_isolated_not_submitted(self):
        pipe = self._pipeline({"Observation"})
        outcome = pipe._put(process.KIND_COLLECTION, "Observation", "x",
                            {"resourceType": "Observation", "id": "x"}, "f.json")
        self.assertEqual(outcome.status, "deferred")

    def test_non_deferred_type_still_processed(self):
        pipe = self._pipeline({"Observation"})
        outcome = pipe._put(process.KIND_COLLECTION, "Patient", "p",
                            {"resourceType": "Patient", "id": "p"}, "f.json")
        self.assertEqual(outcome.status, "succeeded")  # dry-run stores everything else


if __name__ == "__main__":
    unittest.main()
