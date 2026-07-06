"""FR-013 audit: every applied remediation is documented, and vice-versa (SC-003).

Makes "an undocumented remediation is a defect" a deterministic check against the
`REMEDIATIONS` registry rather than markdown prose-scraping. The two-way invariant:

  runtime remediations ⊆ REMEDIATIONS registry ⊆ documented `REMEDIATION:` markers

(a) every registry key has a `REMEDIATION: <key>` marker line in known-validation-issues.md
    → no applied remediation is undocumented; and
(b) every `REMEDIATION: <key>` marker in the doc maps to a registry key
    → no stale/orphan marker.

The `REMEDIATION:` marker is distinct from the `PATTERN:` lines consumed by
scripts/validate.sh (the HL7 gate) and is read only by this audit.
"""

import re
import unittest

from fhir_common import REMEDIATIONS
from tests import REPO_ROOT

DOC = REPO_ROOT / "known-validation-issues.md"
MARKER = re.compile(r"^REMEDIATION:\s*(\S+)\s*$", re.MULTILINE)


class RemediationDocAuditTest(unittest.TestCase):
    def setUp(self):
        self.text = DOC.read_text(encoding="utf-8")
        self.documented = set(MARKER.findall(self.text))

    def test_every_registry_key_is_documented(self):
        missing = REMEDIATIONS - self.documented
        self.assertEqual(
            missing, set(),
            f"Applied remediation(s) with no REMEDIATION: marker in {DOC.name}: {missing}")

    def test_no_orphan_documented_markers(self):
        orphan = self.documented - set(REMEDIATIONS)
        self.assertEqual(
            orphan, set(),
            f"Stale REMEDIATION: marker(s) in {DOC.name} not in the registry: {orphan}")

    def test_registry_and_docs_are_exactly_equal(self):
        self.assertEqual(self.documented, set(REMEDIATIONS))


if __name__ == "__main__":
    unittest.main()
