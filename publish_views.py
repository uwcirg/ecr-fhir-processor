#!/usr/bin/env python3
"""publish_views.py — publish every checked-in SQL-on-FHIR ViewDefinition to the target
Aidbox server and materialize it.

For each ``*.json`` ViewDefinition discovered under ``--viewdefinitions-dir`` this step
``PUT``s the resource to ``{base}/ViewDefinition/{id}`` (update-in-place) and then
``POST``s ``{base}/ViewDefinition/{id}/$materialize``. Publish and materialize outcomes
are reported separately per view; one view's failure never blocks another; any publish or
materialize failure is reflected in a non-zero exit status.

Separate entry point from ``process.py`` (different trigger — research.md R4); the OAuth2
FHIR client, config loader/validator, logging, and per-item outcome model are imported
from the shared ``fhir_common.py`` (research.md R1). Python 3 standard library only.

See specs/002-patient-viewdefinition/ for the spec, plan, contracts, and quickstart.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from fhir_common import (
    FhirClient,
    FileOutcome,
    RunConfig,
    RunSummary,
    SubmissionError,
    load_config,
    logger,
    setup_logging,
    validate_config,
)

#: Materialization types Aidbox's $materialize accepts (research.md R3).
MATERIALIZE_TYPES = ("view", "materialized-view", "table")

#: Default materialization type — an always-current SQL view (research.md R3).
DEFAULT_MATERIALIZE_TYPE = "view"


# --------------------------------------------------------------------------- #
# Discovered work unit (data-model.md §2)
# --------------------------------------------------------------------------- #


@dataclass
class ViewDefinitionFile:
    """A discovered, well-formed ViewDefinition file ready to publish/materialize."""

    path: Path
    resource: dict
    view_id: str
    name: str | None = None


@dataclass
class ViewOutcome:
    """Per-view run record; publish and materialize reported separately (FR-009)."""

    view_id: str
    publish_status: str  # ok | failed
    publish_detail: str = ""
    materialize_status: str = "skipped"  # ok | failed | skipped
    materialize_detail: str = ""


# --------------------------------------------------------------------------- #
# CLI (contracts/publish-materialize-cli.md)
# --------------------------------------------------------------------------- #


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="publish_views.py",
        description="Publish and materialize checked-in SQL-on-FHIR ViewDefinitions.",
    )
    p.add_argument("--config", default="config.json",
                   help="Path to the run config (template: config.example.json).")
    p.add_argument("--viewdefinitions-dir", default="viewdefinitions",
                   help="Directory scanned for *.json ViewDefinition files.")
    p.add_argument("--materialize-type", default=None, choices=MATERIALIZE_TYPES,
                   help="$materialize type (default: server.materialize_type, else "
                        f"'{DEFAULT_MATERIALIZE_TYPE}').")
    p.add_argument("--dry-run", action="store_true",
                   help="Discover + validate files and report planned calls; no network.")
    p.add_argument("--verbose", action="store_true",
                   help="Console DEBUG verbosity (the file log is always detailed).")
    p.add_argument("--log-dir", default=None,
                   help="Audit-log directory (default: config.paths.log_dir, else 'log').")
    return p


# --------------------------------------------------------------------------- #
# Discovery (T016; FR-011, data-model §2)
# --------------------------------------------------------------------------- #


def discover_viewdefinitions(
    directory: str,
) -> tuple[list[ViewDefinitionFile], list[FileOutcome]]:
    """Scan ``directory`` for ``*.json`` ViewDefinition files (FR-011).

    Returns ``(units, failures)``: every well-formed ViewDefinition (``resourceType ==
    "ViewDefinition"`` with an ``id``) becomes a processable unit; a malformed-JSON,
    wrong-type, or id-less file fails *that file* — recorded as a failed
    :class:`FileOutcome` (reflected in exit status) without raising or blocking the rest
    (FR-008). Adding a new ViewDefinition file needs no code change (Story 3).
    """
    units: list[ViewDefinitionFile] = []
    failures: list[FileOutcome] = []
    dir_path = Path(directory)
    if not dir_path.exists():
        return units, failures

    for path in sorted(dir_path.glob("*.json")):
        filename = path.name
        try:
            with path.open(encoding="utf-8") as fh:
                resource = json.load(fh)
        except (json.JSONDecodeError, OSError) as exc:
            failures.append(FileOutcome(filename, "viewdefinition", "discover", 0,
                                        "failed", f"unreadable/malformed JSON: {exc}"))
            continue
        if not isinstance(resource, dict) or resource.get("resourceType") != "ViewDefinition":
            failures.append(FileOutcome(filename, "viewdefinition", "discover", 0,
                                        "failed", "not a ViewDefinition resource"))
            continue
        view_id = resource.get("id")
        if not view_id:
            failures.append(FileOutcome(filename, "viewdefinition", "discover", 0,
                                        "failed", "ViewDefinition is missing required 'id'"))
            continue
        units.append(ViewDefinitionFile(path=path, resource=resource, view_id=view_id,
                                        name=resource.get("name")))
    return units, failures


# --------------------------------------------------------------------------- #
# $materialize body builder (T017; research.md R3)
# --------------------------------------------------------------------------- #


def build_materialize_body(materialize_type: str = DEFAULT_MATERIALIZE_TYPE) -> dict:
    """Build the FHIR ``Parameters`` body for ``$materialize`` (single ``type`` param)."""
    return {
        "resourceType": "Parameters",
        "parameter": [{"name": "type", "valueCode": materialize_type}],
    }


def _parameter_value(parameters: dict, name: str) -> str | None:
    """Pull a named parameter's value out of a FHIR ``Parameters`` response, if present."""
    for param in parameters.get("parameter", []) or []:
        if param.get("name") == name:
            for key, value in param.items():
                if key.startswith("value"):
                    return value
    return None


