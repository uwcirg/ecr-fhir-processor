#!/usr/bin/env python3
"""ecr-fhir-processor — read FHIR R4 eCR bundles, stamp searchable provenance, and
persist them to an OAuth2-secured target FHIR server using update-in-place semantics.

Single-file CLI (constitution: Single-File Simplicity). Python 3 standard library
only — no runtime third-party dependencies (constitution: Zero-Dependency Runtime).

See specs/001-mvp-fhir-processor/ for the spec, plan, contracts, and quickstart.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# Shared primitives — extracted into fhir_common.py so process.py and publish_views.py
# reuse one FHIR client / config / logging / outcome model (research.md R1). Imported
# here (rather than redefined) so process.py's behavior is unchanged; the names remain
# available as process.<name> for the existing test suite.
from fhir_common import (  # noqa: F401  (re-exported for tests/back-compat)
    DEFAULT_PATHS,
    EXIT_COMPLETED_WITH_DEFERRALS,
    EXIT_SUCCESS,
    EXIT_UNEXPECTED_ERROR,
    PLACEHOLDER_PREFIX,
    REMEDIATION_MRP2_STRATUM_PRUNE,
    REMEDIATION_REFERENCE_SKIP,
    REMEDIATION_TERMINOLOGY_UNSET,
    REMEDIATIONS,
    REQUIRED_SERVER_FIELDS,
    FhirClient,
    FileOutcome,
    RunConfig,
    RunSummary,
    SubmissionError,
    load_config,
    log_remediation,
    logger,
    setup_logging,
    validate_config,
)

# --------------------------------------------------------------------------- #
# Canonical constants (T007; provenance-metadata contract / Principle II)
# --------------------------------------------------------------------------- #

#: Provisional canonical host for this processor's CodeSystems (confirm before
#: publishing; only needs to be a stable constant — research.md D4).
PROVENANCE_BASE = "https://uwcirg.github.io/ecr-fhir-processor/CodeSystem"
SYSTEM_PROCESSED_BY = f"{PROVENANCE_BASE}/processed-by"
SYSTEM_PROCESSED_ON = f"{PROVENANCE_BASE}/processed-on"
SYSTEM_SOURCE_FILE = f"{PROVENANCE_BASE}/source-file"
#: The CMS quality-measure attribution tag system (003; data-model §2, contract C-1).
SYSTEM_CMS_MEASURE = f"{PROVENANCE_BASE}/cms-measure"

#: The set of meta.tag systems this processor owns (used for idempotent re-stamp).
#: SYSTEM_CMS_MEASURE is included so re-stamp replaces the cms-measure tag in place,
#: keeping exactly one (INV-CMS-2) and making US3 re-attribution-on-rename safe (R5).
OWN_TAG_SYSTEMS = frozenset({
    SYSTEM_PROCESSED_BY, SYSTEM_PROCESSED_ON, SYSTEM_SOURCE_FILE, SYSTEM_CMS_MEASURE,
})

#: Stable processor identity code stamped into provenance.
PROCESSOR_IDENTITY = "ecr-fhir-processor"

#: Authoritative CMS-code ↔ measure-slug crosswalk (003 FR-010; data-model §3). The single
#: source of truth for the cms-measure tag's display and the directory/filename disagreement
#: check; the constitution Principle-IV measures. The inverse map resolves a directory slug
#: back to its CMS code for the disagreement signal.
MEASURE_SLUG_BY_CMS = {
    "CMS2": "depression-screening",
    "CMS122": "poor-diabetic-control",
    "CMS165": "controllable-bp",
}
CMS_BY_MEASURE_SLUG = {slug: cms for cms, slug in MEASURE_SLUG_BY_CMS.items()}

#: Input classification kinds.
KIND_COLLECTION = "collection-bundle"
KIND_MEASURE_REPORT = "measure-report"
KIND_MESSAGE = "message-bundle"
KIND_UNKNOWN = "unknown"

#: Kind aliases accepted by --only-types/--skip-types alongside FHIR resourceTypes (D10).
KIND_TYPE_ALIASES = {"measure-report": "MeasureReport"}


# --------------------------------------------------------------------------- #
# Data structures (data-model.md)
# --------------------------------------------------------------------------- #


@dataclass
class InputFile:
    """A single .json file discovered under the input tree."""

    path: Path
    measure: str | None
    population: str | None

    @property
    def filename(self) -> str:
        return self.path.name


class CollisionError(Exception):
    """Two top-level resources share (resourceType, id) but differ in content (FR-019)."""


# --------------------------------------------------------------------------- #
# CLI (T008; contracts/cli.md)
# --------------------------------------------------------------------------- #


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="process.py",
        description="Process FHIR R4 eCR bundles and persist them to a FHIR server.",
    )
    p.add_argument("--config", default="config.json",
                   help="Path to the run config (template: config.example.json).")
    p.add_argument("--input-dir", default=None,
                   help="Root of the input tree (default: config.paths.input_dir).")
    p.add_argument("--measure", default=None,
                   help="Restrict to one measure folder "
                        "(poor-diabetic-control, controllable-bp, depression-screening).")
    p.add_argument("--only-types", default=None,
                   help="Comma-separated FHIR resourceTypes to persist EXCLUSIVELY this "
                        "run (accepts the 'measure-report' kind alias). Mutually "
                        "exclusive with --skip-types (D10).")
    p.add_argument("--skip-types", default=None,
                   help="Comma-separated FHIR resourceTypes to EXCLUDE this run "
                        "(excluded resources counted 'skipped'). Accepts the "
                        "'measure-report' kind alias (D10).")
    p.add_argument("--output-dir", default=None,
                   help="Where the submitted-JSON mirror is written "
                        "(default: config.paths.output_dir).")
    p.add_argument("--no-output-mirror", action="store_true",
                   help="Skip writing the local output mirror.")
    p.add_argument("--dry-run", action="store_true",
                   help="Discover, classify, stamp, transform — but do not submit.")
    p.add_argument("--log-dir", default=None,
                   help="Audit-log directory (default: config.paths.log_dir).")
    p.add_argument("--verbose", action="store_true",
                   help="Console DEBUG verbosity (the file log is always detailed).")
    return p


# --------------------------------------------------------------------------- #
# Version & timestamp (T023, T024 — US2)
# --------------------------------------------------------------------------- #


def derive_version() -> str:
    """Runtime software version from git (D5, FR-006); fallback literal ``unknown``."""
    repo_dir = Path(__file__).resolve().parent
    try:
        result = subprocess.run(
            ["git", "describe", "--tags", "--always", "--dirty"],
            cwd=str(repo_dir),
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            version = result.stdout.strip()
            if version:
                return version
    except (OSError, subprocess.SubprocessError):
        pass
    logger.warning("git version unavailable; using 'unknown' (FR-006/D5).")
    return "unknown"


def processing_timestamp() -> str:
    """Run-constant ISO-8601 instant WITH timezone offset (FR-007, INV-1/INV-4)."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --------------------------------------------------------------------------- #
