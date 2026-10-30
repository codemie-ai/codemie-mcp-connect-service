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
    mask_user_context,
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


# Tests for mask_user_context()
class TestMaskUserContext:
    """Tests for mask_user_context() — defensive masking of the /bridge user_context object."""

    def test_keep_readable_keys_scalar_values_emitted_verbatim(self):
        """All eight keep-readable keys pass through unchanged for scalar values."""
        ctx = {
            "id": 42,
            "roles": "admin",
            "is_admin": True,
            "is_maintainer": False,
            "is_auditor": True,
            "user_type": "internal",
            "project_names": "proj-a",
            "admin_project_names": "proj-b",
        }
        assert mask_user_context(ctx) == ctx

    def test_keep_readable_keys_all_scalar_list_values_emitted_verbatim(self):
        """Keep-readable keys pass through for lists whose every element is a scalar."""
        ctx = {
            "roles": ["admin", "user"],
            "project_names": ["proj-a", "proj-b"],
            "admin_project_names": [],
            "id": [1, 2, 3],
        }
        assert mask_user_context(ctx) == {
            "roles": ["admin", "user"],
            "project_names": ["proj-a", "proj-b"],
            "admin_project_names": [],
            "id": [1, 2, 3],
        }

    def test_keep_readable_key_with_dict_value_is_redacted(self):
        """A keep-readable key whose value is a dict is redacted, not emitted."""
        assert mask_user_context({"roles": {"name": "admin"}}) == {"roles": REDACTED_VALUE}

    def test_keep_readable_key_with_list_containing_dict_is_redacted(self):
        """A keep-readable list with any non-scalar element is redacted wholesale."""
        assert mask_user_context({"project_names": ["a", {"x": 1}]}) == {"project_names": REDACTED_VALUE}

    def test_username_multi_char_is_first_char_plus_suffix(self):
        """username longer than one char becomes first char plus a fixed suffix."""
        assert mask_user_context({"username": "jdoe"}) == {"username": "j***"}

    def test_username_single_char_is_redacted(self):
        """username shorter than two chars is redacted, leaking no length."""
        assert mask_user_context({"username": "j"}) == {"username": REDACTED_VALUE}

    def test_username_none_is_redacted(self):
        """username of None is redacted."""
        assert mask_user_context({"username": None}) == {"username": REDACTED_VALUE}

    def test_username_dict_is_redacted(self):
        """username of a non-string type is redacted."""
        assert mask_user_context({"username": {"a": 1}}) == {"username": REDACTED_VALUE}

    def test_pii_keys_are_redacted(self):
        """email, name, picture and extra_attributes are redacted wholesale."""
        ctx = {
            "email": "jdoe@example.com",
            "name": "John Doe",
            "picture": "https://example.com/jdoe.png",
            "extra_attributes": {"department": "engineering"},
        }
        assert mask_user_context(ctx) == {
            "email": REDACTED_VALUE,
            "name": REDACTED_VALUE,
            "picture": REDACTED_VALUE,
            "extra_attributes": REDACTED_VALUE,
        }

    def test_unrecognised_key_is_redacted(self):
        """A key not on the allowlist is redacted by default."""
        assert mask_user_context({"some_new_field": "value"}) == {"some_new_field": REDACTED_VALUE}

    def test_nested_dict_value_redacted_wholesale_not_traversed(self):
        """A nested dict value is redacted wholesale, never traversed recursively."""
        assert mask_user_context({"details": {"id": 1, "roles": ["admin"]}}) == {"details": REDACTED_VALUE}

    def test_none_input_returns_none(self):
        """None in, None out."""
        assert mask_user_context(None) is None

    def test_empty_dict_returns_empty_dict(self):
        """Empty dict in, empty dict out."""
        assert mask_user_context({}) == {}

    def test_input_is_not_mutated(self):
        """mask_user_context is pure — it does not mutate its input."""
        original = {
            "username": "jdoe",
            "email": "jdoe@example.com",
            "roles": ["admin", "user"],
        }
        masked = mask_user_context(original)

        assert original == {
            "username": "jdoe",
            "email": "jdoe@example.com",
            "roles": ["admin", "user"],
        }
        assert masked is not original

    def test_list_value_is_copied_not_referenced(self):
        """An emitted list is a copy, so later mutation cannot reach through it."""
        roles = ["admin", "user"]
        masked = mask_user_context({"roles": roles})

        assert masked["roles"] == roles
        assert masked["roles"] is not roles
