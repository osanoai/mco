---
name: mco-cli
description: |
  REQUIRED when user mentions gemini, codex, claude, cursor, opencode, or qwen as the agent/provider to perform a task. Route "ask gemini", "use codex", "run with claude", "have cursor do X", "have opencode do X", and similar requests through the mco CLI.
  TRIGGER when: user names an AI coding provider as the performer of a task; user wants multi-provider code review; user wants a multi-agent run; user says "ask", "use", "run with", or "review with" plus a provider name.
  SKIP when: user is asking about a provider API/SDK rather than asking that provider to perform work; user explicitly asks to run a local provider binary directly without mco.
---

# MCO CLI Skill

Use the `mco` command from `PATH` to run AI coding providers. Do not call provider binaries directly.

Supported providers: `claude`, `codex`, `cursor`, `gemini`, `opencode`, `qwen`.

## Basic Rules

1. Use `mco` exactly as a shell command. Do not prefix it with this skill directory.
2. Use `mco run` for general tasks: answer, analyze, plan, summarize, implement, investigate.
3. Use `mco review` for review tasks: bugs, regressions, security, changed-code review, findings.
4. Pass the user's task through stdin with `--file -` and a single-quoted heredoc.
5. Keep each provider's result separate in the final response unless the user asks for synthesis.
6. If `mco` returns an error, report the exact error and stop. Do not fall back to direct provider binaries.

## Provider Selection

Use the providers named by the user.

Examples:
- "ask Gemini" -> `--providers gemini`
- "use Claude and Codex" -> `--providers claude,codex`
- "have Cursor do this" -> `--providers cursor`
- "have Opencode review this" -> `--providers opencode`

If the user asks for "all providers", use:

```bash
--providers claude,codex,cursor,gemini,opencode,qwen
```

If the user names an unsupported provider, stop and say that `mco` supports only `claude`, `codex`, `cursor`, `gemini`, `opencode`, and `qwen`.

## Command Templates

For general work, run:

```bash
mco run \
  --repo REPO_PATH \
  --file - \
  --providers PROVIDERS \
  --result-mode stdout <<'PROMPT'
TASK_PROMPT
PROMPT
```

For review work, run:

```bash
mco review \
  --repo REPO_PATH \
  --file - \
  --providers PROVIDERS \
  --result-mode stdout \
  --review-hard-timeout 600 <<'PROMPT'
TASK_PROMPT
PROMPT
```

Replace:
- `REPO_PATH` with the absolute path to the target repository, or `.` if the current directory is the target repository.
- `PROVIDERS` with a comma-separated provider list, such as `gemini`, `cursor`, or `claude,codex`.
- `TASK_PROMPT` with the user's exact task plus any necessary local path context.

The closing `PROMPT` line must start at column 1 with no spaces before it.

## Extra Flags

Only add extra flags when the user explicitly asks for them or the task clearly requires them.

Common flags:
- `--target-paths PATHS` for a specific file or directory scope.
- `--diff` for changes versus the merge base with main/master.
- `--staged` for staged changes only.
- `--unstaged` for unstaged working-tree changes only.
- `--diff-base REF` for a specific comparison base.
- `--provider-models PROVIDER=MODEL` when the user explicitly names a model.
- `--synthesize` when the user asks for a combined consensus answer.

Place extra flags before the heredoc marker.

Example with target paths:

```bash
mco review \
  --repo /path/to/repo \
  --file - \
  --providers claude,codex \
  --result-mode stdout \
  --review-hard-timeout 600 \
  --target-paths src,tests <<'PROMPT'
Review these paths for bugs and regressions.
PROMPT
```

## Model Names

Default behavior: omit `--provider-models`.

If the user names a specific model, first try:

```bash
mco models --provider PROVIDER
```

If the model list works and the requested model appears, add:

```bash
--provider-models PROVIDER=MODEL
```

If the model list fails, report the failure and ask the user whether to continue with provider defaults or provide an exact model override. Do not guess model names.

## Agent Discovery

Use `mco agent` only to inspect available agents, not to run tasks.

To list built-in and configured agents:

```bash
mco agent list
```

To check whether one agent is installed and ready:

```bash
mco agent check PROVIDER
```

If the agent check fails for a user-requested provider, report the exact readiness output and stop. Do not fall back to direct provider binaries.

## Output Handling

After `mco` finishes, summarize the result in readable text:

1. State the command intent.
2. List each provider with success or failure.
3. Preserve each provider's important output separately.
4. For reviews, list findings by severity when the output includes severities.
5. Include exact error text for failed providers or failed `mco` commands.

Do not return raw JSON unless the user requested JSON.