# Provenance stamping (T025 — US2; provenance-metadata contract)
# --------------------------------------------------------------------------- #


def cms_measure_from_filename(filename: str) -> str:
    """Derive the CMS quality-measure code purely from the input filename (003 FR-001/006).

    Matches ``^CMS\\d+`` case-insensitively against the bare filename and returns the
    normalized uppercase ``CMS<digits>`` (e.g. ``cms165_x.json`` -> ``CMS165``). A filename
    that does not begin with the convention returns the positive sentinel ``"unknown"``.
    The parent directory is never consulted for the value (single source of truth — R2).
    """
    match = re.match(r"CMS(\d+)", Path(filename).name, re.IGNORECASE)
    return f"CMS{match.group(1)}" if match else "unknown"


def stamp(meta: dict | None, version: str, timestamp: str, source_filename: str) -> dict:
    """Additively stamp this processor's provenance onto a resource ``meta``.

    Adds four ``meta.tag[]`` entries (processed-by+version, processed-on, source-file,
    cms-measure) and ``meta.source``. Idempotent: this processor's own prior tags (matched
    by ``system``) are replaced, never appended (INV-2). Pre-existing tags from other
    systems and ``meta.profile`` are preserved (INV-3). Returns the meta dict.
    """
    if meta is None:
        meta = {}
    existing = meta.get("tag", []) or []
    # Drop only our own prior tags (idempotent re-stamp); keep everyone else's.
    tags = [t for t in existing if t.get("system") not in OWN_TAG_SYSTEMS]
    tags.append({
        "system": SYSTEM_PROCESSED_BY,
        "code": PROCESSOR_IDENTITY,
        "version": version,
        "display": f"Processed by {PROCESSOR_IDENTITY} {version}",
    })
    tags.append({"system": SYSTEM_PROCESSED_ON, "code": timestamp})
    tags.append({"system": SYSTEM_SOURCE_FILE, "code": source_filename})
    # CMS-measure attribution derived from the filename (003; contract C-1..C-7). One tag,
    # replaced in place on re-stamp (SYSTEM_CMS_MEASURE is in OWN_TAG_SYSTEMS).
    cms_code = cms_measure_from_filename(source_filename)
    tags.append({
        "system": SYSTEM_CMS_MEASURE,
        "code": cms_code,
        "display": MEASURE_SLUG_BY_CMS.get(cms_code, "unknown measure"),
    })
    meta["tag"] = tags
    meta["source"] = f"{SYSTEM_PROCESSED_BY}#{version}"
    return meta


def stamp_resource(resource: dict, version: str, timestamp: str, source_filename: str) -> dict:
    """Stamp a whole resource in place by mutating (or creating) its ``meta``."""
    resource["meta"] = stamp(resource.get("meta"), version, timestamp, source_filename)
    return resource


# --------------------------------------------------------------------------- #
# Transforms (T015, T029 — US1/US4; data-model transforms, fhir-submission contract)
# --------------------------------------------------------------------------- #


