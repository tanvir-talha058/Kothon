import unittest

import keyring
from keyring.backends.fail import Keyring as FailKeyring

import secrets_store


class InMemoryKeyring(keyring.backend.KeyringBackend):
    priority = 1

    def __init__(self):
        self._store = {}

    def get_password(self, service, username):
        return self._store.get((service, username))

    def set_password(self, service, username, password):
        self._store[(service, username)] = password

    def delete_password(self, service, username):
        if (service, username) not in self._store:
            raise keyring.errors.PasswordDeleteError("not found")
        del self._store[(service, username)]


class SecretsStoreTests(unittest.TestCase):
    def setUp(self):
        self._orig = keyring.get_keyring()
        keyring.set_keyring(InMemoryKeyring())

    def tearDown(self):
        keyring.set_keyring(self._orig)

    def test_set_get_has_delete(self):
        self.assertFalse(secrets_store.has_key("openai"))
        self.assertTrue(secrets_store.set_key("openai", "sk-123"))
        self.assertEqual(secrets_store.get_key("openai"), "sk-123")
        self.assertTrue(secrets_store.has_key("openai"))
        self.assertTrue(secrets_store.delete_key("openai"))
        self.assertFalse(secrets_store.has_key("openai"))
        self.assertIsNone(secrets_store.get_key("openai"))

    def test_empty_key_clears(self):
        secrets_store.set_key("gemini", "abc")
        self.assertTrue(secrets_store.set_key("gemini", "   "))
        self.assertFalse(secrets_store.has_key("gemini"))

    def test_blank_provider_rejected(self):
        self.assertFalse(secrets_store.set_key("", "x"))
        self.assertIsNone(secrets_store.get_key(""))

    def test_delete_missing_is_ok(self):
        self.assertTrue(secrets_store.delete_key("anthropic"))


class UnavailableBackendTests(unittest.TestCase):
    """If the keyring backend can't store secrets, the app stays usable."""

    def setUp(self):
        self._orig = keyring.get_keyring()
        keyring.set_keyring(FailKeyring())

    def tearDown(self):
        keyring.set_keyring(self._orig)

    def test_has_key_false_when_unavailable(self):
        self.assertFalse(secrets_store.has_key("openai"))
        self.assertIsNone(secrets_store.get_key("openai"))
        self.assertFalse(secrets_store.set_key("openai", "x"))


if __name__ == "__main__":
    unittest.main()
