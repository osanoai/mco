# MCO

_Run one task across many AI coding agents in parallel — then trust the code they agree on._

MCO is a command-line orchestrator for running the same prompt across multiple coding agents. It can fan out work in parallel, collect provider output, normalize review findings, and return human-readable or machine-readable results.

## Why MCO?

**One agent is a single point of failure.** Ask a single coding agent to write or review code and you get one model's judgment — and one model's blind spots. It misses real bugs, flags problems that aren't real, and sounds equally confident either way. With nothing to check it against, you end up re-verifying everything yourself.

**MCO turns a pool of agents into a review panel.** It runs the same task across the leading coding agents — Claude, Codex, Gemini, Cursor, Grok, and more — in parallel, then uses consensus scoring to separate signal from noise:

- A finding **multiple independent models agree on** is one you can trust.
- A finding **only one model raised** is flagged for a second look, not lost in the pile.
- Each model's blind spot is covered by another, so fewer real issues slip through.

**The tradeoff is honest.** Running several agents takes a little longer than asking one — but the code holds up, and time you don't spend debugging shipped bugs is time saved. A bit more time up front pays for itself downstream.

**Reach for MCO when correctness matters more than raw speed:** reviewing security-sensitive changes, validating AI-generated code before it merges, or getting a high-confidence second opinion without betting your codebase on a single vendor.

## Two ways to use MCO

MCO works on its own and inside the AI assistant you already use:

