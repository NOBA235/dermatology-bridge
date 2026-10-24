# Technical Debt & Deferred Items

> For clinician review — not a diagnosis.

This document tracks cross-phase changes or scope adjustments deferred until after Phase 6 per working agreements.

## Log

- **Phase 0**: Local environment supports SQLite dialect fallback (`sqlite:///./dermobridge.db`) when a local PostgreSQL/Neon connection is not active, while SQLAlchemy models and `0001_initial.py` preserve full PostgreSQL types (`UUID`, `TIMESTAMPTZ`, `JSONB`, `BIGSERIAL`, partial indexes, `pgcrypto` `gen_random_uuid()`).
