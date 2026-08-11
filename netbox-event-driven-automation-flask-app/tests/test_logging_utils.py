import unittest

from logging_utils import redact_payload


class PayloadRedactionTests(unittest.TestCase):
    def test_redacts_sensitive_nested_values(self):
        payload = {
            "name": "example-vm",
            "password": "unsafe",
            "nested": {"api_token_secret": "secret", "vmid": 101},
        }

        sanitized = redact_payload(payload)

        self.assertEqual(sanitized["password"], "***REDACTED***")
        self.assertEqual(sanitized["nested"]["api_token_secret"], "***REDACTED***")
        self.assertEqual(sanitized["nested"]["vmid"], 101)


if __name__ == "__main__":
    unittest.main()
