# api/v1/schemas

Pydantic request/response models for the HTTP layer (e.g. `media.py` with
`MediaUploadRequest` / `MediaAssetResponse`). These are the wire format only;
they are translated to/from application DTOs in the endpoints. Created
per-feature.
