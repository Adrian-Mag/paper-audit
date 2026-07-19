# Paper-Audit System — Session Handover

Written 2026-07-19, at the end of a design discussion held inside Adrian's thesis workspace
(`~/PhD/thesis`, which has strict offline guardrails and is the wrong place to build this).
This file is self-contained: a fresh Claude session in a new workspace should be able to
continue from here without the original conversation.

## What this is

Adrian is building a high-assurance, multi-agent scientific paper audit system: a Python
controller owns all orchestration deterministically, while Claude workers do bounded
epistemic reasoning over an atomic, typed claim ledger. The goal is an epistemically
auditable literature-analysis pipeline, not polished summaries. Adrian has a full detailed
build brief (about 28 sections); ask him for it when later phases need it. For v0, this
handover contains everything required.

## Absolute constraints — read before doing anything

1. **NO API / pay-per-token billing, ever. This is the top constraint, above all features.**
   All Claude usage must draw from Adrian's Claude Max 5x subscription flat-rate limits.
   - Verified 2026-07-19 on this machine: no `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`,
     `CLAUDE_CODE_USE_BEDROCK/VERTEX/FOUNDRY`, `ANTHROPIC_PROFILE`, or
     `CLAUDE_CODE_OAUTH_TOKEN` in the environment; no `apiKeyHelper` in
     `~/.claude/settings*.json`; `~/.claude.json` shows `billingType: stripe_subscription`;
     `~/.claude/.credentials.json` (subscription OAuth) is the only credential on disk.
   - Credential precedence puts an API key ABOVE subscription OAuth, so a stray key would
     silently switch billing. The system therefore ships a runtime guard (`guard.py`) that
     scans for metered credentials before every batch of worker calls and refuses to run
     if any are found. Guard policy is configurable in principle (future downloaders may
     be API-key users) but Adrian's machine-wide policy is subscription-only, and
     per-project config must NOT be able to override the billing policy.
   - `claude -p` smoke test already passed on subscription auth (2026-07-19):
     `claude -p 'Reply with exactly: OK' --model haiku --output-format json` returned
     `OK`. The `total_cost_usd` field in that output is a client-side estimate, not a
     bill; under subscription auth it draws from Max limits.
2. **Backend-neutral by design.** Primary backend: the Claude Agent SDK (Python,
   `pip install claude-agent-sdk` — NOT yet installed; needs a fresh project venv).
   Fallback backend: `claude -p` subprocess (already verified working). Reason: Anthropic
   paused a change to Agent SDK billing in June 2026; if SDK usage is ever split from
   subscriptions, the pipeline must switch to whichever route still draws from the
   subscription without redesign. Rules that keep the fallback real:
   - The `AgentBackend` interface is defined around the INTERSECTION of SDK and CLI
     capabilities (prompt in, schema-validated JSON out, tool allowlist, working dir,
     isolation), never around SDK-only conveniences.
   - Evidence tools (when they arrive, post-v0) go behind a local stdio MCP server, which
     both the SDK (`mcp_servers`) and the CLI (`--mcp-config`) can use identically.
   - A `FakeAgentBackend` exists for tests (zero Claude usage), and the toy fixture must
     periodically be run through BOTH real backends so the CLI path cannot silently rot.
3. **Working style.** Adrian wants design discussed in prose before anything is scaffolded.
   The v0 scope below is already agreed; build that, but resolve the open questions at the
   bottom with him first. Do not expand scope without discussion. No em-dashes in prose
   he will read or keep.

## Decisions already made

- **Artificial fixture paper first.** A 2-3 page markdown "paper" with exactly one planted
  trap (e.g. an empirical result phrased as a general claim), plus a ground-truth file
  stating which claims should survive and what verdict the trap should receive. The demo
  is therefore self-scoring. No real PDFs in v0.
- **No packaging/distribution work yet.** Distributability (pipx, other users, their own
  logins) is a later concern; first make it work.
- **Three-location layout:**
  - Program home: a standalone git repo with its own `.venv/` (location TBD, open
    question 1), installed editable so the CLI entry point is on PATH and usable from
    any workspace.
  - Per-project state: a `.paper-audit/` directory created in whatever project the tool
    is run in (runs, reports, usage).
  - Global config: `~/.config/paper-audit/config.toml` (billing policy, model tiers).
  - NOT in `~/.claude/` — that is Claude Code's config surface. (A thin
    `~/.claude/skills/paper-audit/` wrapper for `/paper-audit` inside Claude Code
    sessions is a possible much-later convenience.)
- **v0 storage is plain JSON artifacts per run** (inspectable), SQLite deferred to v1
  when claims get genealogy and cross-run caching. Everything is Pydantic-typed so the
  move is mechanical.
- **Prompts are versioned files** (`prompts/*.md`), part of experiment configuration;
  prompt changes must invalidate any cached verdicts (hash them into cache keys later).
- **Usage ledger from day one**: every worker call records tokens + model, because under
  flat pricing the real currency is Max 5-hour/weekly limits, not dollars.
- **Model-tier policy (proposed, Adrian broadly agreed):** Haiku for mechanical checks,
  Sonnet for entailment verification, Opus reserved for rare hard cases.

## v0 scope (agreed)