@dataclass
class PutUnit:
    """One independent per-resource ``PUT`` unit of work (D2, Principle V).

    Each contained resource is its own request and its own outcome — there is no
    atomic ``transaction`` Bundle binding them together (FR-020, FR-022).
    """

    resource_type: str
    resource_id: str
    resource: dict

    @property
    def url(self) -> str:
        return f"{self.resource_type}/{self.resource_id}"


def plan_collection_puts(bundle: dict) -> list[PutUnit]:
    """Plan one independent ``PUT [base]/<Type>/<id>`` per contained resource (D2).

    Iterates the ``collection`` Bundle's ``entry[].resource``, retains each original
    ``resource.id`` (D1), and returns one :class:`PutUnit` per resource — **never** an
    atomic ``transaction`` Bundle (FR-020, FR-022). The PutUnit holds the resource by
    reference so upstream stamping is reflected. Raises ``ValueError`` on a resource
    missing ``resourceType``/``id`` (cannot build a PUT url).
    """
    units: list[PutUnit] = []
    for entry in bundle.get("entry", []) or []:
        resource = entry.get("resource", {})
        rtype = resource.get("resourceType")
        rid = resource.get("id")
        if not rtype or not rid:
            raise ValueError(
                f"Collection entry missing resourceType/id (cannot build PUT url): "
                f"{rtype}/{rid}"
            )
        units.append(PutUnit(rtype, rid, resource))
    return units


# --------------------------------------------------------------------------- #
# MeasureReport mrp-2 stratum prune (Cause 2 — the only content transform, US2;
# contracts/stratum-prune.md, Principle VIII/V)
# --------------------------------------------------------------------------- #


def _summarize_stratum_populations(stratum: dict) -> str:
    """Render a removed stratum's population counts for the audit WARNING (FR-006).

    Each population is ``<code>=<count>`` (code from the first `population.code.coding`
    with a code, else `code.text`), so the drop is never silent — the counts it carried
    are captured in the log (contract C6, SC-003).
    """
    parts: list[str] = []
    for pop in stratum.get("population", []) or []:
        code = pop.get("code", {}) or {}
        label = None
        for coding in code.get("coding", []) or []:
            if coding.get("code"):
                label = coding["code"]
                break
        if label is None:
            label = code.get("text", "?")
        parts.append(f"{label}={pop.get('count')}")
    return ", ".join(parts) if parts else "(no populations)"


def prune_measurereport_strata(report: dict, source_filename: str) -> int:
    """Remove every stratifier stratum lacking both ``value`` and ``component`` (mrp-2).

    Mutates ``report`` in place; returns the number of strata removed. A stratum is
    removed **iff** ``value is None and not component`` (contract C1) — a stratum with
    ``value`` xor ``component`` is left untouched (C2). Every other element of the
    MeasureReport is unchanged (C3); empty stratum/stratifier/group arrays are left in
    place (C4 — the transform removes strata, never stratifiers). Idempotent (C5). Never
    fabricates — it only removes (C9). Each removal logs a WARNING via ``log_remediation``
    carrying the removed stratum's population counts (C6, FR-006).
    """
    removed = 0
    for group in report.get("group", []) or []:
        for stratifier in group.get("stratifier", []) or []:
            strata = stratifier.get("stratum")
            if not isinstance(strata, list):
                continue
            kept = []
            for stratum in strata:
                if stratum.get("value") is None and not stratum.get("component"):
                    removed += 1
                    log_remediation(
                        REMEDIATION_MRP2_STRATUM_PRUNE,
                        "Removed value/component-less MeasureReport stratum "
                        "(base-FHIR mrp-2) from %s; carried populations: %s",
                        source_filename, _summarize_stratum_populations(stratum),
                    )
                else:
                    kept.append(stratum)
            # Only touch the stratifier when something was removed, so a clean stratifier
            # stays byte-identical (C3, C5 idempotency). When the removal empties the list,
            # DELETE the `stratum` property rather than leaving `[]`: an empty array is
            # itself a base-FHIR violation ("Array cannot be empty — the property should
            # not be present if it has no values"), which would introduce a new HL7-gate
            # signature (FR-009). A stratifier with no `stratum` satisfies mrp-2 vacuously.
            if len(kept) != len(strata):
                if kept:
                    stratifier["stratum"] = kept
                else:
                    del stratifier["stratum"]
    return removed


def prune_nested_measurereports(bundle: dict, source_filename: str) -> int:
    """Apply :func:`prune_measurereport_strata` to every MeasureReport in ``bundle``.

    Walks ``bundle.entry[*].resource``, recursing into nested Bundles (e.g. the eICR
    document Bundle inside a message Bundle), so a message Bundle carrying an unpruned
    MeasureReport is not rejected whole (contract C7, FR-005). Returns total strata removed.
    """
    total = 0

    def walk(node: dict) -> None:
        nonlocal total
        for entry in node.get("entry", []) or []:
            resource = entry.get("resource")
            if not isinstance(resource, dict):
                continue
            rtype = resource.get("resourceType")
            if rtype == "MeasureReport":
                total += prune_measurereport_strata(resource, source_filename)
            elif rtype == "Bundle":
                walk(resource)

    walk(bundle)
    return total


