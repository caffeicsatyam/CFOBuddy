import re


def user_storage_key(username: object) -> str:
    """Return a filesystem-safe folder key for user-scoped data."""
    key = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(username or "admin")).strip("._")
    return key or "admin"
