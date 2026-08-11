import unittest

from config import AppConfig


class ConfigTests(unittest.TestCase):
    def test_legacy_node_is_accepted_as_default_node(self):
        config = AppConfig.model_validate(
            {
                "proxmox_api_config": {
                    "api_host": "pve.example.test",
                    "api_user": "automation@pve",
                    "api_token_id": "token",
                    "api_token_secret": "secret",
                    "node": "pve-01",
                },
                "netbox_api_config": {
                    "api_host": "netbox.example.test",
                    "api_token": "secret",
                },
            }
        )

        self.assertEqual(config.proxmox_api_config.default_node, "pve-01")


if __name__ == "__main__":
    unittest.main()
