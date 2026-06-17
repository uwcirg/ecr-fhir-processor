"""Tests for the Patient ViewDefinition artifact and the publish/materialize step.

Covers:
- US1 (T007/T009): the checked-in ViewDefinition parses and carries required fields.
- US2 (T010): file discovery isolates malformed / id-less files (FR-008).
- US2 (T011): the $materialize Parameters body builder (research.md R3).
- US2 (T012): per-view outcome → exit-code aggregation (FR-008/FR-009).
- US3 (T020): discovery is resource-type-agnostic — a second file is processed with no
  code change (FR-011/SC-006).
"""

import json
import tempfile
import unittest
from pathlib import Path

import publish_views

REPO_ROOT = Path(__file__).resolve().parent.parent
VIEWDEFINITIONS_DIR = REPO_ROOT / "viewdefinitions"
PATIENT_VIEW = VIEWDEFINITIONS_DIR / "patient.ViewDefinition.json"

PROVENANCE_SYSTEM = "https://uwcirg.github.io/ecr-fhir-processor/CodeSystem/processed-by"
CMS_MEASURE_SYSTEM = "https://uwcirg.github.io/ecr-fhir-processor/CodeSystem/cms-measure"


def _all_view_files():
    """Every checked-in ViewDefinition file (sorted for stable subtest labels)."""
    return sorted(VIEWDEFINITIONS_DIR.glob("*.json"))


# --------------------------------------------------------------------------- #
# US1 (T007/T009): the checked-in Patient ViewDefinition artifact
# --------------------------------------------------------------------------- #


class PatientViewDefinitionFileTest(unittest.TestCase):
    def setUp(self):
        with PATIENT_VIEW.open(encoding="utf-8") as fh:
            self.view = json.load(fh)

    def test_parses_as_json(self):
        self.assertIsInstance(self.view, dict)

    def test_required_fields_present(self):
        self.assertEqual(self.view["resourceType"], "ViewDefinition")
        self.assertEqual(self.view["resource"], "Patient")
        self.assertTrue(self.view["id"])
        self.assertTrue(self.view["name"])
        self.assertIn(self.view["status"], {"active", "draft"})

    def test_select_has_non_empty_column_array(self):
        select = self.view["select"]
        self.assertIsInstance(select, list)
        self.assertTrue(select)
        columns = select[0]["column"]
        self.assertIsInstance(columns, list)
        self.assertTrue(columns)

    def test_default_doh_columns_present(self):
        columns = {c["name"] for c in self.view["select"][0]["column"]}
        expected = {
            "id", "mrn", "name_family", "name_given", "gender", "birth_date",
            "deceased", "race_code", "race_display", "ethnicity_code",
            "ethnicity_display", "address_city", "address_state", "address_postal_code",
            "cms_measure",
        }
        self.assertEqual(columns, expected)

    def test_cms_measure_column_present_and_wellformed(self):
        # 003 US1 (contract VC-1/VC-2): a cms_measure column reads the cms-measure tag's
        # code via the project CMS-measure CodeSystem and reduces to one value per patient.
        by_name = {c["name"]: c for c in self.view["select"][0]["column"]}
        self.assertIn("cms_measure", by_name)
        col = by_name["cms_measure"]
        self.assertEqual(col["type"], "code")
        self.assertIn(
            "https://uwcirg.github.io/ecr-fhir-processor/CodeSystem/cms-measure",
            col["path"])
        # VC-2: single-valued reducer, no row-multiplying forEach.
        self.assertTrue(col["path"].rstrip().endswith(".code.first()"))

    def test_no_row_multiplying_foreach(self):
        # One row per Patient: the top-level select must not use forEach (research.md R6).
        for entry in self.view["select"]:
            self.assertNotIn("forEach", entry)
            self.assertNotIn("forEachOrNull", entry)

    def test_provenance_where_filter_present(self):
        # FR-013 / research.md R7: the view must filter to Patients persisted by this
        # project's processor, via the feature-001 provenance tag.
        where = self.view.get("where")
        self.assertIsInstance(where, list)
        self.assertTrue(where)
        paths = " ".join(w.get("path", "") for w in where)
        self.assertIn(
            "https://uwcirg.github.io/ecr-fhir-processor/CodeSystem/processed-by", paths)
        self.assertIn("ecr-fhir-processor", paths)
        self.assertIn("meta.tag", paths)
        # Version-agnostic: must not pin to processed-on or a version.
        self.assertNotIn("processed-on", paths)


# --------------------------------------------------------------------------- #
# US2 (T010): ViewDefinition file discovery + per-file isolation (FR-008)
# --------------------------------------------------------------------------- #


def _write(directory, filename, content):
    path = Path(directory) / filename
    if isinstance(content, str):
        path.write_text(content, encoding="utf-8")
    else:
        path.write_text(json.dumps(content), encoding="utf-8")
    return path


