# CommCare Connect Labs

This is a **labs/rapid prototyping environment** for CommCare Connect. It operates entirely via API against the production CommCare Connect instance — there is no direct database access to production data.

The repo also contains the full production CommCare Connect Django ORM codebase (opportunity models, user models, etc.). That code is inherited and **not relevant for labs development**. Do not query those models expecting production data — the tables are empty in this environment.

## Architecture at a Glance

- **OAuth session auth** — no Django User model for labs. `LabsUser` is transient (created from session each request, never saved to DB). Auth flow: `/labs/login/` → production OAuth → callback stores token in session.
- **All data via API** — `LabsRecordAPIClient` (`commcare_connect/labs/integrations/connect/api_client.py`) makes HTTP calls to `/export/labs_record/` on production for all CRUD.
- **data_access.py pattern** — each app wraps `LabsRecordAPIClient` in a `data_access.py` class with domain-specific methods.
- **Proxy models** — `LocalLabsRecord` subclasses provide typed `@property` access to JSON data. They cannot be `.save()`d locally.
- **Context middleware** — `request.labs_context` provides `opportunity_id`, `program_id`, `organization_id` on every request.

## App Map

| App              | Purpose                                                               | Key files                                                                        |
| ---------------- | --------------------------------------------------------------------- | -------------------------------------------------------------------------------- |
| `labs/`          | Core infrastructure: OAuth, API client, middleware, analysis pipeline | `integrations/connect/api_client.py`, `models.py`, `middleware.py`, `context.py` |
| `audit/`         | Quality assurance review of FLW visits                                | `data_access.py`, `ai_review.py`, `tasks.py`                                     |
| `tasks/`         | Task management for FLW follow-ups                                    | `data_access.py` (simplest example of the pattern)                               |
| `workflow/`      | Configurable workflow engine with React UIs and pipelines             | `data_access.py` (most complex), `templates/`                                    |
| `ai/`            | AI agent integration via pydantic-ai, SSE streaming                   | `agents/`, `views.py` (AIStreamView)                                             |
| `solicitations/` | RFP management (scoped by program, not opportunity)                   | `data_access.py`, `models.py`                                                    |
| `coverage/`      | Delivery unit mapping from CommCare HQ (separate OAuth)               | `data_access.py`, `data_loader.py`                                               |

**Cross-app connections:** Workflow can create audits and tasks. AI agents modify workflows and solicitations. Coverage is standalone.

## Key Commands

```bash
inv up                              # Start docker services (postgres, redis)
npm ci && inv build-js              # Install JS deps and build frontend
inv build-js -w                     # Build with watch mode (rebuilds on change)
python manage.py runserver          # Django dev server (uses config.settings.local)
pytest                              # Run tests
pytest commcare_connect/audit/      # Run tests for one app
celery -A config.celery_app worker -l info   # Celery worker (async audit creation, AI tasks)
pre-commit run --all-files          # Run linters/formatters
```

## Critical Warnings

- **DO NOT** query Django ORM models (`Opportunity`, `User`, `Organization`) expecting production data. Use `LabsRecordAPIClient`.
- **DO NOT** use `config.settings.labs` for local development. Use `config.settings.local` (the default). Labs settings are for the AWS deployment at `labs.connect.dimagi.com`.
- **DO NOT** call `.save()` on `LabsUser` or `LocalLabsRecord` — they raise `NotImplementedError`. Use `LabsRecordAPIClient` for persistence.
- **DO NOT** modify models in `opportunity/`, `organization/`, `program/`, or `users/` for labs features. That is production ORM code.
- New app URL prefixes must be added to `WHITELISTED_PREFIXES` in `commcare_connect/labs/middleware.py` or they will redirect to production.

## Deeper Documentation

- **[LABS_GUIDE.md](commcare_connect/labs/LABS_GUIDE.md)** — Detailed development patterns: OAuth setup, API client usage, proxy models, CLI scripts
- **[CONTRIBUTING.md](CONTRIBUTING.md)** — Code style, testing conventions, PR process, step-by-step guide for adding new features
- **[.claude/AGENTS.md](.claude/AGENTS.md)** — Full architecture reference: per-app details, API endpoints, data access patterns, common mistakes
- **[docs/LABS_ARCHITECTURE.md](docs/LABS_ARCHITECTURE.md)** — Architecture diagrams, data flow, cross-app dependency matrix, decision tree
- **[pr_guidelines.md](pr_guidelines.md)** — Pull request best practices
- **[new_architecture.md](new_architecture.md)** — Audit write-back architecture design (production-backed storage with OAuth scopes)
