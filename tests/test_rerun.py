"""T037 (deterministic half of SC-008): re-running identical input is idempotent.

The full SC-008 check — "server resource count identical after run 2" — requires a live
FHIR server (quickstart Scenario D) and is not run here. This test verifies the
deterministic guarantees that make SC-008 hold: re-processing the same input produces the
same PUT targets and the same clinical content, and provenance tags never accumulate.
"""

import json
import tempfile
import unittest
from pathlib import Path

import process
from tests import REPO_ROOT

FIXTURE = (REPO_ROOT / "test" / "input" / "controllable-bp" / "standard"
           / "CMS165_bulk_dial_high_00042" / "CMS165_bulk_dial_high_00042.json")


def _dry_pipeline(output_dir, version):
    return process.Pipeline(
        config=process.RunConfig(software={}, server={}, ig_versions={},
                                 paths=dict(process.DEFAULT_PATHS), raw={}),
        version=version,
        timestamp=process.processing_timestamp(),
        run_date="2026-06-09",
        dry_run=True,
        output_dir=output_dir,
        write_mirror=True,
        client=None,
    )


def _process_once(output_dir, version):
    data = json.loads(FIXTURE.read_text())
    pipe = _dry_pipeline(output_dir, version)
    pipe.process(data, process.KIND_COLLECTION, FIXTURE.name, "controllable-bp")
    mirrored = next(Path(output_dir).rglob(FIXTURE.name))
    return json.loads(mirrored.read_text())


def _put_targets(txn):
    return sorted(e["request"]["url"] for e in txn["entry"])


def _clinical(txn):
    # Identity is clinical content (meta excluded — provenance/server-managed vary).
    return sorted(
        json.dumps({k: v for k, v in e["resource"].items() if k != "meta"},
                   sort_keys=True)
        for e in txn["entry"]
    )


class ReRunIdempotencyTest(unittest.TestCase):
    def test_same_put_targets_and_clinical_content_across_runs(self):
        with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
            run1 = _process_once(d1, "v1")
            run2 = _process_once(d2, "v2")  # different version → only provenance differs
            self.assertEqual(_put_targets(run1), _put_targets(run2))
            self.assertEqual(_clinical(run1), _clinical(run2))

    def test_provenance_tags_do_not_accumulate_on_restamp(self):
        with tempfile.TemporaryDirectory() as d1:
            run1 = _process_once(d1, "v1")
            # Feed run1's already-stamped output back through a second run; the mirror
            # is overwritten in place, so re-read it to inspect the re-stamped result.
            pipe = _dry_pipeline(d1, "v2")
            pipe.process(run1, process.KIND_COLLECTION, FIXTURE.name, "controllable-bp")
            restamped = json.loads(next(Path(d1).rglob(FIXTURE.name)).read_text())
            for entry in restamped["entry"]:
                own = [t for t in entry["resource"]["meta"]["tag"]
                       if t["system"] in process.OWN_TAG_SYSTEMS]
                self.assertEqual(len(own), 3)


if __name__ == "__main__":
    unittest.main()
