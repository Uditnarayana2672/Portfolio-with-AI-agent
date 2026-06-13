"""Domain exceptions (innermost layer).

Framework-free errors raised by domain/application code. The API layer catches
these and maps them to HTTP status codes, so use cases never import FastAPI or
deal with HTTP themselves.
"""
# ruff: noqa: N818  – error class names intentionally end in "Error" not "Exception"
from __future__ import annotations


class DomainError(Exception):
    """Base class for all domain/application errors."""


class NotFoundError(DomainError):
    """A requested resource does not exist (→ HTTP 404)."""


class ConflictError(DomainError):
    """The operation conflicts with current state, e.g. duplicate (→ HTTP 409)."""


class SlugTakenError(ConflictError):
    """A slug is already owned by another project (→ HTTP 409 with suggested alternative)."""

    def __init__(self, slug: str, suggested: str) -> None:
        super().__init__(f"Slug {slug!r} is already in use")
        self.slug = slug
        self.suggested = suggested


class FeaturedLimitError(ConflictError):
    """Featuring this project would exceed the maximum number of featured
    projects allowed on the homepage (→ HTTP 409).

    Carries the configured cap so the API can return a precise message.
    """

    def __init__(self, max_featured: int) -> None:
        super().__init__(f"Featured project limit reached (max {max_featured})")
        self.max_featured = max_featured


class ValidationError(DomainError):
    """Input violates a business rule (→ HTTP 422)."""


class CodeTooLongError(ValidationError):
    """A code block's content exceeds the 50,000-character cap
    (→ HTTP 422 with error code ``CODE_TOO_LONG``)."""


class MediaInUseError(ConflictError):
    """A media asset is still referenced and ``force`` was not set (→ HTTP 409).

    Carries the usage total and the resolved references (each already paired
    with an admin deep link) so the API can return the in-use detail the
    delete-confirm modal renders.
    """

    def __init__(self, usage_count: int, references: list) -> None:
        super().__init__(f"Asset is referenced by {usage_count} places.")
        self.usage_count = usage_count
        self.references = references


class PermissionError(DomainError):
    """The caller is not allowed to perform this action (→ HTTP 403)."""


class UnsupportedFileTypeError(DomainError):
    """The uploaded file's type is not on the whitelist (→ HTTP 415).

    Carries the rejected extension and the allowed set so the API can return
    a structured ``{got, allowed}`` detail.
    """

    def __init__(self, got: str, allowed: tuple[str, ...]) -> None:
        super().__init__(f"Unsupported file type: {got!r}")
        self.got = got
        self.allowed = list(allowed)


class FileTooLargeError(DomainError):
    """The uploaded file exceeds the size cap for its type (→ HTTP 413)."""

    def __init__(self, max_bytes: int, limit: str) -> None:
        super().__init__(f"File exceeds the {limit} limit")
        self.max_bytes = max_bytes
        self.limit = limit


class StorageUploadError(DomainError):
    """The storage provider failed after exhausting retries (→ HTTP 502)."""

    def __init__(self, attempts: int, request_id: str | None) -> None:
        super().__init__(f"Storage upload failed after {attempts} attempts")
        self.attempts = attempts
        self.request_id = request_id


class BlockReorderError(DomainError):
    """A block reorder request violates an ordering constraint (→ HTTP 400).

    Carries a machine-readable ``error_code`` (e.g. EMPTY_BLOCK_IDS) so the
    API layer can return the exact error shape the spec requires without
    hard-coding string comparisons.
    """

    def __init__(self, error_code: str, message: str) -> None:
        super().__init__(message)
        self.error_code = error_code


class InvalidUrlError(DomainError):
    """The supplied URL is malformed or uses a disallowed scheme (→ HTTP 400)."""


class BlockedUrlError(DomainError):
    """The URL resolves to a private/loopback/link-local host and is refused as
    an SSRF risk (→ HTTP 400)."""


class UrlFetchError(DomainError):
    """Fetching the remote URL failed — timeout, connection error, or a 4xx/5xx
    from the source (→ HTTP 422)."""


class EmptyFileError(DomainError):
    """The uploaded file contains zero bytes (→ HTTP 400 EMPTY_FILE)."""


class InvalidFolderError(DomainError):
    """The specified folder is not in the allowed list (→ HTTP 400 INVALID_FOLDER).

    Carries the rejected value and the allowed set for the error body.
    """

    def __init__(self, folder: str, allowed: tuple[str, ...]) -> None:
        allowed_list = list(allowed)
        super().__init__(
            f"Folder {folder!r} is not allowed. Allowed: {allowed_list}"
        )
        self.folder = folder
        self.allowed = allowed_list


class ResourceTypeMismatchError(DomainError):
    """The declared resource_type contradicts the file extension (→ HTTP 400).

    E.g. passing resource_type='image' for a .mp4 file.
    """

    def __init__(self, declared: str, inferred: str, ext: str) -> None:
        super().__init__(
            f"resource_type {declared!r} conflicts with .{ext} extension "
            f"(expected {inferred!r})"
        )
        self.declared = declared
        self.inferred = inferred
        self.ext = ext
