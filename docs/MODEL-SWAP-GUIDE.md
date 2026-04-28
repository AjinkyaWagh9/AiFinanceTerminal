# FINTERMINAL — Model Swap Guide

How to upgrade, downgrade, or replace the LLMs that power FINTERMINAL — without touching agent code.

**Architecture reference:** `PLAN.md` §3.1 (Model Abstraction Layer).
**Last updated:** 2026-04-28 (added OpenAI provider + GPT-5 family registry entries; documented `base_url_env` indirection)

---

## TL;DR

Two YAML files control everything:
- `config/models.yaml` — what models *exist* (registry)
- `config/agents.yaml` — what model each *agent uses* (assignment)

Code never names a model. To swap, edit YAML and restart.

---

## Provider class architecture (good to know before adding endpoints)

There are four provider classes total:

| Class | Used by | When to use |
|---|---|---|
| `AnthropicProvider` | `provider: anthropic` | Claude (Sonnet, Opus) |
| `OpenAICompatProvider` | `provider: openai_compat` / `openai` / `xai` | **Workhorse** — OpenAI itself, xAI (Grok), OpenRouter, Together, Groq, NVIDIA NIM, vLLM, llama-server, LM Studio |
| `OllamaProvider` | `provider: ollama` | Local Ollama (Phase 2 stub now) |
| `NullProvider` | `provider: null` | Agents that don't call an LLM (e.g. calendar) |

`OpenAICompatProvider` is registered under three keys (`openai_compat`, `openai`, `xai`) — they all map to the same class. Each model entry in `models.yaml` declares its own:

- `api_key_env` — env var holding the API key (e.g. `OPENAI_API_KEY`, `GROK_API_KEY`, `OPENROUTER_API_KEY`)
- `base_url` *or* `base_url_env` — endpoint URL (literal, or read from env). Defaults to `https://api.openai.com/v1`.

So adding a new OpenAI-compatible endpoint = one YAML entry, no Python code. See Playbook 4 for the full pattern.

---

## Common playbooks

Each playbook lists the exact files to touch in order. None require changing Python code (except adding a new provider, which is a single new file implementing one protocol).

### Playbook 1 — Swap one agent's model (e.g., Quality agent: phi4-mini → qwen3:8b)

```yaml
# config/agents.yaml
agents:
  quality:
    primary: qwen3:8b      # was: phi4-mini
    fallbacks: [phi4-mini]
```

Restart the terminal. Done. ~30 seconds.

If the new model isn't already in `models.yaml`, add it first (see Playbook 4).

### Playbook 1.5 — Switch supervisor from Claude to OpenAI (cost reduction)

When `/analyze` cost is the bottleneck, the OpenAI tier is the easiest win. The provider class (`openai_compat`) already exists; you only edit YAML and `.env`.

**Per-call cost (typical /analyze: ~3k tokens in, ~600 out):**

| Model | Per call | Monthly @ 50/day | Quality vs Sonnet 4.6 |
|---|---:|---:|---|
| `claude-sonnet-4-6` | ~$0.018 | ~$27 | baseline |
| `gpt-5` | ~$0.010 | ~$15 | comparable on synthesis; sometimes better on coding |
| `gpt-5-mini` | ~$0.0019 | ~$2.85 | adequate for routine fundamentals; weaker subtle synthesis |
| `gpt-5-nano` | ~$0.0004 | ~$0.60 | classifier-grade only — not recommended for `/analyze` |

**Steps:**

