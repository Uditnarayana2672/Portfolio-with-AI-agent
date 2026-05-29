# domain/repositories

Repository **interfaces (ports)** — abstract base classes describing how the
application persists/loads aggregates, e.g. `MediaAssetRepository` with
`add`, `get`, `list`, `delete`. Declared here; **implemented** in
`app/infrastructure/persistence/repositories/`. The application layer depends
on these abstractions, never on the concrete SQLAlchemy implementations.
