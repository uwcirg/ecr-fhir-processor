"""T042 (deterministic half of SC-008/SC-011): re-runs are idempotent (v1.1.0 model).

The full SC-008 check — "server resource count identical after run 2" — requires a live
FHIR server (quickstart Scenario D) and is not run here. This test verifies the
deterministic guarantees that make SC-008/SC-011 hold under the independent per-resource
PUT model: re-processing the same input plans the same per-resource PUT targets, never
accumulates provenance tags, and a ``--only-types``/``--skip-types`` split leaves the
already-persisted resources' clinical content untouched.
"""

import json
import tempfile
import unittest
from pathlib import Path

import process
from tests import REPO_ROOT

FIXTURE = (REPO_ROOT / "test" / "input" / "controllable-bp" / "standard"
           / "CMS165_bulk_dial_high_00042" / "CMS165_bulk_dial_high_00042.json")


def _dry_pipeline(output_dir, version, type_filter=None):
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
        type_filter=type_filter or process.TypeFilter(),
    )


def _process_once(output_dir, version, type_filter=None):
    data = json.loads(FIXTURE.read_text())
    pipe = _dry_pipeline(output_dir, version, type_filter)
    pipe.process(data, process.KIND_COLLECTION, FIXTURE.name, "controllable-bp")
    mirrored = next(Path(output_dir).rglob(FIXTURE.name))
    return json.loads(mirrored.read_text())


def _put_targets(bundle):
    # Per-resource PUT targets come from the planner — no transaction Bundle (D2).
    return sorted(u.url for u in process.plan_collection_puts(bundle))


def _clinical(bundle):
    # Identity is clinical content (meta excluded — provenance/server-managed vary).
    return sorted(
        json.dumps({k: v for k, v in e["resource"].items() if k != "meta"},
                   sort_keys=True)
        for e in bundle["entry"]
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
            # Feed run1's already-stamped output back through a second run; the mirror is
            # overwritten in place, so re-read it to inspect the re-stamped result.
            pipe = _dry_pipeline(d1, "v2")
            pipe.process(run1, process.KIND_COLLECTION, FIXTURE.name, "controllable-bp")
            restamped = json.loads(next(Path(d1).rglob(FIXTURE.name)).read_text())
            for entry in restamped["entry"]:
                own = [t for t in entry["resource"]["meta"]["tag"]
                       if t["system"] in process.OWN_TAG_SYSTEMS]
                self.assertEqual(len(own), 3)

    def test_deferred_type_split_leaves_clinical_content_untouched(self):
        # A --skip-types run then an --only-types run land disjoint resource sets; neither
        # alters the other's clinical content (FR-022/FR-023 — no rollback, no rewrite).
        with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
            skip = _process_once(d1, "v1",
                                 process.build_type_filter(None, "Observation"))
            only = _process_once(d2, "v1",
                                 process.build_type_filter("Observation", None))
            # The mirror is the full stamped bundle in both runs; the clinical content of
            # every resource is identical regardless of which run would actually PUT it.
            self.assertEqual(_clinical(skip), _clinical(only))


if __name__ == "__main__":
    unittest.main()