def _operation_outcome_reason(response: dict) -> str:
    """Best-effort human reason from a server ``OperationOutcome`` (FR-008)."""
    issues = response.get("issue") if isinstance(response, dict) else None
    if isinstance(issues, list) and issues:
        reasons = [i.get("diagnostics") or i.get("details", {}).get("text") or i.get("code")
                   for i in issues]
        reasons = [r for r in reasons if r]
        if reasons:
            return "; ".join(str(r) for r in reasons)
    return json.dumps(response)


# --------------------------------------------------------------------------- #
# Per-view publish + materialize flow (T018; contracts §"Server operations")
# --------------------------------------------------------------------------- #


def publish_and_materialize(
    client: FhirClient | None,
    unit: ViewDefinitionFile,
    materialize_type: str,
    dry_run: bool,
) -> ViewOutcome:
    """PUT the ViewDefinition then POST ``$materialize``; isolate per-view failure.

    On publish failure, materialize is **skipped** for this view (FR-008). The two
    operations are recorded separately (FR-009). Never raises for a server/network
    failure — it is captured in the returned :class:`ViewOutcome`.
    """
    view_id = unit.view_id

    if dry_run:
        logger.info("[dry-run] would PUT ViewDefinition/%s then POST "
                    "ViewDefinition/%s/$materialize {type=%s} (%s).",
                    view_id, view_id, materialize_type, unit.path.name)
        return ViewOutcome(view_id, "ok", "dry-run", "ok", f"dry-run ({materialize_type})")

    # 1. Publish (update-in-place).
    publish_url = f"{client.base}/ViewDefinition/{view_id}"
    try:
        status, response = client.request("PUT", publish_url, body=unit.resource)
    except SubmissionError as exc:
        logger.error("Publish FAILED for ViewDefinition/%s (%s): %s",
                     view_id, unit.path.name, exc)
        return ViewOutcome(view_id, "failed", str(exc),
                           "skipped", "publish failed")
    if not 200 <= status < 300:
        reason = f"HTTP {status}: {_operation_outcome_reason(response)}"
        logger.error("Publish REJECTED for ViewDefinition/%s (%s): %s",
                     view_id, unit.path.name, reason)
        return ViewOutcome(view_id, "failed", reason, "skipped", "publish failed")
    logger.info("Publish OK for ViewDefinition/%s (HTTP %d).", view_id, status)
    publish_detail = f"HTTP {status}"

    # 2. Materialize.
    materialize_url = f"{client.base}/ViewDefinition/{view_id}/$materialize"
    body = build_materialize_body(materialize_type)
    try:
        status, response = client.request("POST", materialize_url, body=body)
    except SubmissionError as exc:
        logger.error("Materialize FAILED for ViewDefinition/%s (%s): %s",
                     view_id, unit.path.name, exc)
        return ViewOutcome(view_id, "ok", publish_detail, "failed", str(exc))
    if not 200 <= status < 300:
        reason = f"HTTP {status}: {_operation_outcome_reason(response)}"
        logger.error("Materialize REJECTED for ViewDefinition/%s (%s): %s",
                     view_id, unit.path.name, reason)
        return ViewOutcome(view_id, "ok", publish_detail, "failed", reason)

    view_name = _parameter_value(response, "viewName") or view_id
    view_type = _parameter_value(response, "viewType") or materialize_type
    logger.info("Materialize OK for ViewDefinition/%s -> %s (%s).",
                view_id, view_name, view_type)
    return ViewOutcome(view_id, "ok", publish_detail, "ok",
                       f"{view_name} ({view_type})")


# --------------------------------------------------------------------------- #
# Outcome → exit-code aggregation (T019; FR-008/FR-009, mirrors RunSummary)
# --------------------------------------------------------------------------- #


