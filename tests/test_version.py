"""T022 [US2]: git version derivation + 'unknown' fallback (D5, FR-006)."""

import unittest
from unittest import mock

import process


class VersionTest(unittest.TestCase):
    def test_returns_git_describe_output(self):
        fake = mock.Mock(returncode=0, stdout="v1.2.0-3-gabc123\n")
        with mock.patch("process.subprocess.run", return_value=fake):
            self.assertEqual(process.derive_version(), "v1.2.0-3-gabc123")

    def test_fallback_unknown_on_nonzero(self):
        fake = mock.Mock(returncode=128, stdout="")
        with mock.patch("process.subprocess.run", return_value=fake):
            self.assertEqual(process.derive_version(), "unknown")

    def test_fallback_unknown_when_git_missing(self):
        with mock.patch("process.subprocess.run", side_effect=FileNotFoundError):
            self.assertEqual(process.derive_version(), "unknown")

    def test_timestamp_has_offset(self):
        ts = process.processing_timestamp()
        self.assertTrue(ts.endswith("+00:00") or "+" in ts[10:] or ts[10:].count("-") >= 1)
        # ISO-8601 parseable
        from datetime import datetime
        datetime.fromisoformat(ts)


if __name__ == "__main__":
    unittest.main()
