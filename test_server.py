import unittest
from unittest.mock import patch

import server


class ServerValidationTests(unittest.TestCase):
    @patch("server._is_public_address", return_value=True)
    def test_allows_federal_https_host(self, _public):
        server._validate_endpoint("https://api.nasa.gov/planetary/apod")

    def test_rejects_http(self):
        with self.assertRaises(ValueError):
            server._validate_endpoint("http://api.nasa.gov/planetary/apod")

    def test_rejects_non_federal_host(self):
        with self.assertRaises(ValueError):
            server._validate_endpoint("https://example.com/api")

    @patch("server._is_public_address", return_value=True)
    def test_rejects_caller_api_key(self, _public):
        with self.assertRaises(ValueError):
            server._request_json(
                "https://api.nasa.gov/planetary/apod",
                params={"api_key": "attacker-key"},
            )

    @patch("server._is_public_address", return_value=True)
    def test_rejects_endpoint_api_key(self, _public):
        with self.assertRaises(ValueError):
            server._request_json("https://api.nasa.gov/planetary/apod?api_key=bad")

if __name__ == "__main__":
    unittest.main()
