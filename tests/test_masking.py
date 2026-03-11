# Copyright 2026 EPAM Systems, Inc. ("EPAM")
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tests for sensitive data masking utilities."""

import logging

from src.mcp_connect.utils.masking import (
    REDACTED_VALUE,
    SENSITIVE_PATTERNS,
    is_sensitive_key,
    mask_dict_values,
    mask_sensitive_headers,
)


# Tests for is_sensitive_key()
def test_is_sensitive_key_matches_authorization_case_insensitive():
    """Test authorization pattern matching (case-insensitive)."""
    assert is_sensitive_key("Authorization") is True
    assert is_sensitive_key("authorization") is True
    assert is_sensitive_key("AUTHORIZATION") is True


def test_is_sensitive_key_matches_api_key_variants():
    """Test api-key pattern with hyphen/underscore variants."""
    assert is_sensitive_key("api-key") is True
    assert is_sensitive_key("api_key") is True
    assert is_sensitive_key("apikey") is True
    assert is_sensitive_key("x-api-key") is True
    assert is_sensitive_key("API-KEY") is True
    assert is_sensitive_key("X-API-Key") is True


def test_is_sensitive_key_matches_all_patterns():
    """Test all sensitive patterns."""
    sensitive_keys = [
        "authorization",
        "api-key",
        "x-api-key",
        "token",
        "secret",
        "password",
        "bearer",
        "auth",
        "access-token",
        "access_token",
        "refresh-token",
        "refresh_token",
        "x-auth-token",
    ]
    for key in sensitive_keys:
        assert is_sensitive_key(key) is True, f"Expected {key} to be sensitive"


def test_is_sensitive_key_non_sensitive():
    """Test non-sensitive keys return False."""
    non_sensitive = ["content-type", "accept", "host", "user-agent", "connection"]
    for key in non_sensitive:
        assert is_sensitive_key(key) is False, f"Expected {key} to be non-sensitive"


# Tests for mask_dict_values() with mask_all=True
def test_mask_dict_values_mask_all_true():
    """Test masking all values with mask_all=True."""
    data = {"API_KEY": "secret123", "TOKEN": "abc456", "HOST": "example.com"}
    masked = mask_dict_values(data, mask_all=True)

    assert masked == {"API_KEY": REDACTED_VALUE, "TOKEN": REDACTED_VALUE, "HOST": REDACTED_VALUE}
    # Verify original unchanged (immutability)
    assert data == {"API_KEY": "secret123", "TOKEN": "abc456", "HOST": "example.com"}


def test_mask_dict_values_mask_all_true_empty():
    """Test masking empty dict with mask_all=True returns empty dict."""
    assert mask_dict_values({}, mask_all=True) == {}


# Tests for mask_dict_values() with mask_all=False (selective)
def test_mask_dict_values_mask_all_false_selective():
    """Test selective masking with mask_all=False."""
    data = {
        "authorization": "Bearer xyz",
        "content-type": "application/json",
        "token": "abc",
        "host": "example.com",
    }
    masked = mask_dict_values(data, mask_all=False)

    assert masked["authorization"] == REDACTED_VALUE
    assert masked["token"] == REDACTED_VALUE
    assert masked["content-type"] == "application/json"  # Non-sensitive unmasked
    assert masked["host"] == "example.com"  # Non-sensitive unmasked


def test_mask_dict_values_mask_all_false_only_sensitive():
    """Test selective masking only affects sensitive keys."""
    data = {"secret": "my-secret", "password": "my-pass", "username": "john"}
    masked = mask_dict_values(data, mask_all=False)

    assert masked["secret"] == REDACTED_VALUE
    assert masked["password"] == REDACTED_VALUE
    assert masked["username"] == "john"  # Non-sensitive preserved


def test_mask_dict_values_mask_all_false_empty():
    """Test selective masking on empty dict returns empty dict."""
    assert mask_dict_values({}, mask_all=False) == {}


# Tests for immutability
def test_mask_dict_values_immutability_mask_all_true():
    """Test mask_all=True doesn't mutate original dict."""
    original = {"secret": "value123", "other": "data"}
    masked = mask_dict_values(original, mask_all=True)

    assert original["secret"] == "value123"  # Original unchanged
    assert original["other"] == "data"
    assert masked["secret"] == REDACTED_VALUE
    assert masked["other"] == REDACTED_VALUE
    assert masked is not original  # Different objects


