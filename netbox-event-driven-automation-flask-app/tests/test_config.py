import unittest

from config import AppConfig


class ConfigTests(unittest.TestCase):
    @staticmethod
    def config_payload():
        return {
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

    def test_legacy_node_is_accepted_as_default_node(self):
        config = AppConfig.model_validate(self.config_payload())

        self.assertEqual(config.proxmox_api_config.default_node, "pve-01")

    def test_log_level_is_case_insensitive(self):
        payload = self.config_payload()
        payload["log_level"] = "warning"

        config = AppConfig.model_validate(payload)

        self.assertEqual(config.log_level, "WARNING")

    def test_payload_logging_defaults_to_disabled_per_api(self):
        config = AppConfig.model_validate(self.config_payload())

        self.assertFalse(config.proxmox_api_config.debug_payloads)
        self.assertFalse(config.netbox_api_config.debug_payloads)

    def test_template_choice_set_has_default_name(self):
        config = AppConfig.model_validate(self.config_payload())

        self.assertEqual(
            config.netbox_api_config.proxmox_template_choice_set_name,
            "Proxmox templates",
        )

    def test_storage_choice_sets_have_default_names(self):
        config = AppConfig.model_validate(self.config_payload())

        self.assertEqual(
            config.netbox_api_config.proxmox_vm_storage_choice_set_name,
            "proxmox-vm-storage",
        )
        self.assertEqual(
            config.netbox_api_config.proxmox_lxc_storage_choice_set_name,
            "proxmox-lxc-storage",
        )


if __name__ == "__main__":
    unittest.main()