def extract_eicr_composition(message_bundle: dict) -> dict | None:
    """Extract the eICR ``Composition`` nested in the message Bundle's document Bundle.

    Locates ``entry(content Bundle, type=document)`` and returns its first
    ``Composition`` resource (a per-case GUID id — collision-safe for PUT, unlike the
    document Bundle's fixed template-handle id, D4b). Returns ``None`` if absent (D2b).
    Promotes **only** the Composition — the eICR's other nested clinical copies are
    lower-fidelity duplicates and are NOT re-persisted (Principle V/VI).
    """
    for entry in message_bundle.get("entry", []) or []:
        resource = entry.get("resource", {})
        if resource.get("resourceType") == "Bundle" and resource.get("type") == "document":
            for nested in resource.get("entry", []) or []:
                candidate = nested.get("resource", {})
                if candidate.get("resourceType") == "Composition":
                    return candidate
    return None


def document_resource_keys(message_bundle: dict) -> set[str]:
    """Collect ``Type/id`` keys of the resources inside the message's document Bundle.

    These are the resources the promoted Composition's references resolve against — they
    are persisted (under identical retained GUIDs) via the authoritative collection
    Bundle (D2b).
    """
    keys: set[str] = set()
    for entry in message_bundle.get("entry", []) or []:
        resource = entry.get("resource", {})
        if resource.get("resourceType") == "Bundle" and resource.get("type") == "document":
            for nested in resource.get("entry", []) or []:
                nres = nested.get("resource", {})
                rtype, rid = nres.get("resourceType"), nres.get("id")
                if rtype and rid:
                    keys.add(f"{rtype}/{rid}")
    return keys


# --------------------------------------------------------------------------- #
# Type filter (T030 — US4; D10, cli contract / data-model TypeFilter)
# --------------------------------------------------------------------------- #


@dataclass
class TypeFilter:
    """Selects which FHIR resourceTypes are persisted this run (D10, Principle V).

    ``only`` (from ``--only-types``) persists ONLY the listed types; ``skip`` (from
    ``--skip-types``) persists everything EXCEPT them. The two are mutually exclusive;
    neither set means persist all. Excluded resources are counted ``skipped`` (D8).
    """

    only: frozenset | None = None
    skip: frozenset | None = None

    def allows(self, resource_type: str) -> bool:
        if self.only is not None:
            return resource_type in self.only
        if self.skip is not None:
            return resource_type not in self.skip
        return True


def _normalize_types(raw: str) -> frozenset:
    """Parse a comma-separated type list, mapping kind aliases to resourceTypes (D10)."""
    types = set()
    for token in raw.split(","):
        token = token.strip()
        if token:
            types.add(KIND_TYPE_ALIASES.get(token.lower(), token))
    return frozenset(types)


def build_type_filter(only_types: str | None, skip_types: str | None) -> TypeFilter:
    """Build a :class:`TypeFilter` from the CLI flags; the two are mutually exclusive."""
    if only_types and skip_types:
        raise ValueError("--only-types and --skip-types are mutually exclusive (D10).")
    return TypeFilter(
        only=_normalize_types(only_types) if only_types else None,
        skip=_normalize_types(skip_types) if skip_types else None,
    )


# --------------------------------------------------------------------------- #
# Collision detection (T017 — US1; FR-019, D4b)
# --------------------------------------------------------------------------- #


class CollisionTracker:
    """Tracks top-level persisted ``(resourceType, id)`` to catch silent overwrites.

    Differing content for the same key → CollisionError (fail loud). Identical content
    → "duplicate" (expected dedup of shared Practitioner/Organization/Location). Only
    top-level persisted resources are registered — NOT resources nested inside a
    message Bundle, so the fixed eICR document-Bundle id never enters the set (D4b).
    """

    def __init__(self) -> None:
        self._seen: dict[tuple[str, str], str] = {}

    @staticmethod
    def _canonical(content: dict) -> str:
        # Compare CLINICAL content only: exclude `meta`, which carries our additive
        # provenance tags (per-file source-file) and server-managed versionId/
        # lastUpdated — none of which is part of resource identity (D4b, FR-019).
        clinical = {k: v for k, v in content.items() if k != "meta"}
        return json.dumps(clinical, sort_keys=True, separators=(",", ":"))

    def check(self, resource_type: str, resource_id: str, content: dict) -> str:
        key = (resource_type, resource_id)
        canonical = self._canonical(content)
        if key in self._seen:
            if self._seen[key] == canonical:
                return "duplicate"
            raise CollisionError(
                f"Two resources share {resource_type}/{resource_id} but differ in "
                f"content; refusing to silently overwrite (FR-019)."
            )
        self._seen[key] = canonical
        return "new"


# --------------------------------------------------------------------------- #
# Reference handling (T018 — US1; FR-017, D3)
# --------------------------------------------------------------------------- #


def collect_references(resource: dict) -> list[str]:
    """Return every ``reference`` string found anywhere in ``resource`` (recursive)."""
    refs: list[str] = []

    def walk(node: object) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "reference" and isinstance(value, str):
                    refs.append(value)
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(resource)
    return refs


