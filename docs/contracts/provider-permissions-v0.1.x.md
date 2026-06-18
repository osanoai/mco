# Provider Permission Matrix (`v0.1.x`)

This document freezes provider permission-key behavior for `mco run` / `mco review` in `v0.1.x`.

## Global Enforcement Semantics

- `enforcement_mode=strict` (default):
  - if config requests unsupported permission keys for a provider, that provider fails closed with `reason=permission_enforcement_failed`.
- `enforcement_mode=best_effort`:
  - unsupported permission keys are dropped before adapter execution.
  - provider continues with only supported keys.

## Matrix

| Provider | `supported_permission_keys()` | Effective adapter mapping | Default behavior if key omitted |
|---|---|---|---|
| `claude` | `["permission_mode"]` | `permission_mode` -> `claude --permission-mode <value>` | `permission_mode=plan` |
| `codex` | `["sandbox"]` | `sandbox` -> `codex exec --sandbox <value>` | `sandbox=workspace-write` |
| `cursor` | `["approve_mcps", "force", "mode", "sandbox", "trust"]` | `mode` -> `cursor-agent --mode <value>`; `sandbox` -> `cursor-agent --sandbox <value>`; truthy `force` -> `cursor-agent --force`; truthy `approve_mcps` -> `cursor-agent --approve-mcps`; `trust=false` omits default `cursor-agent --trust` | `cursor-agent --print --output-format text --trust --workspace <repo>` |
| `antigravity` | `[]` | No permission-key mapping in adapter | N/A |
| `grok` | `["permission_mode", "sandbox", "always_approve", "tools", "disallowed_tools", "allow", "deny", "no_plan", "no_memory", "no_subagents", "disable_web_search"]` | `permission_mode` -> `grok --permission-mode <value>`; `sandbox` -> `grok --sandbox <value>`; truthy `always_approve` -> `grok --always-approve`; `tools`, `disallowed_tools`, `allow`, `deny` map to their same-name Grok flags; falsey `no_plan`, `no_memory`, `no_subagents`, or `disable_web_search` omits the corresponding default flag | `permission_mode=bypassPermissions` plus `--no-plan --no-memory --no-subagents --disable-web-search` |
| `opencode` | `[]` | No permission-key mapping in adapter | N/A |
| `qwen` | `[]` | No permission-key mapping in adapter | N/A |

## Strict vs Best-Effort Examples

Given config:

```json
{
  "policy": {
    "enforcement_mode": "strict",
    "provider_permissions": {
      "antigravity": { "sandbox": "workspace-write" }
    }
  }
}
```

- `strict`: `antigravity` fails with `permission_enforcement_failed`.
- `best_effort`: `sandbox` is dropped (since unsupported), `antigravity` still runs.

## Important Boundary

- `allow_paths` is orchestrator-level validation, not OS-kernel sandboxing.
- Real process sandboxing/isolation remains provider-specific.
