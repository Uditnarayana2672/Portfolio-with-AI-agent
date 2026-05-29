# application/use_cases

One class per business operation (e.g. `media/upload_media.py` → `UploadMedia`).
Each receives its ports (repositories, `ImageStorage`, …) via the constructor
and exposes a single `execute(...)`. Contains the workflow only — no SQL, no SDK
calls, no HTTP. Created per-feature.