class DiscoveryTest(unittest.TestCase):
    def test_finds_well_formed_viewdefinition(self):
        with tempfile.TemporaryDirectory() as d:
            _write(d, "patient.ViewDefinition.json",
                   {"resourceType": "ViewDefinition", "id": "patient", "name": "patient_view"})
            units, failures = publish_views.discover_viewdefinitions(d)
            self.assertEqual([u.view_id for u in units], ["patient"])
            self.assertEqual(failures, [])

    def test_malformed_json_fails_only_that_file(self):
        with tempfile.TemporaryDirectory() as d:
            _write(d, "good.json",
                   {"resourceType": "ViewDefinition", "id": "patient"})
            _write(d, "broken.json", "{ this is not json")
            units, failures = publish_views.discover_viewdefinitions(d)
            self.assertEqual([u.view_id for u in units], ["patient"])
            self.assertEqual(len(failures), 1)
            self.assertEqual(failures[0].filename, "broken.json")
            self.assertEqual(failures[0].status, "failed")

    def test_idless_file_fails_only_that_file(self):
        with tempfile.TemporaryDirectory() as d:
            _write(d, "good.json",
                   {"resourceType": "ViewDefinition", "id": "patient"})
            _write(d, "noid.json", {"resourceType": "ViewDefinition", "name": "x"})
            units, failures = publish_views.discover_viewdefinitions(d)
            self.assertEqual([u.view_id for u in units], ["patient"])
            self.assertEqual(len(failures), 1)
            self.assertEqual(failures[0].filename, "noid.json")
            self.assertIn("id", failures[0].detail)

    def test_non_viewdefinition_resource_fails_that_file(self):
        with tempfile.TemporaryDirectory() as d:
            _write(d, "patient.json", {"resourceType": "Patient", "id": "p1"})
            units, failures = publish_views.discover_viewdefinitions(d)
            self.assertEqual(units, [])
            self.assertEqual(len(failures), 1)

    def test_does_not_raise_on_bad_files(self):
        with tempfile.TemporaryDirectory() as d:
            _write(d, "broken.json", "{not json")
            _write(d, "noid.json", {"resourceType": "ViewDefinition"})
            try:
                units, failures = publish_views.discover_viewdefinitions(d)
            except Exception as exc:  # noqa: BLE001
                self.fail(f"discovery raised on bad files: {exc}")
            self.assertEqual(units, [])
            self.assertEqual(len(failures), 2)


# --------------------------------------------------------------------------- #
# US2 (T011): $materialize Parameters body builder (research.md R3)
# --------------------------------------------------------------------------- #


class MaterializeBodyTest(unittest.TestCase):
    def test_default_type_is_view(self):
        body = publish_views.build_materialize_body()
        self.assertEqual(body, {
            "resourceType": "Parameters",
            "parameter": [{"name": "type", "valueCode": "view"}],
        })

    def test_explicit_type_honored(self):
        body = publish_views.build_materialize_body("materialized-view")
        self.assertEqual(body["parameter"][0]["valueCode"], "materialized-view")


# --------------------------------------------------------------------------- #
# US2 (T012): outcome → exit-code aggregation (FR-008/FR-009)
# --------------------------------------------------------------------------- #


class ExitCodeAggregationTest(unittest.TestCase):
    def _ok(self, vid="patient"):
        return publish_views.ViewOutcome(vid, "ok", "HTTP 200", "ok", "sof.patient_view (view)")

    def test_all_ok_exits_zero(self):
        summary = publish_views.summarize_view_outcomes([self._ok(), self._ok("v2")])
        self.assertEqual(summary.exit_code, 0)

    def test_publish_failure_exits_nonzero_and_materialize_skipped(self):
        vo = publish_views.ViewOutcome("bad", "failed", "HTTP 422", "skipped", "publish failed")
        summary = publish_views.summarize_view_outcomes([self._ok(), vo])
        self.assertNotEqual(summary.exit_code, 0)
        # materialize is recorded as skipped (not failed) when publish failed.
        mat = [o for o in summary.outcomes if o.action.startswith("$materialize") and o.filename == "bad"]
        self.assertEqual(mat[0].status, "skipped")

    def test_materialize_failure_exits_nonzero(self):
        vo = publish_views.ViewOutcome("v", "ok", "HTTP 200", "failed", "HTTP 400: bad path")
        summary = publish_views.summarize_view_outcomes([vo])
        self.assertNotEqual(summary.exit_code, 0)

    def test_discovery_failure_exits_nonzero(self):
        from fhir_common import FileOutcome
        failure = FileOutcome("broken.json", "viewdefinition", "discover", 0, "failed", "bad")
        summary = publish_views.summarize_view_outcomes([self._ok()], [failure])
        self.assertNotEqual(summary.exit_code, 0)


# --------------------------------------------------------------------------- #
# US3 (T020): generalization — a second file is processed with no code change
# --------------------------------------------------------------------------- #