def warn_on_absolute_references(resource: dict, base_url: str) -> None:
    """Log a WARNING for absolute references pointing at a non-target host (D3).

    References are never rewritten; relative refs are left intact so they resolve via
    retained ids. Walks the resource recursively for ``reference`` string fields.
    """
    base = (base_url or "").rstrip("/")
    for value in collect_references(resource):
        if value.startswith(("http://", "https://")):
            if not base or not value.startswith(base):
                logger.warning(
                    "Absolute reference to a non-target host will not "
                    "resolve internally (left as-is, D3): %s", value
                )


def warn_unresolved_composition_refs(composition: dict, resolvable: set) -> list[str]:
    """WARN for each promoted-Composition reference that won't resolve (D2b, D3).

    Checks only relative ``Type/id`` references against ``resolvable`` (the set of
    ``Type/id`` keys persisted for this case). Absolute/``urn:`` references are handled
    by :func:`warn_on_absolute_references` and are not re-checked here. References are
    **never** mutated. Returns the list of unresolved relative references.
    """
    unresolved: list[str] = []
    for ref in collect_references(composition):
        if ref.startswith(("http://", "https://", "urn:")) or "/" not in ref:
            continue
        if ref not in resolvable:
            unresolved.append(ref)
            logger.warning(
                "Promoted Composition reference does not resolve to a persisted "
                "resource (left as-is, D2b/D3): %s", ref
            )
    return unresolved


# --------------------------------------------------------------------------- #
# Discovery & classification (T010 — Foundational; FR-001, data-model)
# --------------------------------------------------------------------------- #


def classify_resource(data: dict) -> str:
    """Classify a parsed FHIR resource into one of the processor's input kinds."""
    rtype = data.get("resourceType")
    if rtype == "MeasureReport":
        return KIND_MEASURE_REPORT
    if rtype == "Bundle":
        btype = data.get("type")
        if btype == "collection":
            return KIND_COLLECTION
        if btype == "message":
            return KIND_MESSAGE
    return KIND_UNKNOWN


def discover_inputs(root: str, measure_filter: str | None = None) -> list[InputFile]:
    """Recursively find ``*.json`` under ``root``, deriving measure/population from path.

    Returns InputFiles sorted by path for deterministic processing. ``measure_filter``
    restricts to a single top-level measure folder (CLI ``--measure``).
    """
    root_path = Path(root)
    found: list[InputFile] = []
    if not root_path.exists():
        logger.warning("Input root does not exist: %s", root)
        return found
    for path in sorted(root_path.rglob("*.json")):
        rel = path.relative_to(root_path).parts
        measure = rel[0] if len(rel) >= 2 else None
        population = rel[1] if len(rel) >= 3 else None
        if measure_filter and measure != measure_filter:
            continue
        # Disagreement signal (003 FR-007): warn — never silently reconcile (Principle V) —
        # when the filename code is concrete AND the directory slug maps to a *different*
        # concrete code. The filename remains authoritative for the tag regardless.
        file_code = cms_measure_from_filename(path.name)
        dir_code = CMS_BY_MEASURE_SLUG.get(measure)
        if file_code != "unknown" and dir_code is not None and file_code != dir_code:
            logger.warning(
                "CMS measure mismatch for %s: filename=%s directory=%s (%s); "
                "using filename.", path.name, file_code, dir_code, measure)
        found.append(InputFile(path=path, measure=measure, population=population))
    return found


# --------------------------------------------------------------------------- #
# Output mirror (T020 — US1; D9)
# --------------------------------------------------------------------------- #


def mirror_output(output_dir: str, measure: str | None, run_date: str,
                  filename: str, payload: dict) -> Path:
    """Write the (stamped/transformed) submitted JSON to output/{measure}/{date}/."""
    target_dir = Path(output_dir) / (measure or "unknown") / run_date
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / filename
    with target.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    logger.debug("Mirrored submitted JSON to %s", target)
    return target


# --------------------------------------------------------------------------- #
# Per-file processing (wires US1 + US2; T016/T019/T026)
# --------------------------------------------------------------------------- #


def _mark_remediated(outcome: FileOutcome, removed: int) -> None:
    """Reclassify a stored outcome as ``remediated`` after a content transform (US2).

    Only a ``succeeded`` (stored) outcome is promoted to ``remediated`` — a ``failed`` PUT
    is left as the more urgent signal, and a ``skipped``/``deferred`` unit was never stored.
    ``remediated`` counts as stored but is reported separately so an operator sees which
    resources required a transform (data-model §5, contracts/run-accounting.md).
    """
    if outcome.status == "succeeded":
        outcome.status = "remediated"
        note = f"remediated: pruned {removed} mrp-2 stratum(s)"
        outcome.detail = f"{outcome.detail}; {note}" if outcome.detail else note


