# ADR-NNN — Short imperative title

> One-line summary: the decision, in active voice. ("Adopt X" / "Replace Y with Z" / "Build a custom Q layer.")

**Status:** Proposed | Accepted | Superseded by ADR-NNN | Deprecated
**Date:** YYYY-MM-DD
**Source:** PLAN.md §X.Y · Other ADR refs · External feedback (filename / build-log link)
**Drivers:** What forced this decision now? Be specific (incident, feedback, blocker, regression).

---

## Context

What's the current state? What did we try / consider before deciding to make this change?

Include any data: numbers from probes, latency measurements, error rates, cost estimates. Decisions without numbers are guesses.

If this supersedes another ADR, link it explicitly: "Supersedes [[ADR-NNN]] — that decision was right at the time but X changed."

---

## Decision

What we're doing. Imperative voice.

If the decision has multiple components (interface + implementation + scope), enumerate them. Each component should be testable in isolation.

```
Optionally: code snippets, schema, file paths showing exactly where the decision lands.
```

---

## Consequences

### Positive
- What this enables
- What constraint it removes
- What it validates from earlier ADRs

### Negative / risks
- What this makes harder
- What it couples or commits us to
- Failure modes + mitigations

### What this does NOT change
- Existing scope, ADRs, or non-goals that stay in force.
- Phase boundaries that remain unchanged.

---

## Alternatives considered and rejected

| Alternative | Why rejected |
|---|---|
| Alt A | Reason |
| Alt B | Reason (cost / coupling / scope creep) |

Be honest. The alternatives section is where future-you decides whether to revisit.

---

## Open questions

- Q-ADR-NNN-1: Phrase as a falsifiable question with a target resolution date or trigger.

---

## Cross-links

- Triggered by: [[input.md feedback (YYYY-MM-DD)]] / [[Build Log entry]]
- Affects: [[ADR-other]] · [[Phase X — Y]] · [[Code Map entry]]
- Implementation: commit `<short-sha>` / [[2026-MM-DD - Build log entry]]
