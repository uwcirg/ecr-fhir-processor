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
import logging
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# --------------------------------------------------------------------------- #
# Canonical constants (T007; provenance-metadata contract / Principle II)
# --------------------------------------------------------------------------- #

#: Provisional canonical host for this processor's CodeSystems (confirm before
#: publishing; only needs to be a stable constant — research.md D4).
PROVENANCE_BASE = "https://uwcirg.github.io/ecr-fhir-processor/CodeSystem"
SYSTEM_PROCESSED_BY = f"{PROVENANCE_BASE}/processed-by"
SYSTEM_PROCESSED_ON = f"{PROVENANCE_BASE}/processed-on"
SYSTEM_SOURCE_FILE = f"{PROVENANCE_BASE}/source-file"

#: The set of meta.tag systems this processor owns (used for idempotent re-stamp).
OWN_TAG_SYSTEMS = frozenset({SYSTEM_PROCESSED_BY, SYSTEM_PROCESSED_ON, SYSTEM_SOURCE_FILE})

#: Stable processor identity code stamped into provenance.
PROCESSOR_IDENTITY = "ecr-fhir-processor"

#: Required, non-empty server fields (rejected if still a YOUR_* placeholder).
REQUIRED_SERVER_FIELDS = ("base_url", "token_endpoint", "client_id", "client_secret")

#: Prefix marking the example-config placeholders that must be replaced (FR-010).
PLACEHOLDER_PREFIX = "YOUR_"

#: Default config-relative paths (overridable by config.paths and CLI flags).
DEFAULT_PATHS = {"input_dir": "input", "output_dir": "output", "log_dir": "log"}

#: Input classification kinds.
KIND_COLLECTION = "collection-bundle"
KIND_MEASURE_REPORT = "measure-report"
KIND_MESSAGE = "message-bundle"
KIND_UNKNOWN = "unknown"

logger = logging.getLogger("ecr-fhir-processor")


# --------------------------------------------------------------------------- #
# Data structures (data-model.md)
# --------------------------------------------------------------------------- #


@dataclass
class RunConfig:
    """Parsed config.json (template config.example.json, reconciled per D7)."""

    software: dict
    server: dict
    ig_versions: dict
    paths: dict
    raw: dict = field(default_factory=dict)


@dataclass
class InputFile:
    """A single .json file discovered under the input tree."""

    path: Path
    measure: str | None
    population: str | None

    @property
    def filename(self) -> str:
        return self.path.name


@dataclass
class FileOutcome:
    """Per-file result folded into the RunSummary."""

    filename: str
    kind: str
    action: str
    resource_count: int
    status: str  # succeeded | failed | skipped
    detail: str = ""


@dataclass
class RunSummary:
    """Aggregate of one execution (FR-014, D8)."""

    read: int = 0
    submitted: int = 0
    succeeded: int = 0
    failed: int = 0
    skipped: int = 0
    outcomes: list[FileOutcome] = field(default_factory=list)

    def record(self, outcome: FileOutcome) -> None:
        self.outcomes.append(outcome)

    @property
    def exit_code(self) -> int:
        return 0 if self.failed == 0 else 1


class CollisionError(Exception):
    """Two top-level resources share (resourceType, id) but differ in content (FR-019)."""


class SubmissionError(Exception):
    """A FHIR submission returned a non-2xx status (carries the server payload)."""

    def __init__(self, status: int, detail: str):
        super().__init__(f"HTTP {status}: {detail}")
        self.status = status
        self.detail = detail


# --------------------------------------------------------------------------- #
# Logging (T006, D9, FR-013)
# --------------------------------------------------------------------------- #


def setup_logging(log_dir: str, verbose: bool) -> Path:
    """Configure dual logging: console + timestamped audit file under ``log_dir``.

    ``--verbose`` raises the console handler to DEBUG; the file is always detailed.
    Returns the path of the log file written.
    """
    log_path_dir = Path(log_dir)
    log_path_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%dt%H%M%S")
    log_file = log_path_dir / f"ecr-fhir-processor_{stamp}.log"

    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(message)s")

    console = logging.StreamHandler()
    console.setLevel(logging.DEBUG if verbose else logging.INFO)
    console.setFormatter(fmt)
    logger.addHandler(console)

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    logger.debug("Logging to %s", log_file)
    return log_file


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
# Config (T009 load; T028 validate — US3)
# --------------------------------------------------------------------------- #


