"""T027 [US3]: fail-fast config validation (FR-010, D7, cli contract)."""

import unittest

import process


def _config(server):
    return process.RunConfig(software={}, server=server, ig_versions={},
                             paths=dict(process.DEFAULT_PATHS), raw={})


GOOD_SERVER = {
    "base_url": "https://fhir.example.org",
    "token_endpoint": "https://auth.example.org/token",
    "client_id": "real-id",
    "client_secret": "real-secret",
}


class ConfigValidationTest(unittest.TestCase):
    def test_valid_server_passes(self):
        self.assertEqual(process.validate_config(_config(GOOD_SERVER), dry_run=False), [])

    def test_missing_field_named(self):
        server = dict(GOOD_SERVER)
        del server["client_secret"]
        errors = process.validate_config(_config(server), dry_run=False)
        self.assertTrue(any("server.client_secret" in e for e in errors))

    def test_empty_field_named(self):
        server = dict(GOOD_SERVER, base_url="   ")
        errors = process.validate_config(_config(server), dry_run=False)
        self.assertTrue(any("server.base_url" in e for e in errors))

    def test_placeholder_rejected(self):
        server = dict(GOOD_SERVER, client_id="YOUR_CLIENT_ID")
        errors = process.validate_config(_config(server), dry_run=False)
        self.assertTrue(any("server.client_id" in e and "placeholder" in e
                            for e in errors))

    def test_dry_run_skips_server_requirements(self):
        placeholders = {k: process.PLACEHOLDER_PREFIX + k.upper()
                        for k in process.REQUIRED_SERVER_FIELDS}
        self.assertEqual(process.validate_config(_config(placeholders), dry_run=True), [])


if __name__ == "__main__":
    unittest.main()
