# SKILLS – Expected AI Agent Capabilities

This document describes the skills AI agents should leverage when contributing
to **MonAssmat**.

---

## Business Domain Knowledge (Top Priority)

- French childminder contracts (assistante maternelle)
- distinction between facts, rights, and payments
- paid leave:
  - accrual
  - consumption
  - valuation (maintenance of salary vs one-tenth rule)
- full-year vs incomplete-year contracts
- retroactive recalculation and regularization

---

## Technical Skills

### Backend
- modern Python (typing, dataclasses, tests)
- FastAPI (simple usage, no advanced patterns)
- SQLAlchemy 2.x
- clean relational data modeling
- database migrations

### Frontend
- semantic HTML
- Jinja2 templates
- HTMX (pragmatic usage)
- lightweight JavaScript (DOM events, calendar UI)

---

## Architecture & Design

- flat, low-depth project structure
- refusal of unnecessary abstractions
- strict separation between:
  - stored data (facts)
  - business logic
  - orchestration / API layer

---

## Critical Review Skills

AI agents should be able to:
- reject trendy but inappropriate solutions
- propose simpler alternatives
- identify future pain points early
- clearly explain trade-offs

---

## Quality Bar

This project prioritizes:
- robustness
- human readability
- long-term maintainability

An AI agent should behave like a **demanding co-maintainer**, not a snippet factory.