def load_config(path: str) -> RunConfig:
    """Read ``path`` JSON into a RunConfig. Raises FileNotFoundError / ValueError."""
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(
            f"Config file not found: {path}. Copy config.example.json to config.json "
            f"and fill in server credentials."
        )
    with config_path.open(encoding="utf-8") as fh:
        raw = json.load(fh)

    paths = dict(DEFAULT_PATHS)
    paths.update(raw.get("paths", {}) or {})

    return RunConfig(
        software=raw.get("software", {}) or {},
        server=raw.get("server", {}) or {},
        ig_versions=raw.get("ig_versions", {}) or {},
        paths=paths,
        raw=raw,
    )


def validate_config(config: RunConfig, dry_run: bool) -> list[str]:
    """Fail-fast validation (FR-010, US3). Returns a list of error messages.

    Required, non-empty ``server.*`` fields; values still equal to their ``YOUR_*``
    placeholders are rejected. Under ``--dry-run`` server credentials are not required
    (no token request/submission happens).
    """
    errors: list[str] = []
    if dry_run:
        return errors  # dry-run never contacts the server (SUB-5)

    server = config.server or {}
    for fieldname in REQUIRED_SERVER_FIELDS:
        value = server.get(fieldname)
        if value is None or (isinstance(value, str) and value.strip() == ""):
            errors.append(f"Missing required config field: server.{fieldname}")
        elif isinstance(value, str) and value.startswith(PLACEHOLDER_PREFIX):
            errors.append(
                f"Config field server.{fieldname} is still the example placeholder "
                f"'{value}'. Edit config.json with real values."
            )
    return errors


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


