# SKILLS.md – Expected Skills & Knowledge

This document describes the skills expected from contributors
(human or AI) interacting with this project.

---

## Domain Knowledge (Required)

- French childcare employment rules (assistant(e) maternel(le))
- Monthly salary vs actual worked hours
- Paid leave concepts:
  - acquisition period
  - days taken
  - salary maintenance
  - 10% rule
- Importance of historical correctness

You are not required to know all rules,
but you must NOT invent them.

When unsure: ask or isolate assumptions.

---

## Backend Engineering

- Python (clean, readable, explicit)
- SQLAlchemy 2.x ORM usage
- Relational data modeling
- Alembic migrations
- Writing testable pure functions

---

## Software Design Mindset

- Favor clarity over abstraction
- Respect existing architectural constraints
- Avoid premature optimization
- Be comfortable with flat architectures
- Think in terms of data invariants

---

## Frontend Integration

- Jinja2 templating
- HTMX request/response patterns
- Vanilla JavaScript interop
- Server-driven UI philosophy

---

## Testing & Reliability

- pytest basics
- Edge cases over happy paths
- Deterministic behavior
- Reproducibility of calculations

---

## What You Should NOT Do

- Assume scalability constraints
- Introduce modern frontend stacks without justification
- Apply enterprise patterns
- “Improve” structure without justification

---

## Success Criteria

A contribution is successful if:
- It reduces ambiguity
- It improves correctness
- It keeps the project simple
- It does not surprise the maintainer
