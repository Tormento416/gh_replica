import unittest

from hyrlink_platform.cli import workos_config_status


class WorkOSConfigTests(unittest.TestCase):
    def test_only_presence_is_returned(self):
        result = workos_config_status({"WORKOS_CLIENT_ID": "client_example", "WORKOS_API_KEY": "sensitive-value"})
        self.assertEqual(result["WORKOS_CLIENT_ID"], "set")
        self.assertEqual(result["WORKOS_API_KEY"], "set")
        self.assertEqual(result["WORKOS_ISSUER"], "not set")
        self.assertNotIn("sensitive-value", str(result))

    def test_blank_values_are_not_set(self):
        result = workos_config_status({"WORKOS_API_KEY": "   "})
        self.assertEqual(result["WORKOS_API_KEY"], "not set")


if __name__ == "__main__":
    unittest.main()