def stamp(meta: dict | None, version: str, timestamp: str, source_filename: str) -> dict:
    """Additively stamp this processor's provenance onto a resource ``meta``.

    Adds three ``meta.tag[]`` entries (processed-by+version, processed-on, source-file)
    and ``meta.source``. Idempotent: this processor's own prior tags (matched by
    ``system``) are replaced, never appended (INV-2). Pre-existing tags from other
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
    meta["tag"] = tags
    meta["source"] = f"{SYSTEM_PROCESSED_BY}#{version}"
    return meta


def stamp_resource(resource: dict, version: str, timestamp: str, source_filename: str) -> dict:
    """Stamp a whole resource in place by mutating (or creating) its ``meta``."""
    resource["meta"] = stamp(resource.get("meta"), version, timestamp, source_filename)
    return resource


# --------------------------------------------------------------------------- #
# Transforms (T015 — US1; data-model transforms, fhir-submission contract)
# --------------------------------------------------------------------------- #


def transform_collection_to_transaction(bundle: dict) -> dict:
    """Convert a ``collection`` Bundle to a ``transaction`` Bundle of PUT entries (D2).

    Each entry gets ``request = {method: "PUT", url: "<ResourceType>/<id>"}`` and the
    original ``resource.id`` is retained (D1). Returns a new Bundle dict; entry
    resources are shared by reference so upstream stamping is reflected.
    """
    out = dict(bundle)
    out["type"] = "transaction"
    new_entries = []
    for entry in bundle.get("entry", []) or []:
        resource = entry.get("resource", {})
        rtype = resource.get("resourceType")
        rid = resource.get("id")
        if not rtype or not rid:
            raise ValueError(
                f"Collection entry missing resourceType/id (cannot build PUT url): "
                f"{rtype}/{rid}"
            )
        new_entry = {"resource": resource,
                     "request": {"method": "PUT", "url": f"{rtype}/{rid}"}}
        if "fullUrl" in entry:
            new_entry["fullUrl"] = entry["fullUrl"]
        new_entries.append(new_entry)
    out["entry"] = new_entries
    return out


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


def warn_on_absolute_references(resource: dict, base_url: str) -> None:
    """Log a WARNING for absolute references pointing at a non-target host (D3).

    References are never rewritten; relative refs are left intact so they resolve via
    retained ids. Walks the resource recursively for ``reference`` string fields.
    """
    base = (base_url or "").rstrip("/")

    def walk(node: object) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "reference" and isinstance(value, str):
                    if value.startswith(("http://", "https://")):
                        if not base or not value.startswith(base):
                            logger.warning(
                                "Absolute reference to a non-target host will not "
                                "resolve internally (left as-is, D3): %s", value
                            )
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(resource)


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
        found.append(InputFile(path=path, measure=measure, population=population))
    return found


# --------------------------------------------------------------------------- #
# FHIR client / OAuth2 (T014, T016, T019 — US1; fhir-submission contract)
# --------------------------------------------------------------------------- #


class FhirClient:
    """Minimal OAuth2 client-credentials FHIR client (urllib only, D6)."""

    def __init__(self, server: dict):
        self.server = server
        self.base = (server.get("base_url") or "").rstrip("/")
        self.token: str | None = None

    def _fetch_token(self) -> str:
        data = urllib.parse.urlencode({
            "grant_type": "client_credentials",
            "client_id": self.server.get("client_id", ""),
            "client_secret": self.server.get("client_secret", ""),
        }).encode("utf-8")
        req = urllib.request.Request(
            self.server["token_endpoint"], data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        with urllib.request.urlopen(req) as resp:  # noqa: S310 (config-controlled URL)
            payload = json.loads(resp.read().decode("utf-8"))
        token = payload.get("access_token")
        if not token:
            raise SubmissionError(0, "Token endpoint returned no access_token.")
        logger.debug("Obtained bearer token (cached for this run).")
        return token

    def _ensure_token(self) -> None:
        if self.token is None:
            self.token = self._fetch_token()

    def request(self, method: str, url: str, body: dict | None = None) -> tuple[int, dict]:
        """Issue a FHIR request, refreshing the token once on 401 (D6, SUB-3)."""
        self._ensure_token()
        encoded = json.dumps(body).encode("utf-8") if body is not None else None
        for attempt in range(2):
            req = urllib.request.Request(
                url, data=encoded, method=method,
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Accept": "application/fhir+json",
                    "Content-Type": "application/fhir+json",
                },
            )
            try:
                with urllib.request.urlopen(req) as resp:  # noqa: S310
                    raw = resp.read().decode("utf-8")
                    parsed = json.loads(raw) if raw else {}
                    return resp.status, parsed
            except urllib.error.HTTPError as exc:
                raw = exc.read().decode("utf-8", errors="replace")
                if exc.code == 401 and attempt == 0:
                    logger.debug("401 received; refreshing token and retrying once.")
                    self.token = self._fetch_token()
                    continue
                try:
                    parsed = json.loads(raw) if raw else {}
                except json.JSONDecodeError:
                    parsed = {"raw": raw}
                raise SubmissionError(exc.code, json.dumps(parsed)) from exc
            except urllib.error.URLError as exc:
                raise SubmissionError(0, f"Network error reaching {url}: {exc.reason}") from exc
        raise SubmissionError(401, "Authentication failed after token refresh.")

    def submit_transaction(self, bundle: dict) -> tuple[int, dict]:
        return self.request("POST", self.base, body=bundle)

    def submit_put(self, resource_type: str, resource_id: str, resource: dict) -> tuple[int, dict]:
        return self.request("PUT", f"{self.base}/{resource_type}/{resource_id}", body=resource)


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


@dataclass
class Pipeline:
    """Run-scoped processing context (one per execution)."""

    config: RunConfig
    version: str
    timestamp: str
    run_date: str
    dry_run: bool
    output_dir: str
    write_mirror: bool
    client: FhirClient | None
    collisions: CollisionTracker = field(default_factory=CollisionTracker)

    def _stamp_and_check(self, resource: dict, source_filename: str) -> None:
        """Stamp a top-level resource and register it with the collision tracker."""
        stamp_resource(resource, self.version, self.timestamp, source_filename)
        rtype = resource.get("resourceType")
        rid = resource.get("id")
        if rtype and rid:
            status = self.collisions.check(rtype, rid, resource)
            if status == "duplicate":
                logger.info("Dedup: %s/%s already persisted with identical content.",
                            rtype, rid)
        if self.client is not None:
            warn_on_absolute_references(resource, self.client.base)

    def process(self, data: dict, kind: str, source_filename: str,
                measure: str | None) -> FileOutcome:
        """Stamp, transform, and submit one parsed input by kind."""
        if kind == KIND_COLLECTION:
            return self._process_collection(data, source_filename, measure)
        if kind == KIND_MEASURE_REPORT:
            return self._process_measure_report(data, source_filename, measure)
        if kind == KIND_MESSAGE:
            return self._process_message(data, source_filename, measure)
        raise ValueError(f"Unsupported kind: {kind}")

    def _process_collection(self, bundle: dict, source_filename: str,
                            measure: str | None) -> FileOutcome:
        entries = bundle.get("entry", []) or []
        for entry in entries:
            resource = entry.get("resource")
            if resource is not None:
                self._stamp_and_check(resource, source_filename)
        txn = transform_collection_to_transaction(bundle)
        count = len(txn.get("entry", []))
        self._maybe_mirror(measure, source_filename, txn)
        if self.dry_run:
            logger.info("[dry-run] would POST transaction of %d PUT entries (%s).",
                        count, source_filename)
            return FileOutcome(source_filename, KIND_COLLECTION, "POST-transaction",
                               count, "succeeded", "dry-run")
        status, response = self.client.submit_transaction(txn)
        return self._txn_outcome(source_filename, count, status, response)

    def _process_measure_report(self, report: dict, source_filename: str,
                                measure: str | None) -> FileOutcome:
        self._stamp_and_check(report, source_filename)
        rid = report.get("id")
        self._maybe_mirror(measure, source_filename, report)
        if self.dry_run:
            logger.info("[dry-run] would PUT MeasureReport/%s (%s).", rid, source_filename)
            return FileOutcome(source_filename, KIND_MEASURE_REPORT,
                               f"PUT MeasureReport/{rid}", 1, "succeeded", "dry-run")
        status, response = self.client.submit_put("MeasureReport", rid, report)
        return self._put_outcome(source_filename, KIND_MEASURE_REPORT,
                                 f"PUT MeasureReport/{rid}", 1, status, response)

    def _process_message(self, bundle: dict, source_filename: str,
                         measure: str | None) -> FileOutcome:
        # Stamp the message Bundle's OWN meta; nested content is persisted as part of
        # the wrapper and is NOT registered with the collision tracker (D4b).
        bundle["meta"] = stamp(bundle.get("meta"), self.version, self.timestamp,
                               source_filename)
        rid = bundle.get("id")
        rtype = "Bundle"
        if rid:
            status = self.collisions.check(rtype, rid, bundle)
            if status == "duplicate":
                logger.info("Dedup: Bundle/%s already persisted with identical content.",
                            rid)
        self._maybe_mirror(measure, source_filename, bundle)
        if self.dry_run:
            logger.info("[dry-run] would PUT Bundle/%s (%s).", rid, source_filename)
            return FileOutcome(source_filename, KIND_MESSAGE, f"PUT Bundle/{rid}",
                               1, "succeeded", "dry-run")
        status, response = self.client.submit_put("Bundle", rid, bundle)
        return self._put_outcome(source_filename, KIND_MESSAGE, f"PUT Bundle/{rid}",
                                 1, status, response)

    def _maybe_mirror(self, measure: str | None, source_filename: str,
                      payload: dict) -> None:
        if self.write_mirror:
            mirror_output(self.output_dir, measure, self.run_date, source_filename, payload)

    def _txn_outcome(self, filename: str, count: int, status: int,
                     response: dict) -> FileOutcome:
        if 200 <= status < 300:
            return FileOutcome(filename, KIND_COLLECTION, "POST-transaction",
                               count, "succeeded", f"HTTP {status}")
        logger.error("Transaction rejected for %s (HTTP %d): %s", filename, status,
                     json.dumps(response))
        return FileOutcome(filename, KIND_COLLECTION, "POST-transaction", count,
                           "failed", f"HTTP {status}: {json.dumps(response)}")

    def _put_outcome(self, filename: str, kind: str, action: str, count: int,
                     status: int, response: dict) -> FileOutcome:
        if 200 <= status < 300:
            return FileOutcome(filename, kind, action, count, "succeeded", f"HTTP {status}")
        logger.error("Submission rejected for %s (HTTP %d): %s", filename, status,
                     json.dumps(response))
        return FileOutcome(filename, kind, action, count, "failed",
                           f"HTTP {status}: {json.dumps(response)}")


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
            summary.submitted += 1
            outcome = pipeline.process(data, kind, item.filename, item.measure)
        except CollisionError as exc:
            logger.error("Collision processing %s: %s", item.filename, exc)
            summary.failed += 1
            summary.record(FileOutcome(item.filename, kind, "collision", 0,
                                       "failed", str(exc)))
            continue
        except (SubmissionError, ValueError) as exc:
            logger.error("Failed processing %s: %s", item.filename, exc)
            summary.failed += 1
            summary.record(FileOutcome(item.filename, kind, "error", 0,
                                       "failed", str(exc)))
            continue

        summary.record(outcome)
        if outcome.status == "succeeded":
            summary.succeeded += 1
        elif outcome.status == "failed":
            summary.failed += 1

    _report_summary(summary, args.dry_run)
    return summary.exit_code


def _report_summary(summary: RunSummary, dry_run: bool) -> None:
    logger.info("=" * 60)
    logger.info("RunSummary%s", " [DRY-RUN]" if dry_run else "")
    for o in summary.outcomes:
        logger.info("  %-9s %-16s %-28s n=%-3d %s",
                    o.status, o.kind, o.action, o.resource_count,
                    o.filename + (f" — {o.detail}" if o.detail else ""))
    logger.info("-" * 60)
    logger.info("read=%d submitted=%d succeeded=%d failed=%d skipped=%d",
                summary.read, summary.submitted, summary.succeeded,
                summary.failed, summary.skipped)
    logger.info("exit_code=%d", summary.exit_code)
    logger.info("=" * 60)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