One artificial paper + one question, pipeline: analyst emits atomic typed claims
(Pydantic-validated, compound claims rejected) → deterministic exact-quote check in pure
Python → one FRESH-context entailment verifier per claim (sees only its claim + cited
passage, never the analyst's narrative or sibling verdicts) → deterministic conservative
synthesis (drops unsupported claims, may not introduce new prose claims) → report +
coverage table + automatic scoring against the fixture's ground truth.

Explicitly OUT of v0: PDF/evidence layer (block IDs, page images), MCP tools, citation
chains, derivation verifier, hidden-control machinery, independent reconstruction, SQLite.

### v0 file tree (agreed)

```
paper-audit/                          # program home, git repo
├── pyproject.toml                    # deps: pydantic (+ claude-agent-sdk)
├── README.md
├── src/paper_audit/
│   ├── cli.py                        # entry point: `paper-audit run --fixture toy`
│   ├── guard.py                      # billing preflight; refuses metered credentials
│   ├── config.py                     # global + project config; billing policy here
│   ├── schemas.py                    # Question, AtomicClaim (typed), EvidenceRef,
│   │                                 #   Verdict, CoverageReport
│   ├── backends/
│   │   ├── base.py                   # AgentBackend protocol: (job, schema) -> result
│   │   ├── sdk_backend.py            # Agent SDK query()-per-worker (fresh session each)
│   │   ├── cli_backend.py            # claude -p subprocess runner (fallback, kept live)
│   │   └── fake.py                   # canned responses for tests, zero Claude usage
│   ├── pipeline/
│   │   ├── analyst.py                # stage 1: paper+question in, claims JSON out
│   │   ├── quote_check.py            # stage 2: pure Python verbatim-substring check
│   │   ├── verifier.py               # stage 3: one fresh worker per claim
│   │   └── synthesize.py            # stage 4: deterministic merge + report
│   ├── prompts/
│   │   ├── analyst.md
│   │   └── entailment_verifier.md
│   ├── store.py                      # JSON run artifacts (see per-project layout)
│   └── usage.py                      # token/model ledger per worker call
├── fixtures/
│   ├── toy_paper.md                  # artificial paper, ONE planted trap
│   └── toy_question.yaml             # question + ground truth for self-scoring
└── tests/
    ├── test_guard.py                 # injects fake ANTHROPIC_API_KEY, asserts refusal
    ├── test_schemas.py               # rejects compound/malformed claims
    ├── test_quote_check.py           # substring edge cases (whitespace, unicode)
    └── test_pipeline_fake.py         # full pipeline on FakeAgentBackend
```

### Per-project layout (created on first run in any workspace)

```
<project>/.paper-audit/
└── runs/<date>_<fixture>_<question>/
    ├── claims.json          # analyst output, post-validation
    ├── quote_check.json     # pass/fail per evidence ref
    ├── verdicts/C1.json ... # one per verifier; includes session id + usage
    ├── report.md            # human-readable conservative answer
    └── usage.json           # summed token spend for the run
```

## Core principles inherited from the full brief (govern v0 too)

- Agents perform epistemic reasoning; deterministic code controls the experiment. The
  controller decides what each worker sees, whether its session is fresh, how output is
  validated, and when to stop. Never delegate these to prompts.
- One proposition per claim; compound claims are rejected or split before verification.
- A claim being true does not mean the cited source supports it; verifiers judge source
  support only.
- Never upgrade: inference → explicit statement; numerical illustration → theorem; cited
  assertion → inspected evidence; restricted result → universal conclusion.
- "Unknown" / "unsupported" are valid, first-class outputs, not failures.
- Structured verdicts only (schema-validated); free-form prose is never accepted as a
  verdict. Malformed worker output fails the run loudly.
- The final report is a projection of the audited ledger; the synthesis step cannot add
  substantive claims.

## Environment facts (this machine, 2026-07-19)

- `claude` CLI v2.1.215 at `~/.local/bin/claude`; auth is Max subscription OAuth only.
- Agent SDK not installed anywhere (checked npm global and pip in both conda envs).
- At SDK install time, verify how the Python package locates the CLI runtime (versions
  have differed between bundling it and using the global `claude`; the global one exists
  either way). Use a fresh venv in the repo. Do NOT use the `inferences` conda env; it
  belongs to the thesis workspace.
- No `ant` CLI installed (irrelevant to this project; it is API-key oriented).

## Open questions — resolve with Adrian before creating files

1. **Program home location and name** (e.g. `~/tools/paper-audit` vs `~/PhD/paper-audit`
   vs elsewhere). Presumably the new workspace this session is starting in; confirm.
2. **v0 worker input mode:** inline paper text in the prompt (proposed, simplest) vs
   making workers read the fixture from a file so behaviour is closer to the eventual
   real-PDF setup. Adrian had not yet said which he prefers.

## Suggested build order once questions are resolved

1. Repo skeleton + venv + `pip install pydantic claude-agent-sdk`; verify SDK import and
   that it resolves subscription auth (tiny one-call smoke test, then stop).
2. `guard.py` + `schemas.py` + `fake.py` backend + all four test files. Everything here
   runs without touching Claude or Max limits.
3. `fixtures/toy_paper.md` + `toy_question.yaml` (design the trap deliberately).
4. `cli_backend.py` (already-verified path) end to end on the fixture, then
   `sdk_backend.py`, then compare. Score both against ground truth.
5. Report results to Adrian, including the usage ledger numbers (what one full toy audit
   costs in tokens), before any scope expansion.
