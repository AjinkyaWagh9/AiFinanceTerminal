# YYYY-MM-DD — Short topic sentence

> One-paragraph TL;DR — what shipped, why it matters, where to look for details. The reader should be able to skip the rest of this note and still know whether to dig deeper.

**Commit(s):** `<short-sha>` — pushed to `main` (or `branch-name`).
**Trigger:** What forced this work? (Bug, feedback doc, blocker, ADR.)

---

## What shipped

| Module / file | Action | Notes |
|---|---|---|
| `path/to/file.py` | new / modified / removed | One-line description |

Or, when prose works better:

- New module `data/india/something.py` — purpose, entry points
- Modified `data/openbb_client.py` — what changed and why

---

## Surprises / worth remembering

| Symptom | Root cause | Fix |
|---|---|---|
| Specific observed failure | Why it actually happened (not the symptom) | What we did about it |

These are the entries that earn their keep over time. A future-you looking at a similar symptom should find it here.

---

## Before vs after (when relevant)

| Field / metric | Before | After |
|---|---|---|
| `/some-command output` | Old behavior | New behavior |

Include real numbers. "Lifted from 4 to 7 fields populated" beats "improved coverage."

---

## What's NOT changing

- ADRs not affected
- Phase boundaries that remain
- Scope this work explicitly excludes (deferred items)

---

## Cross-links

- ADR: [[ADR-NNN ...]] (if a new design decision was made; otherwise reference the ADR being implemented)
- Code map: [[Code Map entry]] (touch the affected pages)
- Phase: [[Phase X — Y]]
- Adjacent build log: [[earlier or related entry]]

---

## Next step / open

What's the natural follow-up? What did this commit defer?
