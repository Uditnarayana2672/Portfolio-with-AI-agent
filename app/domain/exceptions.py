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


class BulkPermissionError(PermissionError):
    """One or more project IDs in a bulk request don't belong to the caller (→ HTTP 403).

    Carries the list of foreign IDs so the API can surface them in the error body.
    """

    def __init__(self, foreign_ids: list) -> None:
        super().__init__("One or more projects do not belong to you")
        self.foreign_ids = list(foreign_ids)


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


class PublishBlockedError(DomainError):
    """The project cannot be published because required fields are missing or
    content is incomplete (→ HTTP 422).

    Carries all human-readable issues so the API can surface them at once.
    """

    def __init__(self, issues: list[str]) -> None:
        super().__init__(f"Publish blocked: {', '.join(issues)}")
        self.issues = list(issues)


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


# ── Blog editor ──────────────────────────────────────────────────────────────


class BlogRuleError(ValidationError):
    """A blog post write breaks a rule (→ HTTP 422 with ``code``).

    ``code`` is the machine-readable error from the API spec (e.g.
    ``INVALID_CONTENT``, ``SCHEDULE_TOO_SOON``); ``detail`` carries context such
    as the JSON path of the offending node.
    """

    def __init__(self, code: str, message: str, detail: dict | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.detail = detail or {}


class ContentTooLargeError(BlogRuleError):
    """The serialized post body exceeds the size cap (→ HTTP 413)."""

    def __init__(self, max_bytes: int) -> None:
        super().__init__(
            "CONTENT_TOO_LARGE",
            "This post is too large — split it into a series.",
            {"max_bytes": max_bytes},
        )


class ChecklistFailedError(ValidationError):
    """Publishing or scheduling was refused because a checklist blocker failed
    (→ HTTP 422 CHECKLIST_FAILED). Carries the full checklist."""

    def __init__(self, checklist) -> None:
        super().__init__("Fix the blockers in the checklist before publishing.")
        self.checklist = checklist


class InvalidStateError(ConflictError):
    """The post is in the wrong state for this action (→ HTTP 409 with ``code``,
    e.g. NOT_PUBLISHED, ALREADY_PUBLISHED, NO_CHANGES)."""

    def __init__(self, code: str, message: str, detail: dict | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.detail = detail or {}


class VersionConflictError(ConflictError):
    """The client's ``version`` is stale — the post changed elsewhere
    (→ HTTP 409 VERSION_CONFLICT)."""

    def __init__(self, current_version: int, updated_at) -> None:
        super().__init__("Post was changed in another tab.")
        self.current_version = current_version
        self.updated_at = updated_at


class BlogNotFoundError(NotFoundError):
    """A blog post, revision or category is missing (→ HTTP 404 with ``code``)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class PortfolioContentNotFoundError(NotFoundError):
    """The portfolio content seed row is missing (→ HTTP 404 CONTENT_NOT_FOUND)."""