1. Add the key to `.env` (NOT `.env.example` — that's the committed template):
   ```bash
   echo 'OPENAI_API_KEY=sk-proj-...' >> finterminal/.env
   ```

2. Edit `config/agents.yaml`:
   ```yaml
   agents:
     supervisor:
       primary: gpt-5-mini                              # was: claude-sonnet-4-6
       fallbacks: [gpt-5, claude-sonnet-4-6]            # router walks this on ProviderError
   ```

3. Restart the terminal. No code change. No registry edit (gpt-5-* are already registered in `models.yaml`).

**Verify before fully committing:**

```bash
# Run /analyze on the same ticker against both models, compare side by side.
# YAML edit → restart → /analyze RELIANCE → screenshot.
# Edit YAML back to Claude → restart → /analyze RELIANCE → diff the bull/bear sections.
```

The acceptance bar from `Phase-1-Kickoff.md` §5.4 still applies regardless of model: every numeric tagged `[src: ...]`, confidence calibrated to 0.4–0.7 default, "What Would Change My Mind" non-empty and concrete. If gpt-5-mini fails any of those, swap back or try `gpt-5`.

**Reverse direction** (back to Claude): same playbook, just flip `primary:` and `fallbacks:` lines.

---

### Playbook 2 — Globally upgrade Claude (Sonnet 4.6 → Opus 4.7) for synthesis-heavy agents

```yaml
# config/agents.yaml — change these four lines
agents:
  supervisor:    { primary: claude-opus-4-7, fallbacks: [claude-sonnet-4-6] }
  critic:        { primary: claude-opus-4-7, fallbacks: [claude-sonnet-4-6] }
  bull_bear:     { primary: claude-opus-4-7, fallbacks: [claude-sonnet-4-6] }
  transcript:
    synthesize:  { primary: claude-opus-4-7, fallbacks: [claude-sonnet-4-6] }
```

Restart. Watch costs for a week (`/llm-cost` command, see §3 below). Roll back if budget breaks.

### Playbook 3 — Swap local model for a bigger one (qwen3:8b → qwen3:32b) when you upgrade RAM

Pre-flight: confirm hardware can host. qwen3:32b Q4 needs ~20 GB unified memory; M4 Air 16 GB will swap and crawl.

1. Pull model:
   ```bash
   ollama pull qwen3:32b
   ```
2. Add to registry:
   ```yaml
   # config/models.yaml — append
   - name: qwen3:32b
     provider: ollama
     api_id: qwen3:32b
     context_window: 32768
     cost_per_mtok_in: 0.0
     cost_per_mtok_out: 0.0
     capabilities: [reasoning, tool_use, multilingual, json_mode]
     tags: [local, premium, slow]
   ```
3. Reassign in `agents.yaml`:
   ```yaml
   agents:
     data:        { primary: qwen3:32b, fallbacks: [qwen3:8b, claude-sonnet-4-6] }
     news:        { primary: qwen3:32b, fallbacks: [qwen3:8b, claude-sonnet-4-6] }
     transcript:
       extract:   { primary: qwen3:32b, fallbacks: [qwen3:8b, claude-sonnet-4-6] }
     ceo_tracker: { primary: qwen3:32b, fallbacks: [qwen3:8b, claude-sonnet-4-6] }
     comps:       { primary: qwen3:32b, fallbacks: [qwen3:8b, claude-sonnet-4-6] }
   ```
4. Restart. Run `/analyze RELIANCE.NS` and check latency in the `/llm-cost` log. If a single call exceeds ~15 s, the model is too big for your hardware — roll back step 3.

**Hardware reality check** (rough, M-series with quantized models):

| Model size | Quant | RAM needed | M4 Air 16 GB | M4 Pro 24 GB | M-series 32 GB+ |
|---|---|---:|---|---|---|
| 8B | Q4_K_M | ~6 GB | ✅ fast | ✅ fast | ✅ fast |
| 14B | Q4_K_M | ~10 GB | ⚠️ tight | ✅ comfortable | ✅ fast |
| 32B | Q4_K_M | ~20 GB | ❌ swaps | ⚠️ tight | ✅ comfortable |
| 70B | Q4_K_M | ~42 GB | ❌ no | ❌ no | ⚠️ exo cluster |

### Playbook 4 — Add a brand-new model (e.g., Llama 5 70B via NVIDIA NIM)

NVIDIA NIM is OpenAI-compatible, so no new provider class needed.

1. Set env var:
   ```bash
   # .env
   NIM_API_KEY=nvapi-...
   NIM_BASE_URL=https://integrate.api.nvidia.com/v1
   ```
2. Add to registry:
   ```yaml
   # config/models.yaml
   - name: llama-5-70b-nim
     provider: openai_compat
     api_id: meta/llama-5-70b-instruct
     base_url_env: NIM_BASE_URL
     api_key_env: NIM_API_KEY
     context_window: 128000
     cost_per_mtok_in: 0.0          # NIM free tier
     cost_per_mtok_out: 0.0
     capabilities: [reasoning, tool_use, json_mode, synthesis]
     tags: [cloud, free, large]
   ```
3. Use it in `agents.yaml` for whichever agent benefits.
4. Restart. Verify with `/llm-test llama-5-70b-nim` (Phase 2 helper command).

### Playbook 5 — Add a brand-new provider (e.g., Together.ai)

Only needed when the provider's API isn't OpenAI-compatible. Together.ai *is* OpenAI-compatible, so this is overkill — use Playbook 4 instead. But if you ever needed (say) a custom provider:

1. Create `src/finterminal/llm/providers/together.py`:
   ```python
   from ..base import LLMProvider, Message, Completion, ModelMetadata

   class TogetherProvider(LLMProvider):
       def __init__(self, model_meta: ModelMetadata, api_key: str):
           self._meta = model_meta
           self._client = TogetherClient(api_key=api_key)

       async def complete(self, system, messages, max_tokens=2000, **kwargs) -> Completion:
           resp = await self._client.chat.completions.create(
               model=self._meta.api_id,
               messages=[{"role": "system", "content": system}, *messages],
               max_tokens=max_tokens,
           )
           return Completion(
               text=resp.choices[0].message.content,
               tokens_in=resp.usage.prompt_tokens,
               tokens_out=resp.usage.completion_tokens,
           )

       @property
       def metadata(self) -> ModelMetadata:
           return self._meta
   ```

2. Register in `src/finterminal/llm/providers/__init__.py`:
   ```python
   PROVIDERS["together"] = TogetherProvider
   ```

3. Add models to `models.yaml` with `provider: together`.

That's it. ~30 lines of code, one line of registration.

### Playbook 6 — Migrate an agent to be cheaper (cost crisis mode)

If `/llm-cost` shows a single agent eating your Claude budget:

1. Identify the agent (likely Critic or Bull-Bear).
2. Try the cheaper alternative first:
   ```yaml
   critic: { primary: qwen3:8b, fallbacks: [claude-sonnet-4-6] }
   ```
3. Run a side-by-side: `/analyze RELIANCE.NS --compare critic=qwen3:8b,claude-sonnet-4-6` (Phase 3 A/B feature).
4. If quality holds, commit the swap. If not, narrow the use:
   ```yaml
   critic:
     primary: qwen3:8b               # default cheap path
     escalate_when:                  # Phase 4 feature
       - confidence_below: 0.6
     escalate_to: claude-sonnet-4-6
   ```

### Playbook 7 — Disable an entire agent (turn off Sentiment to save Grok cost)

```yaml
# config/agents.yaml
agents:
  sentiment:
    primary: grok-3-mini
    enabled: false        # <- this line
```

Restart. Sentiment commands return "module disabled" notices (see PLAN.md §4.3). Safe — terminal still works fully.

### Playbook 8 — Pin a model version (Claude releases Sonnet 4.7, you want to stay on 4.6 until you've evaluated)

```yaml
# config/models.yaml
- name: claude-sonnet-4-6
  provider: anthropic
  api_id: claude-sonnet-4-6     # already pinned via api_id
```

Anthropic API IDs are versioned — `api_id: claude-sonnet-4-6` will not silently upgrade. To evaluate 4.7 in parallel:

```yaml
# add a second registry entry
- name: claude-sonnet-4-7-eval
  provider: anthropic
  api_id: claude-sonnet-4-7
  cost_per_mtok_in: 3.0
  cost_per_mtok_out: 15.0
  ...

# in agents.yaml, A/B for one agent
agents:
  critic:
    mode: ab_test                          # Phase 3 feature
    a: claude-sonnet-4-6
    b: claude-sonnet-4-7-eval
    log_both: true
```

Both models run on every `/analyze`; both responses logged into DuckDB. After 100 calls, compare quality manually or via Critic-of-Critic eval. Promote the winner; remove the loser.

---

## 2. Hot-reload (Phase 3)

Changes to `agents.yaml` apply on next process start. To pick them up without a restart, the Phase 3 router has a filesystem watcher:

```bash
/llm-reload   # rereads agents.yaml + models.yaml, swaps providers in-place
```

In-flight requests finish on the old model; new requests use the new model. Useful when iterating on a cost crisis — change YAML, hit `/llm-reload`, see effect on the next `/analyze`.

---

## 3. Observability — `/llm-cost` and `llm_calls` table

Every LLM call writes a row to `llm_calls` in DuckDB. Schema:

```sql
CREATE TABLE llm_calls (
  ts            TIMESTAMP,
  agent         VARCHAR,
  model         VARCHAR,
  provider      VARCHAR,
  tokens_in     INTEGER,
  tokens_out    INTEGER,
  cost_usd      DOUBLE,
  latency_ms    INTEGER,
  cache_hit     BOOLEAN,
  error         VARCHAR
);
```

Built-in commands (Phase 2):

- `/llm-cost` — last 30 days, by agent and by model, with totals
- `/llm-cost agent=critic` — drill down to one agent
- `/llm-cost month` — current month vs. budget
- `/llm-cost compare claude-sonnet-4-6 claude-opus-4-7` — head-to-head

Sample output:
```
Last 30d  |  agent       | model              | calls | $ in   | $ out  | total
          |  supervisor  | claude-sonnet-4-6  |   412 | $4.20  | $11.30 | $15.50
          |  critic      | claude-sonnet-4-6  |   412 | $3.10  | $7.80  | $10.90
          |  data        | qwen3:8b           |  1820 |  $0.00 |  $0.00 |  $0.00
          |  sentiment   | grok-3-mini        |   720 |  $1.10 |  $0.40 |  $1.50
          |  TOTAL       |                    |  3364 |  $8.40 | $19.50 | $27.90
```

---

## 4. Budget guardrails (Phase 2.5)

`config/budgets.yaml` (introduced in Phase 2.5):

```yaml
monthly_budget_usd: 100
per_agent_caps:
  critic: 30
  supervisor: 30
  bull_bear: 20
  sentiment: 15

on_breach:
  - notify: "${TELEGRAM_WEBHOOK}"   # Phase 4
  - downgrade:                       # auto-fail-down at 80% of cap
    - agent: critic
      to: qwen3:8b
  - block_at_100pct: true
```

When an agent's monthly spend hits 80% of its cap, `BudgetGuard` rewrites its routing to the fallback. At 100%, calls error with `BudgetExceeded`. You override per-call with `--no-budget`.

---

## 5. Capability-based routing (Phase 2.5)

Sometimes an agent doesn't care which model — it cares about a *capability*. Example: a future Vision agent that reads chart screenshots:

```python
# inside the agent
llm = router.for_capability("vision", max_cost_per_mtok_out=20.0)
```

The router queries the registry: "give me a model with `vision` in capabilities, cheapest first, that's not over budget." Returns a handle. Agent doesn't care if it's Claude, GPT-4o, or Qwen-VL.

Configure preferences in `config/capabilities.yaml`:

```yaml
capabilities:
  vision:
    prefer_local: true
    fallback_cloud: claude-sonnet-4-6
  live_search:
    prefer: grok-3-mini
  deep_reasoning:
    prefer: claude-opus-4-7
    fallback: claude-sonnet-4-6
```

---

## 6. When NOT to swap

Some pitfalls to avoid:

- **Don't swap mid-investigation.** If you're in the middle of analyzing a name, finish on the current model — comparing analyses across model versions is confounded.
- **Don't downgrade the Critic to save money first.** The Critic is your safety rail. Downgrade Data or News agents before touching Critic.
- **Don't swap to a model you haven't smoke-tested.** Always run `/llm-test <model>` first — Phase 2 helper that runs a fixed prompt and shows output side-by-side with the current default.
- **Don't trust cost-per-token alone.** A model that's 1/10 the price but needs 3× the tokens (because it can't follow JSON schema) is more expensive net.
- **Don't enable A/B testing in production with real money.** Use it on watchlist tickers for evaluation, not on `/analyze` calls you act on.

---

## 7. Migration milestones (likely upgrades over the project's life)

A predictable sequence of swaps as the project matures:

| When | Swap | Why |
|---|---|---|
| Phase 1 → 2 | Add Qwen3 8B for Data + News | Free up Claude budget for synthesis work |
| Phase 2 → 2.5 | Add Phi-4 Mini for classification | Quality, Macro, Ownership are formula-heavy |
| Phase 2.5 → 3 | Maybe upgrade Critic to Opus | Cyclical critique benefits from deeper reasoning |
| Hardware upgrade (M4 Pro 24 GB+) | Qwen3 8B → Qwen3 14B locally | Better local quality without cost |
| When NIM adds Llama 5 | Add as cloud fallback | Free large-model burst |
| When Anthropic ships Sonnet 5 | A/B against Sonnet 4.6/4.7 for 1 week | Don't auto-upgrade |
| If second device added | exo cluster + 70B model | See `BACKLOG.md` §1.10 |

Each is a YAML edit + restart. The agent code, prompts, and database schema do not change.