- **As a CLI** — run `mco run` or `mco review` directly from your terminal, or wire them into scripts, hooks, and CI. See [Quick Start](#quick-start).
- **As a skill for your AI assistant** — MCO ships with a [skill](./SKILL.md) that teaches agents like Claude Code *when* and *how* to drive the CLI, so you orchestrate multiple agents from plain English without leaving your normal workflow:

  > "Ask Grok and Codex to review this change for security bugs."

  Your assistant turns that into the right `mco review` command, runs it, and reports each provider's findings back. See [Use as a Skill](#use-as-a-skill) to set it up.

It is intentionally provider-neutral. Built-in adapters cover common local CLIs, and custom agents can be registered through config without changing MCO itself.

## Built-in Providers

| Provider id | CLI binary | Notes |
|-------------|------------|-------|
| `antigravity` | `agy` | Canonical provider id. Legacy input alias: `gemini` |
| `claude` | `claude` | Claude Code |
| `codex` | `codex` | Codex CLI |
| `cursor` | `cursor-agent` | Cursor CLI |
| `grok` | `grok` | Grok CLI |
| `opencode` | `opencode` | OpenCode |
| `qwen` | `qwen` | Qwen Code |

Run `mco doctor` to see which providers are installed and authenticated on your machine.

## Install

From source:

```bash
git clone <your-mco-repo-url>
cd mco
python3 -m pip install -e .
```

If your fork publishes an npm wrapper, install that package and ensure `python3` is available on `PATH`.

## Quick Start

Run a general task:

```bash
mco run \
  --repo . \
  --prompt "Summarize this repository." \
  --providers claude,codex \
  --result-mode stdout
```

Run a structured review:

```bash
mco review \
  --repo . \
  --prompt "Review this repository for high-risk bugs and security issues." \
  --providers claude,codex,antigravity \
  --json
```

Read the prompt from stdin:

```bash
cat prompt.md | mco run --repo . --providers claude,codex --file -
```

Check local provider readiness:

```bash
mco doctor
mco doctor --providers antigravity,claude --json
```

List model catalog entries:

```bash
mco models
mco models --provider antigravity
```

## Use as a Skill

MCO ships with a [skill](./SKILL.md) that teaches a skill-aware AI assistant — such as Claude Code — to drive the CLI for you. Once it is installed, naming any supported provider in a request routes the work through `mco` automatically, with no flags to remember.

Install it for Claude Code by linking the skill into your skills directory:

```bash
mkdir -p ~/.claude/skills/mco-cli
ln -s "$(pwd)/SKILL.md" ~/.claude/skills/mco-cli/SKILL.md
```

Copy the file instead of linking if you prefer a static install. For other skill-aware agents, place `SKILL.md` wherever that tool loads skills from.

Then ask in plain language:

- "Ask Antigravity to summarize this repository."
- "Have Claude and Codex review the staged changes."
- "Use Grok, Codex, and Qwen to review `src/` for security issues and show me what they agree on."

Behind the scenes the skill keeps the orchestration correct: it always routes through `mco` (never raw provider binaries), chooses `run` vs `review` for the task, normalizes provider aliases (for example, legacy `gemini` to `antigravity`), passes your prompt safely, and keeps each provider's output separate.

Prerequisite: `mco` on your `PATH` — see [Install](#install).

## Commands

### `mco run`

General-purpose multi-provider execution. Providers complete the prompt freely; no findings schema is enforced.

```bash
mco run \
  --repo . \
  --prompt "Compare the tradeoffs in the runtime architecture." \
  --providers claude,codex,qwen \
  --result-mode stdout
```

### `mco review`

Structured code review. MCO asks providers for findings, normalizes them, deduplicates overlapping reports, and computes consensus metadata.

```bash
mco review \
  --repo . \
  --prompt "Review for security and correctness issues." \
  --providers claude,codex,antigravity \
  --format markdown-pr
```

### `mco doctor`

Checks provider binary presence, version, and auth readiness.

```bash
mco doctor --json
```

### `mco models`

Shows model tiers from the local model catalog.

```bash
mco models --provider claude
```

### `mco session`

Starts and manages persistent multi-turn provider sessions with queueing and cancellation.

```bash
mco session start --provider claude --name dev
mco session send dev "Continue the previous analysis."
mco session queue dev
mco session cancel dev
```

### `mco agent`

Lists and checks built-in and configured custom agents.

```bash
mco agent list
mco agent check my-ollama
```

### `mco serve`

Runs MCO as an MCP server over stdio.

```bash
mco serve
```

## Output

Review mode supports:

| Format | Flag | Use case |
|--------|------|----------|
| Human-readable report | `--format report` | Terminal output |
| PR Markdown | `--format markdown-pr` | Pull request comments |
| SARIF 2.1.0 | `--format sarif` | Code scanning uploads |
| JSON | `--json` | Automation |

Result delivery modes:

| Mode | Behavior |
|------|----------|
| `--result-mode stdout` | Print result and skip artifact files |
| `--result-mode artifact` | Write artifacts and print a summary |
| `--result-mode both` | Write artifacts and print full result |

Use `--save-artifacts` to keep stdout output while also writing artifacts.

When artifacts are enabled, MCO writes:

```text
reports/review/<task_id>/
  summary.md
  decision.md
  findings.json
  run.json
  providers/
  raw/
```

## Review Coordination

MCO can coordinate review work in several ways:

| Mode | Flag | Behavior |
|------|------|----------|
| Parallel | default | All selected providers receive the same prompt |
| Chain | `--chain` | Providers run sequentially; later providers see earlier output |
| Debate | `--debate` | Providers run a second challenge/refinement round on merged findings |
| Divide by files | `--divide files` | Files are split across providers |
| Divide by dimensions | `--divide dimensions` | Providers focus on dimensions such as security, performance, and correctness |

`--divide` is mutually exclusive with `--chain` and `--debate`.

Example:

```bash
mco review \
  --repo . \
  --prompt "Review this change for correctness and maintainability." \
  --providers claude,codex,antigravity,qwen \
  --divide dimensions
```

## Consensus Metadata

For structured reviews, MCO deduplicates findings across providers and records:

- `detected_by`: providers that reported the finding
- `agreement_ratio`: `detected_by_count / total_providers_ran`
- `consensus_score`: `agreement_ratio * max_confidence`
- `consensus_level`: `confirmed`, `needs-verification`, or `unverified`

Consensus metadata appears in JSON, SARIF, Markdown, and terminal reports.

## Configuration

MCO is zero-config by default. Optional config files can persist project or user defaults.

Config load order:

1. CLI flags
2. Project config: `.mcorc.json`
3. Global config: `~/.mco/config.json`
4. Built-in defaults

Example `.mcorc.json`:

```json
{
  "providers": ["claude", "codex", "antigravity"],
  "transport": "shim",
  "policy": {
    "stall_timeout_seconds": 600,
    "enforcement_mode": "best_effort",
    "max_provider_parallelism": 3,
    "perspectives": {
      "claude": "Focus on security vulnerabilities",
      "codex": "Focus on performance and resource usage",
      "antigravity": "Focus on maintainability"
    }
  }
}
```

Provider-keyed config maps accept legacy `gemini` keys and canonicalize them to `antigravity`.

## Common Flags

| Flag | Default | Description |
|------|---------|-------------|
| `--providers` | `antigravity,claude,codex,cursor,grok,opencode,qwen` | Comma-separated provider list |
| `--file` | unset | Read prompt from file path, or `-` for stdin |
| `--target-paths` | `.` | Comma-separated review scope |
| `--allow-paths` | `.` | Paths providers are allowed to access |
| `--stall-timeout` | `900` | Cancel provider after no output progress for this many seconds |
| `--review-hard-timeout` | `1800` | Global review deadline; `0` disables |
| `--max-provider-parallelism` | `0` | `0` means full provider parallelism |
| `--provider-timeouts` | unset | Per-provider timeout overrides, e.g. `claude=120,codex=90` |
| `--provider-models` | unset | Per-provider model overrides or tiers |
| `--provider-permissions-json` | unset | Provider permission settings |
| `--perspectives-json` | unset | Per-provider review focus |
| `--stream` | off | `jsonl` or `live` streaming output |
| `--quiet` | off | Print final provider text only |
| `--memory` | off | Enable memory integration |

Run `mco review --help` or `mco run --help` for the complete flag list.

## Provider Permissions

Some adapters expose permission controls through provider-specific keys.

| Provider | Key | Example |
|----------|-----|---------|
| `claude` | `permission_mode` | `plan` |
| `codex` | `sandbox` | `workspace-write` |
| `cursor` | `mode`, `sandbox`, `trust`, `force`, `approve_mcps` | `mode=plan` |
| `grok` | `permission_mode`, `sandbox`, `allow`, `deny`, and related toggles | `bypassPermissions` |

Example:

```bash
mco review \
  --repo . \
  --prompt "Review this change." \
  --providers claude,codex \
  --provider-permissions-json '{"claude":{"permission_mode":"plan"},"codex":{"sandbox":"workspace-write"}}'
```

Unsupported permission keys fail in `strict` mode and are dropped in `best_effort` mode.

## Custom Agents

Custom agents are loaded from:

1. `.mco/agents.yaml`
2. `.mcorc.yaml`
3. `~/.mco/agents.yaml`

Example:

```yaml
agents:
  - name: my-acp-agent
    transport: acp
    command: my-agent --acp
    permission_keys: [sandbox]

  - name: my-shim-agent
    transport: shim
    command: my-review-bot --json

  - name: my-ollama
    model: qwen2.5-coder:14b
```

Custom agents can participate in the same `mco run` and `mco review` workflows as built-in providers.

## Memory

Memory is optional and uses [evermemos-mcp](https://pypi.org/project/evermemos-mcp/).

```bash
pip install mco[memory]

mco review \
  --repo . \
  --prompt "Review for security issues." \
  --providers claude,codex,antigravity \
  --memory
```

When enabled, MCO can:

- inject prior findings into new prompts
- persist new findings with stable hashes
- track provider reliability by task category
- blend repo, stack, and global priors for cold starts
- passively mark findings as fixed when they disappear after related file changes

Memory commands:

```bash
mco memory status
mco memory agent-stats
mco memory priors --category security
mco findings list
mco findings confirm <hash> --status fixed
```

Requires `EVERMEMOS_API_KEY`.

## MCP Server

Install optional MCP dependencies:

```bash
pip install mco[memory]
```

Configure an MCP client:

```json
{
  "mcpServers": {
    "mco": {
      "command": "mco",
      "args": ["serve"]
    }
  }
}
```

Available tools:

- `mco_review`
- `mco_run`
- `mco_doctor`
- `mco_findings_list`
- `mco_memory_status`

Tools return `{"ok": true, "data": ...}` on success and `{"ok": false, "error": {"code": "...", "message": "..."}}` on failure.

## Exit Codes

| Code | Meaning |
|------|---------|
| `0` | Success |
| `2` | Input, config, provider, or runtime failure |
| `3` | Inconclusive review result |

## Development

Run tests:

```bash
python3 -m pytest -q
```

Run selected local smoke checks:

```bash
./mco doctor --json
./mco models
printf 'Say OK\n' | ./mco run --repo . --providers claude --file -
```

## License

MIT. See [LICENSE](./LICENSE).
