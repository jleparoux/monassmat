# AGENTS.md – Rules for AI Assistants

This project is intentionally simple, pragmatic, and conservative.
Any AI assistant contributing to this codebase MUST follow the rules below.

Failure to respect these rules is considered a regression.

---

## Core Principles (DO NOT VIOLATE)

1. **Do not introduce unnecessary abstractions**
   - No DDD layers
   - No service/repository/factory patterns
   - No hexagonal or clean architecture

2. **Do not increase directory depth**
   - Maximum depth: 2
   - Prefer new files over new folders

3. **Do not persist derived data**
   - Database stores facts only
   - All computed values must be recalculable

4. **Do not mix concerns**
   - ORM models → structure only
   - Business logic → pure Python
   - API layer → orchestration only

---

## File Responsibilities (STRICT)

- `models.py`
  - SQLAlchemy models only
  - Constraints, relationships
  - NO business logic

- `logic.py`
  - Pure functions
  - No FastAPI, no ORM, no DB access
  - Fully testable in isolation

- `crud.py`
  - Simple DB access helpers
  - No calculations

- `app.py`
  - FastAPI routes
  - Dependency injection
  - Calls `crud` and `logic`

- `schemas.py`
  - Pydantic input/output schemas
  - Validation only

---

## Allowed Technologies

Backend:
- Python 3.x
- FastAPI
- SQLAlchemy 2.x
- Pydantic v2
- Alembic
- pytest

Frontend:
- Jinja2 templates
- HTMX
- Vanilla JavaScript (existing calendar logic)

Database:
- PostgreSQL (preferred)
- SQLite (temporary only)

---

## Forbidden Practices

- Storing computed totals in DB
- Introducing async complexity without need
- Introducing background jobs, queues, caches
- Rewriting working JS in React/Vue/etc.
- Over-optimizing performance

---

## How to Extend the Project

When adding a feature:
1. Update `README.md` (functional behavior)
2. Add or update DB facts if needed
3. Implement pure logic in `logic.py`
4. Expose via API if necessary
5. Add tests for logic first

---

## Decision Rule

If unsure between:
- simple vs clever → choose simple
- explicit vs generic → choose explicit
- duplication vs abstraction → allow duplication

This is a personal, long-term maintainable tool.
Not a framework. Not a product.
