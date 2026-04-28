# Code Map — module-or-directory-name

> Back to [[Index]] | See also [[adjacent code map]] · [[ADR that drives this]]

**Directory or path:** `src/finterminal/path/to/module/`
**Shipped:** YYYY-MM-DD, commit `<short-sha>` (omit if pre-existing)
**Driver:** Brief — why this module exists. Reference an ADR if relevant.

---

## File inventory

| File | Lines | Purpose |
|---|---:|---|
| `__init__.py` | N | Module docstring + roadmap |
| `module.py` | N | Public surface |

---

## `module.py`

### Public surface
```python
function_name(arg: type) -> ReturnType
ClassName(...)
```

One-line description of each export.

### Strategy / contract
- Inputs and how they're normalized
- External calls (URLs, services)
- Cache / rate-limit behavior
- Error handling: what triggers exceptions vs partial returns

### Implementation notes
- Specific gotchas (parser quirks, network behaviors, edge cases)
- Why we chose X instead of Y (link to ADR if depthful)

### Live validation (when applicable)
| Input | Output |
|---|---|
| Concrete sample | What we observed |

---

## Roadmap (when there's planned future work)

| Future addition | Purpose | ADR |
|---|---|---|
| `next_module.py` | Future scope | [[ADR-NNN]] |

---

## Cross-links

- ADR: [[ADR-NNN ...]]
- Architecture: [[01 - Architecture/X]]
- Build log: [[YYYY-MM-DD - Topic]]
- Adjacent code: [[other Code Map entry]]