class GeneralizationTest(unittest.TestCase):
    def test_two_views_both_discovered(self):
        with tempfile.TemporaryDirectory() as d:
            # Copy the real Patient view in alongside a second minimal ViewDefinition.
            with PATIENT_VIEW.open(encoding="utf-8") as fh:
                _write(d, "patient.ViewDefinition.json", json.load(fh))
            _write(d, "encounter.ViewDefinition.json",
                   {"resourceType": "ViewDefinition", "id": "encounter",
                    "name": "encounter_view", "status": "active", "resource": "Encounter",
                    "select": [{"column": [{"name": "id", "path": "getResourceKey()"}]}]})
            units, failures = publish_views.discover_viewdefinitions(d)
            self.assertEqual(sorted(u.view_id for u in units), ["encounter", "patient"])
            self.assertEqual(failures, [])


# --------------------------------------------------------------------------- #
# US1 (T014): generic, directory-driven shape suite over EVERY view file
# --------------------------------------------------------------------------- #


class AllViewDefinitionsShapeTest(unittest.TestCase):
    """Shape assertions applied to every viewdefinitions/*.json (research.md R8).

    Driven generically over the directory so a newly added view file is covered
    with no new test. Covers the eleven new views (004) plus Patient (002/003).
    """

    def setUp(self):
        self.files = _all_view_files()

    def test_directory_has_view_files(self):
        # Guard: the glob must actually find the checked-in views.
        self.assertTrue(self.files, "no ViewDefinition files discovered")

    def test_every_file_parses_as_json(self):
        for path in self.files:
            with self.subTest(view=path.name):
                with path.open(encoding="utf-8") as fh:
                    view = json.load(fh)
                self.assertIsInstance(view, dict)

    def test_every_file_has_required_fields(self):
        for path in self.files:
            with self.subTest(view=path.name):
                with path.open(encoding="utf-8") as fh:
                    view = json.load(fh)
                self.assertEqual(view.get("resourceType"), "ViewDefinition")
                self.assertTrue(view.get("id"))
                self.assertTrue(view.get("name"))
                self.assertIn(view.get("status"), {"active", "draft"})
                self.assertTrue(view.get("resource"))

    def test_every_file_has_non_empty_select_columns(self):
        for path in self.files:
            with self.subTest(view=path.name):
                with path.open(encoding="utf-8") as fh:
                    view = json.load(fh)
                select = view.get("select")
                self.assertIsInstance(select, list)
                self.assertTrue(select)
                columns = select[0].get("column")
                self.assertIsInstance(columns, list)
                self.assertTrue(columns)

    def test_every_file_has_resource_key_id_column(self):
        for path in self.files:
            with self.subTest(view=path.name):
                with path.open(encoding="utf-8") as fh:
                    view = json.load(fh)
                by_name = {c["name"]: c for c in view["select"][0]["column"]}
                self.assertIn("id", by_name)
                self.assertEqual(by_name["id"]["path"], "getResourceKey()")

    def test_no_row_multiplying_foreach(self):
        # One row per resource: no forEach / forEachOrNull anywhere in select (research.md R3).
        for path in self.files:
            with self.subTest(view=path.name):
                with path.open(encoding="utf-8") as fh:
                    view = json.load(fh)
                for entry in view["select"]:
                    self.assertNotIn("forEach", entry)
                    self.assertNotIn("forEachOrNull", entry)


# --------------------------------------------------------------------------- #
# US3 (T021): provenance + cms_measure scoping uniform across EVERY view file
# --------------------------------------------------------------------------- #


class AllViewDefinitionsScopingTest(unittest.TestCase):
    """FR-005/FR-006: every view scopes to processor-persisted resources and exposes
    a single-valued cms_measure column — the same scoping the Patient view has."""

    def setUp(self):
        self.files = _all_view_files()

    def test_every_file_has_provenance_where_filter(self):
        for path in self.files:
            with self.subTest(view=path.name):
                with path.open(encoding="utf-8") as fh:
                    view = json.load(fh)
                where = view.get("where")
                self.assertIsInstance(where, list)
                self.assertTrue(where)
                paths = " ".join(w.get("path", "") for w in where)
                self.assertIn(PROVENANCE_SYSTEM, paths)
                self.assertIn("ecr-fhir-processor", paths)
                self.assertIn("meta.tag", paths)
                # Version-agnostic: must not pin to processed-on or a version.
                self.assertNotIn("processed-on", paths)

    def test_every_file_has_single_valued_cms_measure_column(self):
        for path in self.files:
            with self.subTest(view=path.name):
                with path.open(encoding="utf-8") as fh:
                    view = json.load(fh)
                by_name = {c["name"]: c for c in view["select"][0]["column"]}
                self.assertIn("cms_measure", by_name)
                col = by_name["cms_measure"]
                self.assertEqual(col["type"], "code")
                self.assertIn(CMS_MEASURE_SYSTEM, col["path"])
                # Single-valued reducer, no row-multiplying forEach.
                self.assertTrue(col["path"].rstrip().endswith(".code.first()"))


if __name__ == "__main__":
    unittest.main()
