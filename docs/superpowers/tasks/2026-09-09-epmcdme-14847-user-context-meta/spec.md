# EPMCDME-14847 — Forward `user_context` to MCP tools as `_meta`

Sub-task of EPMCDME-13260. Repository: `codemie-mcp-connect-service`.

## Problem

Downstream MCP tools receive only an opaque `user_id`. The parent story needs them to also see the
authenticated user's non-sensitive profile — email, roles, project access — so they can apply RBAC,
personalise, and record audit trails without calling back into CodeMie.

`/bridge` blocks this twice. It *rejects* the field, because `BridgeRequestBody` sets `extra="forbid"`
(`models/request.py:27`) — the rejection that caused EPMCDME-13546 and made the backend strip
`user_context`. And even once accepted the field would go nowhere: `/bridge` does not forward the body
verbatim, it parses `method` + `params` and makes a typed SDK call at `client/methods.py:102`, so the
value must be threaded down to it explicitly.

## Approach

**Contract (settled with the backend team; not re-opened).** The backend sends `user_context` as a
plain top-level field and knows nothing about MCP `_meta`. This service owns the translation,
forwarding it as `_meta` under the namespaced key `codemie.ai/user-context`, on `tools/call` only.
Tools read `params._meta["codemie.ai/user-context"]`; servers that ignore `_meta` are unaffected —
that is the backward-compatibility story. Scope is `tools/call` only because `ClientSession.call_tool`
in the pinned `mcp` 1.30.0 takes a keyword-only `meta` while `list_tools` has no such parameter.

**Model.** Add `user_context: dict[str, Any] | None` to `BridgeRequestBody` (`models/request.py:24`).
It stays an opaque dict rather than a typed model: the backend's profile field set drifts, and a
permissive dict means this service never needs a lockstep release. `extra="forbid"` stays — one entry
is added to the allow-list, validation is not loosened. The 400-not-422 rejection of other unknown
fields depends on both the model config and the `extra_forbidden` branch at `main.py:218`; both stay
intact.

**Threading.** A generic `meta` parameter is threaded through the six functions between
`bridge_endpoint` (`routes.py:241`) and `methods.py:102`, across both branches: cached
(`routes.py:162` → `invoke_with_timeout` `manager.py:39`) and single-usage (`routes.py:122` →
`execute_single_usage_request` `single_usage.py:50` → one of `single_usage.py:114`, `:197`, `:262`).
`managed.py` is not on this path and is untouched. `invoke_mcp_method` (`methods.py:54`) takes a
`meta` dict, never a `user_context` — the route layer builds the namespaced key, keeping the MCP layer
decoupled and reusable for future `_meta` needs. The kwarg reaches `session.call_tool` **only when a
value is present**, so the two-positional call shape pinned by `test_mcp_methods.py:94` and its three
siblings stays valid and the field-absent path is byte-identical to today.

**Inert by construction.** `generate_cache_key` (`cache.py:223-229`), `apply_substitutions`
(`substitution.py:82`) and `extract_request_context` are explicit field allowlists, so the new field
cannot leak into any of them. The cache-key exclusion is deliberate — `user_context` is
per-invocation, and keying on it would give every user a private cached client and destroy reuse. It
is unpinned by any test today, so this adds the first negative cache-key test.

## Masking policy

Real values on the wire; masked values in this service's logs (the backend masks its own separately).
A dedicated function in `utils/masking.py` owns this. `SENSITIVE_PATTERNS` (`masking.py:22`) is **not**
widened — it feeds `_mask_params_recursive` over arbitrary tool arguments, where `name` is a common
legitimate key.

The function is defensive rather than an allowlist of PII names: it emits a small known-safe set and
redacts *everything else*, so any field the backend adds later is masked by default.

```python
def mask_user_context(user_context: dict[str, Any] | None) -> dict[str, Any] | None:
    """Mask a user-context object for logging. Pure; returns a new dict."""
```

Rules apply to top-level keys only — nested containers are **replaced wholesale, never traversed**:

- **Keep readable:** `id`, `roles`, `is_admin`, `is_maintainer`, `is_auditor`, `user_type`,
  `project_names`, `admin_project_names`, so an authorization failure stays diagnosable without
  leaking identity.
- **Type guard on that set.** A keep-readable key is emitted verbatim only if its value is a scalar
  (`str`/`int`/`float`/`bool`/`None`) or a list whose every element is a scalar. If the backend ever
  sends one of these keys as a dict, or a list containing dicts, it is redacted instead. The allowlist
  must not be widenable by a type change originating outside this service.
- **Partial:** `username` → first character plus a fixed `***` (`jdoe` → `j***`). Fixed width, so no
  length leaks. A non-`str`, or shorter than 2 characters, is redacted fully. This is the repository's
  first partial-redaction primitive — `masking.py` today holds only all-or-nothing flat
  `dict[str, str]` maskers, so expect a new helper rather than reuse.
