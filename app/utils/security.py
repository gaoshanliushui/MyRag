"""
Security Utilities - API key generation and validation
"""

import hashlib
import os
import secrets
import string
from typing import Optional

from app.utils.logging import get_logger

logger = get_logger("utils.security")


def generate_api_key(length: int = 32) -> str:
    """
    Generate a secure random API key.

    Args:
        length: Length of the API key (default: 32)

    Returns:
        Generated API key
    """
    # Use system's cryptographically secure random generator
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def validate_api_key(api_key: Optional[str]) -> bool:
    """
    Validate an API key format.

    Args:
        api_key: API key to validate

    Returns:
        True if valid, False otherwise
    """
    if not api_key:
        return False

    # Basic validation - length and character set
    if len(api_key) < 16:
        logger.warning("API key too short")
        return False

    allowed_chars = set(string.ascii_letters + string.digits)
    if not all(c in allowed_chars for c in api_key):
        logger.warning("API key contains invalid characters")
        return False

    return True

def hash_api_key(api_key: str) -> str:
    """
    Hash an API key for secure storage.

    Uses SHA-256 for consistent hashing.

    Args:
        api_key: API key to hash

    Returns:
        Hex digest of the hashed API key
    """
    return hashlib.sha256(api_key.encode()).hexdigest()