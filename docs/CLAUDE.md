# FINTERMINAL — Workspace Instructions

## Layout

- `PLAN.md`, `BACKLOG.md`, `Phase-1-Kickoff.md`, `MODEL-SWAP-GUIDE.md` — design docs
- `finterminal/` — the actual Python project (see its own `README.md`); pushed to https://github.com/AjinkyaWagh9/Finance-Terminal.git
- `TerminalVault/` — Obsidian vault. The brain / durable knowledge base of the project. Not pushed to GitHub.

## Vault update protocol (mandatory)

After **any meaningful code or content change**, spawn a Haiku  subagent via the `Agent` tool to update `TerminalVault/`. The vault is the cross-session memory — if it isn't updated, future sessions will lose context.

A "meaningful change" includes:
- New code modules, functions, or classes
- New design decisions or trade-offs (warrants an ADR)
- Phase / milestone completions
- Significant refactors or interface changes
- New external dependencies or data sources
- Changes to the model registry or agent assignments

A "trivial change" (skip the vault update):
- Typo fixes
- Comment-only edits
- Reformatting / linting

### How to invoke

```
Agent(
  description="Update TerminalVault — <one-line summary>",
  subagent_type="general-purpose",
  model="sonnet",          // or "haiku" for small updates
  prompt="""
    Update the Obsidian vault at /Users/ajinkyawagh/Desktop/FINTERMINAL/TerminalVault.

    Context — what just changed:
      <2-4 sentences summarizing the work>

    Files affected:
      <list of paths with file:line references where helpful>

    Tasks:
      1. Append a dated entry to TerminalVault/05 - Build Log/ — YYYY-MM-DD - <topic>.md
      2. Update or create code-map entries under TerminalVault/04 - Code Map/ for any new/changed modules
      3. If a new design decision was made, add an ADR under TerminalVault/02 - Decisions/
      4. Cross-link with [[wikilinks]] to existing pages (don't create orphans)
      5. Keep entries tight — bullets and tables, not prose. Use file:line refs to point at code rather than duplicating it.
      6. Update TerminalVault/Index.md if you added a major new page.

    Conventions:
      - Date format: YYYY-MM-DD
      - File naming: "Title Case With Spaces.md" (Obsidian-friendly)
      - Use [[wikilinks]] not [markdown](links) for internal navigation
      - Keep individual notes under 200 lines; split if longer
  """
)
```

## Project conventions

- **Indian markets first.** NSE/BSE primary; US in Phase 3.
- **Source discipline.** Every numeric claim in agent output must trace to data in the context block (`[src: ...]` tag). The Critic agent enforces this.
- **No model names in agent code.** Always go through `router.for_agent(name)` — see `MODEL-SWAP-GUIDE.md`.
- **Keep `.env` keys local.** Never commit; never echo full keys in tool output.
- **DuckDB column gotcha:** `asof` is a reserved keyword (used in `ASOF JOIN`). Use `as_of` everywhere.