- **Everything else → `REDACTED_VALUE`** (`masking.py:27`): `email`, `name`, `picture`,
  `extra_attributes`, and every unrecognised key, nested dict or nested list.

The masker is pure and must not mutate its input, matching the immutability tests in
`tests/test_masking.py`.

**Two log sites, both masked, both newly covered:**

1. **One INFO line at the route layer**, where the namespaced key is built, carrying the masked object
   only. On by default in production: the story's audit/RBAC motivation makes "which identity ran this
   tool" the first incident question. `methods.py` gains no user-context knowledge.
2. **The `DEBUG_LOG_BRIDGE_PAYLOAD` block** (`routes.py:276-283`), which masks `request_headers` and
   `env` by hardcoded key name and would dump any new top-level field in the clear. Its flag is read
   once at import (`routes.py:49`), making the block untestable as written; it moves to a small helper
   read per request. This is a deliberate, if small, behaviour change to an existing production path —
   the env var becomes dynamic and takes effect without a restart. The block has zero coverage today,
   so the new test is the first thing ever to exercise it.

## Behaviour decisions

- An empty `user_context` (`{}`) is treated as **absent**; no `meta` is passed. Follows the truthiness
  convention at `substitution.py:129`.
- A `user_context` on a non-`tools/call` method is **silently ignored**, not warned about, consistent
  with how the codebase handles inapplicable optional fields.
- The EPMCDME-11351 `McpError` → `isError` mapping (`methods.py:103-117`) is untouched.

## Acceptance criteria

- `POST /bridge` with a body containing `user_context` returns no 4xx.
- A body with any *other* unknown field is still rejected 400 with `type == "extra_forbidden"`.
- `tools/call` forwards the value as `_meta` under `codemie.ai/user-context`.
- `tools/list` and every other method do not forward it.
- Two requests differing only by `user_context` produce the same cache key.
- Omitting the field yields a `session.call_tool` call with no `meta` kwarg — identical to current main.
- A `user_context` of `{}` is treated as absent; no `meta` kwarg is passed.
- Both modes (cached and `single_usage: true`) and all three transports (stdio, streamable-http, sse) forward it.
- `mask_user_context` emits `id`, `roles`, `is_admin`, `is_maintainer`, `is_auditor`, `user_type`, `project_names`, `admin_project_names` verbatim.
- `mask_user_context` redacts a keep-readable key whose value is a dict, or a list containing a non-scalar.
- `mask_user_context` renders `username` as first character + `***`, redacting fully when under 2 characters or not a string.
- `mask_user_context` redacts `email`, `name`, `picture`, `extra_attributes`, and any unrecognised key.
- `mask_user_context` does not mutate its input and returns `None` for `None`.
- The route-layer INFO line carries the masked object, never the raw one.
- The `DEBUG_LOG_BRIDGE_PAYLOAD` dump carries the masked object, and the flag is honoured per request without a restart.
- `SENSITIVE_PATTERNS` is unchanged and existing `tests/test_masking.py` non-sensitive-key assertions still pass.
- `README.md` documents the field.
- Gates green: `ruff format`, `ruff check`, `mypy src/`, `black --check`, `pytest`.

## Non-goals

- `_meta` on `tools/list` or any method other than `tools/call`.
- Any backend change — that is EPMCDME-13260.
- Filtering or interpreting `extra_attributes`, or tracking the backend's SPI schema drift; this service treats `user_context` as opaque.
- Typing `user_context` as a Pydantic model.
- Relaxing `extra="forbid"` for anything beyond this one field.
- Widening `SENSITIVE_PATTERNS`, or making `_mask_params_recursive` user-context-aware.
- Adding `user_context` to `generate_cache_key`.
- `$env` / `$headers` substitution on `user_context` — backend-resolved data, not a template.
- WebSocket transport (absent by decision, ADR-007).
- Recursive masking *into* nested containers; they are redacted wholesale by design.

## Risks

- **`tests/conftest.py:80`** — `single_usage_side_effect(request, method, params, timeout_ms)` is a
  fixed-arity positional `side_effect` for the whole endpoint suite. The moment the route passes an
  extra argument it raises `TypeError` and every single-usage endpoint test fails at once, pointing at
  the fixture rather than the change. The plan must update it deliberately.
- **No CI.** `mypy --strict`, ruff, black and pytest are enforced only by a local gate run.
- **`README.md` is already misleading here.** Line 51 claims MCP SDK "v1.21.0+" against a 1.30.0 pin,
  and the pre-merge chain at lines 153-161 cannot pass as written — it includes an integration
  selector that collects nothing and exits 5. Use `.ai-run/guides/quality-gates.md` instead.
- The three route handlers have no direct tests today, so nothing currently asserts what they pass
  downstream. The forwarding criteria above are the first such coverage.