def test_mask_dict_values_immutability_mask_all_false():
    """Test mask_all=False doesn't mutate original dict."""
    original = {"authorization": "Bearer xyz", "host": "example.com"}
    masked = mask_dict_values(original, mask_all=False)

    assert original["authorization"] == "Bearer xyz"  # Original unchanged
    assert original["host"] == "example.com"
    assert masked["authorization"] == REDACTED_VALUE
    assert masked["host"] == "example.com"
    assert masked is not original  # Different objects


# Tests for mask_sensitive_headers()
def test_mask_sensitive_headers_selective_masking():
    """Test mask_sensitive_headers wrapper function."""
    headers = {
        "Authorization": "Bearer token123",
        "Content-Type": "application/json",
        "X-API-Key": "secret456",
        "Accept": "application/json",
    }
    masked = mask_sensitive_headers(headers)

    assert masked["Authorization"] == REDACTED_VALUE
    assert masked["X-API-Key"] == REDACTED_VALUE
    assert masked["Content-Type"] == "application/json"
    assert masked["Accept"] == "application/json"


def test_mask_sensitive_headers_masks_authorization():
    """Test authorization header masking."""
    headers = {"Authorization": "Bearer token"}
    masked = mask_sensitive_headers(headers)
    assert masked["Authorization"] == REDACTED_VALUE


def test_mask_sensitive_headers_masks_api_key_case_insensitive():
    """Test API-Key header masking (case-insensitive)."""
    headers = {"API-Key": "abc123"}
    masked = mask_sensitive_headers(headers)
    assert masked["API-Key"] == REDACTED_VALUE


def test_mask_sensitive_headers_preserves_non_sensitive_values():
    """Test non-sensitive headers preserved."""
    headers = {"Content-Type": "application/json"}
    masked = mask_sensitive_headers(headers)
    assert masked["Content-Type"] == "application/json"


def test_mask_sensitive_headers_handles_empty_input():
    """Test empty dict returns empty dict."""
    masked = mask_sensitive_headers({})
    assert masked == {}


def test_mask_sensitive_headers_handles_none_input():
    """Test None input returns empty dict."""
    masked = mask_sensitive_headers(None)
    assert masked == {}


# Integration test: verify credentials masked in logs
def test_integration_no_credentials_in_logs(caplog):
    """Integration test: verify credentials masked in actual logs."""

    from src.mcp_connect.utils.masking import mask_dict_values

    # Create logger that works with caplog
    logger = logging.getLogger("test_masking_integration")
    logger.setLevel(logging.DEBUG)

    # Log with test credential
    test_data = {
        "API_KEY": "test-secret-123",
        "TOKEN": "sensitive-token-456",
        "HOST": "example.com",
    }

    with caplog.at_level(logging.DEBUG):
        logger.debug("Test data: %s", mask_dict_values(test_data, mask_all=True))

    # Verify log contains masked values, NOT actual credentials
    assert len(caplog.records) > 0
    log_message = caplog.records[-1].message
    assert REDACTED_VALUE in log_message
    assert "test-secret-123" not in log_message  # CRITICAL: no actual credential
    assert "sensitive-token-456" not in log_message  # CRITICAL: no actual credential


def test_integration_selective_masking_in_logs(caplog):
    """Integration test: verify selective masking preserves non-sensitive data."""

    from src.mcp_connect.utils.masking import mask_dict_values

    # Create logger that works with caplog
    logger = logging.getLogger("test_masking_integration_selective")
    logger.setLevel(logging.DEBUG)

    # Log with mixed sensitive and non-sensitive data
    test_data = {
        "authorization": "Bearer secret-token",
        "content-type": "application/json",
        "x-api-key": "my-api-key",
        "host": "api.example.com",
    }

    with caplog.at_level(logging.DEBUG):
        logger.debug("Headers: %s", mask_dict_values(test_data, mask_all=False))

    # Verify sensitive values masked, non-sensitive preserved
    assert len(caplog.records) > 0
    log_message = caplog.records[-1].message
    assert REDACTED_VALUE in log_message
    assert "secret-token" not in log_message  # Sensitive masked
    assert "my-api-key" not in log_message  # Sensitive masked
    assert "application/json" in log_message  # Non-sensitive preserved
    assert "api.example.com" in log_message  # Non-sensitive preserved


# Test SENSITIVE_PATTERNS regex constant
def test_sensitive_patterns_regex_constant():
    """Test SENSITIVE_PATTERNS regex is properly defined."""
    import re

    assert isinstance(SENSITIVE_PATTERNS, re.Pattern)
    assert SENSITIVE_PATTERNS.flags & re.IGNORECASE  # Verify case-insensitive flag