def summarize_view_outcomes(
    view_outcomes: list[ViewOutcome],
    discovery_failures: list[FileOutcome] | None = None,
) -> RunSummary:
    """Fold per-view outcomes into a :class:`RunSummary` (reuses FileOutcome/exit_code).

    Publish and materialize each become their own :class:`FileOutcome`, so the summary's
    ``exit_code`` is ``0`` iff every view both published and materialized (any publish or
    materialize failure → non-zero). A materialize ``skipped`` (because publish failed) is
    not itself counted a failure — the publish failure already drives the non-zero exit.
    Discovery failures (malformed/id-less files) are folded in as failures too (FR-008).
    """
    summary = RunSummary()
    for failure in discovery_failures or []:
        summary.record(failure)
        summary.failed += 1
    for vo in view_outcomes:
        summary.record(FileOutcome(vo.view_id, "viewdefinition",
                                   f"PUT ViewDefinition/{vo.view_id}", 1,
                                   "succeeded" if vo.publish_status == "ok" else "failed",
                                   vo.publish_detail, resource_type="ViewDefinition"))
        mat_status = {"ok": "succeeded", "failed": "failed", "skipped": "skipped"}[
            vo.materialize_status]
        summary.record(FileOutcome(vo.view_id, "viewdefinition",
                                   f"$materialize ViewDefinition/{vo.view_id}", 1,
                                   mat_status, vo.materialize_detail,
                                   resource_type="ViewDefinition"))
        if vo.publish_status != "ok":
            summary.failed += 1
        if vo.materialize_status == "failed":
            summary.failed += 1
        if vo.publish_status == "ok" and vo.materialize_status == "ok":
            summary.succeeded += 1
    return summary


def _report(view_outcomes: list[ViewOutcome], discovery_failures: list[FileOutcome],
            dry_run: bool) -> None:
    """Print the per-view summary + roll-up line (FR-009, quickstart §2)."""
    logger.info("=" * 60)
    logger.info("Publish/Materialize summary%s", " [DRY-RUN]" if dry_run else "")
    for failure in discovery_failures:
        logger.info("  DISCOVERY FAILED: %s — %s", failure.filename, failure.detail)
    for vo in view_outcomes:
        logger.info("ViewDefinition: %s", vo.view_id)
        logger.info("  publish:     %s%s", vo.publish_status.upper(),
                    f" ({vo.publish_detail})" if vo.publish_detail else "")
        logger.info("  materialize: %s%s", vo.materialize_status.upper(),
                    f"  -> {vo.materialize_detail}" if vo.materialize_detail else "")
    published = sum(1 for vo in view_outcomes if vo.publish_status == "ok")
    materialized = sum(1 for vo in view_outcomes if vo.materialize_status == "ok")
    failed = (len(discovery_failures)
              + sum(1 for vo in view_outcomes
                    if vo.publish_status != "ok" or vo.materialize_status == "failed"))
    total = len(view_outcomes) + len(discovery_failures)
    logger.info("-" * 60)
    logger.info("--- %d view%s: %d published, %d materialized, %d failed ---",
                total, "" if total == 1 else "s", published, materialized, failed)
    logger.info("=" * 60)


# --------------------------------------------------------------------------- #
# Run orchestration
# --------------------------------------------------------------------------- #


def _resolve_materialize_type(arg: str | None, config: RunConfig) -> str:
    """CLI flag wins, then config.server.materialize_type, else the 'view' default."""
    if arg:
        return arg
    configured = (config.server or {}).get("materialize_type")
    if configured:
        return configured
    return DEFAULT_MATERIALIZE_TYPE


def run(args: argparse.Namespace) -> int:
    """Top-level run: load+validate config, discover, publish+materialize, summarize."""
    try:
        config = load_config(args.config)
    except FileNotFoundError as exc:
        if args.dry_run:
            config = RunConfig(software={}, server={}, ig_versions={},
                               paths={}, raw={})
        else:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    log_dir = args.log_dir or (config.paths or {}).get("log_dir") or "log"
    setup_logging(log_dir, args.verbose, prefix="publish-views")

    # Fail loudly before any network call when required server.* is missing/placeholder.
    config_errors = validate_config(config, args.dry_run)
    if config_errors:
        for err in config_errors:
            logger.error(err)
        return 1

    materialize_type = _resolve_materialize_type(args.materialize_type, config)
    logger.info("publish_views materialize-type=%s%s",
                materialize_type, " [DRY-RUN]" if args.dry_run else "")

    units, discovery_failures = discover_viewdefinitions(args.viewdefinitions_dir)
    if not units and not discovery_failures:
        # Nothing to do is an operator error worth surfacing (FR-006/FR-007).
        msg = (f"No ViewDefinition files found under {args.viewdefinitions_dir} — "
               f"nothing to publish.")
        if args.dry_run:
            logger.warning(msg)
            return 0
        logger.error(msg)
        return 1

    client = None if args.dry_run else FhirClient(config.server)
    view_outcomes = [
        publish_and_materialize(client, unit, materialize_type, args.dry_run)
        for unit in units
    ]

    _report(view_outcomes, discovery_failures, args.dry_run)
    summary = summarize_view_outcomes(view_outcomes, discovery_failures)
    return summary.exit_code


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