@dataclass
class Pipeline:
    """Run-scoped processing context (one per execution).

    Persists each contained resource as its **own** ``PUT`` (no atomic transaction —
    D2/Principle V): failures isolate per resource and resource types persist
    independently. ``process()`` returns one :class:`FileOutcome` per unit of work
    (per-resource PUT, standalone PUT, message-Bundle PUT, and promoted-Composition PUT).
    """

    config: RunConfig
    version: str
    timestamp: str
    run_date: str
    dry_run: bool
    output_dir: str
    write_mirror: bool
    client: FhirClient | None
    type_filter: TypeFilter = field(default_factory=TypeFilter)
    collisions: CollisionTracker = field(default_factory=CollisionTracker)
    #: Resource types to DEFER — isolated as `deferred` (not submitted) because only
    #: fabricating or dropping clinical content could store them (FR-007, Principle V).
    #: Empty by default: the current sample needs no deferral, but the mechanism must
    #: exist so storability is never bought with fabrication (drives the three-state exit
    #: code via RunSummary.deferred). Populated by policy, not a CLI flag today.
    deferrals: frozenset = field(default_factory=frozenset)

    # -- shared helpers ------------------------------------------------------ #

    def _stamp(self, resource: dict, source_filename: str) -> None:
        """Stamp a resource and WARN on absolute non-target references (US2 T026, D3)."""
        stamp_resource(resource, self.version, self.timestamp, source_filename)
        if self.client is not None:
            warn_on_absolute_references(resource, self.client.base)

    def _put(self, kind: str, resource_type: str, resource_id: str, resource: dict,
             source_filename: str) -> FileOutcome:
        """Persist one resource as its own ``PUT`` and return its isolated outcome.

        Applies the type filter (counted ``skipped``, D10), honours ``--dry-run`` (logs
        the would-be PUT, no submission, SUB-5), and isolates a non-2xx / network failure
        to this resource (counted ``failed``, never blocks siblings — SUB-3, D8).
        """
        action = f"PUT {resource_type}/{resource_id}"
        if not self.type_filter.allows(resource_type):
            logger.info("Skipping %s — excluded by --only-types/--skip-types (%s).",
                        action, source_filename)
            return FileOutcome(source_filename, kind, action, 1, "skipped",
                               "excluded by type filter (D10)")
        if resource_type in self.deferrals:
            # Isolate rather than fabricate: this type could only be stored by inventing or
            # dropping clinical content, so it is deferred (not submitted) — never blocks a
            # sibling, and surfaces via the three-state exit code (FR-007, FR-011).
            logger.warning("Deferring %s (%s): only fabrication could store this type; "
                           "isolated, not submitted (FR-007).", action, source_filename)
            return FileOutcome(source_filename, kind, action, 1, "deferred",
                               "deferred: would require fabrication (FR-007)")
        if self.dry_run:
            logger.info("[dry-run] would %s (%s).", action, source_filename)
            return FileOutcome(source_filename, kind, action, 1, "succeeded", "dry-run")
        try:
            status, response = self.client.submit_put(resource_type, resource_id, resource)
        except SubmissionError as exc:
            logger.error("Submission error for %s (%s): %s", action, source_filename, exc)
            return FileOutcome(source_filename, kind, action, 1, "failed", str(exc))
        if 200 <= status < 300:
            return FileOutcome(source_filename, kind, action, 1, "succeeded", f"HTTP {status}")
        logger.error("Submission rejected for %s (%s) HTTP %d: %s", action,
                     source_filename, status, json.dumps(response))
        return FileOutcome(source_filename, kind, action, 1, "failed",
                           f"HTTP {status}: {json.dumps(response)}")

    def _guarded_put(self, kind: str, resource_type: str, resource_id: str,
                     resource: dict, source_filename: str) -> FileOutcome:
        """Collision-check then PUT a single top-level resource; isolate either failure."""
        try:
            status = self.collisions.check(resource_type, resource_id, resource)
        except CollisionError as exc:
            logger.error("Collision for %s/%s (%s): %s", resource_type, resource_id,
                         source_filename, exc)
            return FileOutcome(source_filename, kind, f"PUT {resource_type}/{resource_id}",
                               1, "failed", str(exc))
        if status == "duplicate":
            logger.info("Dedup: %s/%s already persisted with identical content.",
                        resource_type, resource_id)
        return self._put(kind, resource_type, resource_id, resource, source_filename)

    def _maybe_mirror(self, measure: str | None, source_filename: str,
                      payload: dict) -> None:
        if self.write_mirror:
            mirror_output(self.output_dir, measure, self.run_date, source_filename, payload)

    # -- entry point --------------------------------------------------------- #

    def process(self, data: dict, kind: str, source_filename: str,
                measure: str | None) -> list[FileOutcome]:
        """Stamp, plan, and submit one parsed input by kind; return per-unit outcomes."""
        if kind == KIND_COLLECTION:
            return self._process_collection(data, source_filename, measure)
        if kind == KIND_MEASURE_REPORT:
            return self._process_measure_report(data, source_filename, measure)
        if kind == KIND_MESSAGE:
            return self._process_message(data, source_filename, measure)
        raise ValueError(f"Unsupported kind: {kind}")

    def _process_collection(self, bundle: dict, source_filename: str,
                            measure: str | None) -> list[FileOutcome]:
        # Plan one independent PUT per contained resource — NO transaction (D2, FR-022).
        units = plan_collection_puts(bundle)
        for unit in units:
            self._stamp(unit.resource, source_filename)
        # Mirror the stamped bundle (the submitted-resource content) for inspection (D9).
        self._maybe_mirror(measure, source_filename, bundle)
        return [self._guarded_put(KIND_COLLECTION, unit.resource_type, unit.resource_id,
                                  unit.resource, source_filename) for unit in units]

    def _process_measure_report(self, report: dict, source_filename: str,
                                measure: str | None) -> list[FileOutcome]:
        self._stamp(report, source_filename)
        # Cause 2 transform on the write path, BEFORE the mirror, so output/ bytes equal
        # the PUT bytes (FR-008, contract C8). The test/input fixture is never touched.
        removed = prune_measurereport_strata(report, source_filename)
        self._maybe_mirror(measure, source_filename, report)
        outcome = self._guarded_put(KIND_MEASURE_REPORT, "MeasureReport",
                                    report.get("id"), report, source_filename)
        if removed:
            _mark_remediated(outcome, removed)
        return [outcome]

    def _process_message(self, bundle: dict, source_filename: str,
                         measure: str | None) -> list[FileOutcome]:
        # Stamp the message Bundle's OWN meta; its nested clinical copies are persisted
        # via the authoritative collection Bundle, NOT here (Principle V/VI).
        bundle["meta"] = stamp(bundle.get("meta"), self.version, self.timestamp,
                               source_filename)
        # Promote ONLY the nested eICR Composition to a first-class resource (D2b).
        composition = extract_eicr_composition(bundle)
        if composition is not None:
            self._stamp(composition, source_filename)
            warn_unresolved_composition_refs(composition, document_resource_keys(bundle))
        # Cause 2 transform for MeasureReports nested inside this message/document Bundle,
        # BEFORE the mirror + whole-Bundle PUT, so the Bundle is not rejected whole for an
        # unpruned nested MeasureReport (FR-005) and output/ bytes equal the PUT bytes (C8).
        removed = prune_nested_measurereports(bundle, source_filename)
        self._maybe_mirror(measure, source_filename, bundle)

        outcomes = [self._guarded_put(KIND_MESSAGE, "Bundle", bundle.get("id"),
                                      bundle, source_filename)]
        if removed:
            _mark_remediated(outcomes[0], removed)
        if composition is not None:
            # The Composition's per-case GUID is collision-safe (D4b); persist it as its
            # own first-class outcome in addition to the message Bundle.
            outcomes.append(self._guarded_put(KIND_MESSAGE, "Composition",
                                              composition.get("id"), composition,
                                              source_filename))
        else:
            logger.warning("No eICR Composition found to promote in %s (D2b).",
                           source_filename)
        return outcomes


