# application/dtos

Plain input/output data structures for use cases (dataclasses), decoupled from
HTTP request/response shapes in `app/api/v1/schemas/`. Created per-feature, e.g.
`media.py` with `UploadMediaInput` / `MediaAssetOutput`.
