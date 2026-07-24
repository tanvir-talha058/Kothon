"""Secure storage for cloud-provider API keys.

Keys are kept in the Windows Credential Manager via ``keyring`` — never in the
plaintext ``settings.json`` and never returned to the UI. Each provider id is a
separate credential under the ``Kothon`` service.

All functions degrade quietly: if the keyring backend is unavailable the app
stays usable in offline mode (has_key just reports False).
"""
from __future__ import annotations

import keyring

_SERVICE = "Kothon"


def set_key(provider: str, key: str) -> bool:
    """Store (or overwrite) the API key for a provider. Empty key clears it."""
    provider = (provider or "").strip()
    if not provider:
        return False
    key = (key or "").strip()
    try:
        if not key:
            return delete_key(provider)
        keyring.set_password(_SERVICE, provider, key)
        return True
    except Exception:
        return False


def get_key(provider: str) -> str | None:
    """Return the stored API key for a provider, or None if unset/unavailable."""
    provider = (provider or "").strip()
    if not provider:
        return None
    try:
        return keyring.get_password(_SERVICE, provider)
    except Exception:
        return None


def delete_key(provider: str) -> bool:
    """Remove a provider's stored key. Returns True if the store is now clear."""
    provider = (provider or "").strip()
    if not provider:
        return False
    try:
        keyring.delete_password(_SERVICE, provider)
    except keyring.errors.PasswordDeleteError:
        pass  # nothing stored — already clear
    except Exception:
        return False
    return True


def has_key(provider: str) -> bool:
    """Whether a non-empty key is stored for the provider."""
    return bool(get_key(provider))