# --------------------------------------------------------------------------- #
# Run orchestration (T011 RunSummary; T029 precedence — US3)
# --------------------------------------------------------------------------- #


def resolve_paths(config: RunConfig, args: argparse.Namespace) -> dict:
    """CLI flags override config.paths defaults (T029, US3 scenario 1)."""
    return {
        "input_dir": args.input_dir or config.paths.get("input_dir", "input"),
        "output_dir": args.output_dir or config.paths.get("output_dir", "output"),
        "log_dir": args.log_dir or config.paths.get("log_dir", "log"),
    }


def run(args: argparse.Namespace) -> int:
    """Top-level run: load+validate config, discover, process, summarize."""
    try:
        config = load_config(args.config)
    except FileNotFoundError as exc:
        if args.dry_run:
            # Dry-run never contacts the server (SUB-5); proceed with built-in
            # path/ig defaults so the transform/validation gate works config-free.
            config = RunConfig(software={}, server={}, ig_versions={},
                               paths=dict(DEFAULT_PATHS), raw={})
        else:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
    except (json.JSONDecodeError, ValueError) as exc:
        # Logging may not be configured yet — emit to stderr too.
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    paths = resolve_paths(config, args)
    setup_logging(paths["log_dir"], args.verbose)

    try:
        type_filter = build_type_filter(args.only_types, args.skip_types)
    except ValueError as exc:
        logger.error(str(exc))
        return 1

    config_errors = validate_config(config, args.dry_run)
    if config_errors:
        for err in config_errors:
            logger.error(err)
        return 1

    version = derive_version()
    timestamp = processing_timestamp()
    run_date = datetime.now().strftime("%Y-%m-%d")
    logger.info("ecr-fhir-processor version=%s processed-on=%s%s",
                version, timestamp, " [DRY-RUN]" if args.dry_run else "")

    inputs = discover_inputs(paths["input_dir"], args.measure)
    if not inputs:
        logger.info("No input files found under %s — nothing processed.",
                    paths["input_dir"])
        return 0

    client = None if args.dry_run else FhirClient(config.server)
    pipeline = Pipeline(
        config=config,
        version=version,
        timestamp=timestamp,
        run_date=run_date,
        dry_run=args.dry_run,
        output_dir=paths["output_dir"],
        write_mirror=not args.no_output_mirror,
        client=client,
        type_filter=type_filter,
    )

    summary = RunSummary()
    for item in inputs:
        summary.read += 1
        try:
            with item.path.open(encoding="utf-8") as fh:
                data = json.load(fh)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Skipping unreadable/malformed file %s: %s",
                           item.filename, exc)
            summary.skipped += 1
            summary.record(FileOutcome(item.filename, KIND_UNKNOWN, "skip", 0,
                                       "skipped", str(exc)))
            continue

        kind = classify_resource(data)
        if kind == KIND_UNKNOWN:
            logger.warning("Skipping unrecognized file %s (resourceType=%s, type=%s).",
                           item.filename, data.get("resourceType"), data.get("type"))
            summary.skipped += 1
            summary.record(FileOutcome(item.filename, KIND_UNKNOWN, "skip", 0,
                                       "skipped", "unrecognized kind"))
            continue

        try:
            # Per-resource isolation: collision/submission failures are handled inside
            # the pipeline and returned as individual outcomes; only a malformed bundle
            # (planner ValueError) or unsupported kind fails the whole file here.
            outcomes = pipeline.process(data, kind, item.filename, item.measure)
        except ValueError as exc:
            logger.error("Failed processing %s: %s", item.filename, exc)
            summary.failed += 1
            summary.record(FileOutcome(item.filename, kind, "error", 0,
                                       "failed", str(exc)))
            continue

        for outcome in outcomes:
            summary.record(outcome)
            if outcome.status == "succeeded":
                summary.succeeded += 1
                summary.submitted += 1
            elif outcome.status == "remediated":
                # Stored, but via a content transform — counted separately from untouched
                # `succeeded` so the summary reports which resources required remediation
                # (data-model §5). Does not affect the exit code.
                summary.remediated += 1
                summary.submitted += 1
            elif outcome.status == "deferred":
                # Isolated to avoid fabrication (FR-007) — NOT submitted; drives the
                # three-state exit code (EXIT_COMPLETED_WITH_DEFERRALS) via RunSummary.
                summary.deferred += 1
            elif outcome.status == "failed":
                summary.failed += 1
                summary.submitted += 1
            elif outcome.status == "skipped":
                summary.skipped += 1

    _report_summary(summary, args.dry_run)
    return summary.exit_code


