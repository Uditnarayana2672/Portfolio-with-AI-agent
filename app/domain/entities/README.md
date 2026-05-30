# domain/entities

Pure business objects — framework-free (no SQLAlchemy/FastAPI imports).
Implemented as plain dataclasses. One file per aggregate, e.g. `media_asset.py`
defining a `MediaAsset` entity. These are created per-feature.
