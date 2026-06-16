#!/usr/bin/env python3
"""Shared primitives for the ecr-fhir-processor tools.

Extracted from ``process.py`` so that both the eCR processor (``process.py``) and the
ViewDefinition publish/materialize step (``publish_views.py``) reuse one OAuth2 FHIR
client, one config loader/validator, one logging setup, and one per-item outcome/summary
model — no duplication, no new runtime dependency (constitution: Zero-Dependency Runtime,
Single-File Simplicity's named "FHIR client logic, validation orchestration" boundary).

Python 3 standard library only. See specs/002-patient-viewdefinition/research.md R1.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

# --------------------------------------------------------------------------- #
# Shared constants
# --------------------------------------------------------------------------- #

#: Required, non-empty server fields (rejected if still a YOUR_* placeholder).
REQUIRED_SERVER_FIELDS = ("base_url", "token_endpoint", "client_id", "client_secret")

#: Prefix marking the example-config placeholders that must be replaced (FR-010).
PLACEHOLDER_PREFIX = "YOUR_"

#: Default config-relative paths (overridable by config.paths and CLI flags).
DEFAULT_PATHS = {"input_dir": "input", "output_dir": "output", "log_dir": "log"}

#: Shared logger. Both entry points configure and write through this single named
#: logger via :func:`setup_logging`.
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
class FileOutcome:
    """Per-file result folded into the RunSummary."""

    filename: str
    kind: str
    action: str
    resource_count: int
    status: str  # succeeded | failed | skipped
    detail: str = ""
    resource_type: str | None = None  # FHIR type; derived from `action` for submissions

    def __post_init__(self) -> None:
        # Submission actions are "PUT <Type>/<id>"; file-level skip/error actions
        # ("skip", "error") carry no resource type. Derive it once here so the run
        # summary can stratify resource counts by type (FHIR ids never contain "/").
        if self.resource_type is None and self.action.startswith("PUT "):
            self.resource_type = self.action[len("PUT "):].split("/", 1)[0]


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


class SubmissionError(Exception):
    """A FHIR submission returned a non-2xx status (carries the server payload)."""

    def __init__(self, status: int, detail: str):
        super().__init__(f"HTTP {status}: {detail}")
        self.status = status
        self.detail = detail


# --------------------------------------------------------------------------- #
# Logging (T006, D9, FR-013)
# --------------------------------------------------------------------------- #


def setup_logging(log_dir: str, verbose: bool, prefix: str = "ecr-fhir-processor") -> Path:
    """Configure dual logging: console + timestamped audit file under ``log_dir``.

    ``--verbose`` raises the console handler to DEBUG; the file is always detailed.
    ``prefix`` names the audit-log file (one family per tool, e.g. ``publish-views``).
    Returns the path of the log file written.
    """
    log_path_dir = Path(log_dir)
    log_path_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%dt%H%M%S")
    log_file = log_path_dir / f"{prefix}_{stamp}.log"

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

    skip = server.get("validation_skip")
    if skip is not None and (
        not isinstance(skip, list) or not all(isinstance(s, str) for s in skip)
    ):
        errors.append(
            'Config field server.validation_skip must be a list of strings '
            '(e.g. ["reference"]).'
        )
    return errors


# --------------------------------------------------------------------------- #
# FHIR client / OAuth2 (T014, T016, T019 — US1; fhir-submission contract)
# --------------------------------------------------------------------------- #


class FhirClient:
    """Minimal OAuth2 client-credentials FHIR client (urllib only, D6)."""

    def __init__(self, server: dict):
        self.server = server
        self.base = (server.get("base_url") or "").rstrip("/")
        self.token: str | None = None
        # Optional Aidbox validation relaxation (config server.validation_skip, e.g.
        # ["reference"]). When set, every submission carries the `aidbox-validation-skip`
        # header so Aidbox bypasses the named validation pass(es). See
        # known-validation-issues.md "Aidbox ingestion-time validation". Empty/absent =
        # no header = full validation (default).
        self.validation_skip: list[str] = list(server.get("validation_skip") or [])
        if self.validation_skip:
            logger.info(
                "Aidbox validation relaxation active: aidbox-validation-skip: %s",
                ",".join(self.validation_skip),
            )

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
            headers = {
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/fhir+json",
                "Content-Type": "application/fhir+json",
            }
            if self.validation_skip:
                headers["aidbox-validation-skip"] = ",".join(self.validation_skip)
            req = urllib.request.Request(
                url, data=encoded, method=method, headers=headers,
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

    def submit_put(self, resource_type: str, resource_id: str, resource: dict) -> tuple[int, dict]:
        """Persist a single resource via update-in-place ``PUT`` by id (D2, SUB-1)."""
        return self.request("PUT", f"{self.base}/{resource_type}/{resource_id}", body=resource)
