"""server.validation_skip → `aidbox-validation-skip` request header on submissions.

Relaxes Aidbox ingestion-time validation per known-validation-issues.md
("Aidbox ingestion-time validation"). The header is per-request, so it is exercised
here by capturing the outgoing urllib Request rather than contacting a server.
"""

import unittest
import urllib.request

import process


class _FakeResp:
    status = 200

    def read(self):
        return b"{}"

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


# urllib.request.Request stores header keys via str.capitalize().
_SKIP_HEADER = "aidbox-validation-skip".capitalize()  # -> "Aidbox-validation-skip"

_SERVER = {
    "base_url": "https://fhir.example.org",
    "token_endpoint": "https://auth.example.org/token",
    "client_id": "x",
    "client_secret": "y",
}


class ValidationSkipHeaderTest(unittest.TestCase):
    def setUp(self):
        self.captured = []
        self._orig_urlopen = urllib.request.urlopen

        def fake_urlopen(req, *args, **kwargs):
            self.captured.append(req)
            return _FakeResp()

        urllib.request.urlopen = fake_urlopen

    def tearDown(self):
        urllib.request.urlopen = self._orig_urlopen

    def _client(self, skip):
        server = dict(_SERVER)
        if skip is not None:
            server["validation_skip"] = skip
        client = process.FhirClient(server)
        client.token = "tkn"  # pre-seed so no token fetch happens
        return client

    def _put(self, client):
        client.submit_put("Observation", "abc",
                          {"resourceType": "Observation", "id": "abc"})
        return next(r for r in self.captured if r.method == "PUT")

    def test_header_sent_when_configured(self):
        req = self._put(self._client(["reference"]))
        self.assertEqual(req.get_header(_SKIP_HEADER), "reference")

    def test_multiple_values_comma_joined(self):
        req = self._put(self._client(["reference", "terminology"]))
        self.assertEqual(req.get_header(_SKIP_HEADER), "reference,terminology")

    def test_no_header_by_default(self):
        req = self._put(self._client(None))
        self.assertIsNone(req.get_header(_SKIP_HEADER))

    def test_empty_list_sends_no_header(self):
        req = self._put(self._client([]))
        self.assertIsNone(req.get_header(_SKIP_HEADER))


if __name__ == "__main__":
    unittest.main()