def _report_summary(summary: RunSummary, dry_run: bool) -> None:
    logger.info("=" * 60)
    logger.info("RunSummary%s", " [DRY-RUN]" if dry_run else "")
    for o in summary.outcomes:
        logger.info("  %-9s %-16s %-28s n=%-3d %s",
                    o.status, o.kind, o.action, o.resource_count,
                    o.filename + (f" — {o.detail}" if o.detail else ""))
    # Stratify resource outcomes by FHIR type (D8). `read` counts input *files*; the
    # remaining totals count *resources* (one per independent PUT). Type-less outcomes
    # (unreadable/unrecognized files) carry no resource_type and are omitted here.
    by_type: dict[str, dict[str, int]] = {}
    for o in summary.outcomes:
        if o.resource_type is None:
            continue
        counts = by_type.setdefault(
            o.resource_type,
            {"succeeded": 0, "remediated": 0, "deferred": 0, "failed": 0, "skipped": 0})
        if o.status in counts:
            counts[o.status] += 1

    if by_type:
        logger.info("-" * 60)
        logger.info("resources by type "
                    "(stored = succeeded + remediated; deferred = not submitted):")
        for rtype in sorted(by_type):
            c = by_type[rtype]
            # submitted = every unit actually PUT; deferred/skipped were not submitted.
            submitted = c["succeeded"] + c["remediated"] + c["failed"]
            logger.info(
                "  %-18s submitted=%-3d succeeded=%-3d remediated=%-3d failed=%-3d "
                "deferred=%-3d skipped=%-3d",
                rtype, submitted, c["succeeded"], c["remediated"], c["failed"],
                c["deferred"], c["skipped"])

    logger.info("-" * 60)
    logger.info("read=%d input-files | resources: submitted=%d succeeded=%d "
                "remediated=%d failed=%d deferred=%d skipped=%d",
                summary.read, summary.submitted, summary.succeeded,
                summary.remediated, summary.failed, summary.deferred, summary.skipped)
    logger.info("exit_code=%d (%s)", summary.exit_code, _exit_code_meaning(summary.exit_code))
    logger.info("=" * 60)


def _exit_code_meaning(code: int) -> str:
    """Human-readable meaning of a resolved exit code, so an operator reads the run's
    disposition from its own summary without cross-referencing the docs (FR-012)."""
    return {
        EXIT_SUCCESS: "success — every in-scope resource stored",
        EXIT_UNEXPECTED_ERROR: "unexpected error — an undocumented rejection/transport failure",
        EXIT_COMPLETED_WITH_DEFERRALS: "completed with deferrals — some types isolated, not submitted",
    }.get(code, "unknown")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
