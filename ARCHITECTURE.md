# Backend Architecture — Onion Architecture

This backend follows **Onion Architecture**. Every feature we build (Media
Manager, Blog, Projects, the Jerry AI assistant, …) is structured into the same
four concentric layers. The one rule that makes it "onion":

> **Dependencies point inward only.** Outer layers know about inner layers;
> inner layers know *nothing* about outer ones. The domain at the center has
> zero dependencies on frameworks, the database, or any third-party SDK.

```
        ┌─────────────────────────────────────────────┐
        │                 API / Presentation            │   app/api/
        │   (FastAPI routers, schemas, DI wiring)        │
        │   ┌─────────────────────────────────────────┐ │
        │   │            Infrastructure                 │ │   app/infrastructure/
        │   │  (SQLAlchemy, Cloudinary, Supabase,       │ │
        │   │   config) — IMPLEMENTS inner interfaces   │ │
        │   │   ┌─────────────────────────────────────┐ │ │
        │   │   │           Application               │ │ │   app/application/
        │   │   │   (use cases, ports/interfaces,     │ │ │
        │   │   │    DTOs) — orchestrates the domain  │ │ │
        │   │   │   ┌───────────────────────────────┐ │ │ │
        │   │   │   │           Domain              │ │ │ │   app/domain/
        │   │   │   │  (entities, repository ports, │ │ │ │
        │   │   │   │   enums, domain exceptions)   │ │ │ │
        │   │   │   │      NO dependencies          │ │ │ │
        │   │   │   └───────────────────────────────┘ │ │ │
        │   │   └─────────────────────────────────────┘ │ │
        │   └─────────────────────────────────────────┘ │
        └─────────────────────────────────────────────┘
```

---

## Layer 1 — Domain (`app/domain/`) — the core

Pure business concepts. No FastAPI, no SQLAlchemy, no Cloudinary imports here.

| Folder/file | Holds |
|---|---|
| `entities/` | Plain business objects (e.g. `MediaAsset`) — framework-free dataclasses. |
| `repositories/` | **Repository interfaces (ports)** — abstract contracts like `MediaAssetRepository` (ABCs). *Declared* here, *implemented* in infrastructure. |
| `enums.py` | Domain enums shared across features. |
| `exceptions.py` | Domain exceptions (`NotFoundError`, `ConflictError`, …) — mapped to HTTP codes at the API edge. |

Depends on: **nothing**.

## Layer 2 — Application (`app/application/`) — use cases

The "what the app does" layer. Orchestrates domain entities through repository
ports to fulfil one business operation each.

| Folder | Holds |
|---|---|
| `use_cases/` | One class per operation (e.g. `UploadMedia`, `ListMedia`, `DeleteMedia`). Receives ports via constructor injection; contains the workflow, not the DB/SDK details. |
| `interfaces/` | **Ports for infrastructure services** the use cases need but don't implement — e.g. `ImageStorage` (Cloudinary abstraction). |
| `dtos/` | Plain input/output data for use cases, decoupled from HTTP request/response shapes. |

Depends on: **domain only**.

## Layer 3 — Infrastructure (`app/infrastructure/`) — adapters

Concrete implementations of the interfaces declared inward. This is the only
layer allowed to import SQLAlchemy, Cloudinary, Supabase, httpx, etc.

| Folder/file | Holds |
|---|---|
| `config.py` | `Settings` (pydantic-settings, loads `.env`). |
| `persistence/database.py` | SQLAlchemy `Base`, `engine`, `SessionLocal`, `get_db`. |
| `persistence/orm/` | SQLAlchemy ORM models (the physical table mappings). |
| `persistence/repositories/` | Repository **implementations** (e.g. `SqlAlchemyMediaAssetRepository`) that satisfy the domain ports. |
| `external/cloudinary_storage.py` | `CloudinaryImageStorage` implementing the `ImageStorage` port. |
| `external/supabase_auth.py` | Supabase JWT/JWKS verification. |

Depends on: **domain + application** (to implement their interfaces).

## Layer 4 — API / Presentation (`app/api/`) — the edge

Thin HTTP layer. Converts requests → use-case calls → responses. No business
logic lives here.

| Folder/file | Holds |
|---|---|
| `v1/endpoints/` | FastAPI routers (thin controllers). |
| `v1/schemas/` | Pydantic request/response models. |
| `v1/dependencies/auth.py` | `get_current_user` / `get_current_admin`. |
| `v1/dependencies/providers.py` | **Composition root**: builds repositories + services and injects them into use cases for each request. |
| `v1/router.py` | Aggregates all feature routers under `/api/v1`. |

Depends on: **application** (calls use cases) and wires in **infrastructure** via `providers.py`.

`app/main.py` is the application entry point / outermost composition root.

---

## How a request flows (Media upload, as an example)

```
HTTP POST /api/v1/media
  → endpoints/media.py            (parse request, call use case)
  → providers.py                  (inject SqlAlchemyMediaAssetRepository + CloudinaryImageStorage)
  → use_cases/media/upload_media.py  (orchestrate: store image, persist entity)
        ├── ImageStorage port      → CloudinaryImageStorage (infra)
        └── MediaAssetRepository port → SqlAlchemyMediaAssetRepository (infra)
  → domain entity MediaAsset       (business rules)
  ← response schema                (serialize back to JSON)
```

## Rules of thumb when adding a feature
1. Start in the **domain**: entity + repository interface.
2. Add **application** use cases + any new port + DTOs.
3. Implement ports in **infrastructure** (ORM model, repository, adapters).
4. Expose it in **API**: schema, endpoint, and wire it in `providers.py`.
5. Never import outward (domain must not import infrastructure/api).
