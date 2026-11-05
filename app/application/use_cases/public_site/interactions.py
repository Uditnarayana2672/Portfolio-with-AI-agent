"""Things visitors do: views, reactions, polls, comments, contact, newsletter."""
from __future__ import annotations

import datetime
import html
import secrets
import uuid
from dataclasses import dataclass

from app.application.interfaces.site_services import CaptchaVerifier, EmailSender
from app.domain.exceptions import ConflictError, NotFoundError, ValidationError
from app.domain.repositories.activity_log_repository import ActivityLogRepository
from app.domain.repositories.public_site_repository import PublicSiteRepository

ALLOWED_REACTIONS = frozenset({"like", "love", "fire", "clap", "mind_blown"})
CONFIRM_LIFETIME = datetime.timedelta(days=7)


class CaptchaFailedError(ValidationError):
    """The spam check did not pass (→ HTTP 400 CAPTCHA_FAILED)."""


class CommentsClosedError(ConflictError):
    """Comments are off for this post (→ HTTP 403 COMMENTS_CLOSED)."""


class AlreadyVotedError(ConflictError):
    """This browser already voted (→ HTTP 409 ALREADY_VOTED)."""


class PollClosedError(ConflictError):
    """The poll has expired (→ HTTP 409 POLL_CLOSED)."""


class TokenExpiredError(ValidationError):
    """An email link is unknown or too old (→ HTTP 410 TOKEN_EXPIRED)."""


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


class Engagement:
    def __init__(self, repo: PublicSiteRepository) -> None:
        self._repo = repo

    def record_view(self, kind: str, content_id: uuid.UUID, path: str, session_id: str | None) -> None:
        self._repo.record_view(kind, content_id, path, session_id)

    def react(self, kind: str, content_id: uuid.UUID, reaction: str, session_id: str | None) -> dict[str, int]:
        if reaction not in ALLOWED_REACTIONS:
            raise ValidationError(f"reaction_type must be one of: {sorted(ALLOWED_REACTIONS)}")
        self._repo.add_reaction(kind, content_id, reaction, session_id)
        return self._repo.reaction_counts(kind, content_id)

    def reactions(self, kind: str, content_id: uuid.UUID) -> dict[str, int]:
        counts = self._repo.reaction_counts(kind, content_id)
        return {r: counts.get(r, 0) for r in sorted(ALLOWED_REACTIONS)}


@dataclass(frozen=True)
class PollResult:
    question: str
    status: str
    total_votes: int
    show_results: bool
    options: list[dict]
    my_vote: int | None


class PublicPolls:
    def __init__(self, repo: PublicSiteRepository) -> None:
        self._repo = repo

    def _block(self, block_id: uuid.UUID):
        block = self._repo.public_poll_block(block_id)
        if block is None:
            raise NotFoundError("Poll not found.")
        return block

    @staticmethod
    def _is_closed(config: dict) -> bool:
        raw = config.get("expiry_date")
        if not raw:
            return False
        try:
            expiry = datetime.datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except ValueError:
            return False
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=datetime.timezone.utc)
        return expiry <= _now()

    def _result(self, block, poll_id: uuid.UUID | None, session_id: str | None) -> PollResult:
        config = block.config
        labels = [str(o) for o in config.get("options") or []]
        # No poll row yet, or its options changed: nobody has voted on this version.
        tallies = self._repo.poll_tallies(poll_id) if poll_id else {}
        total = sum(tallies.values())
        my_vote = self._repo.poll_vote_of(poll_id, session_id) if poll_id and session_id else None
        closed = self._is_closed(config)
        # show_results off: only reveal numbers to someone who voted, or once closed.
        reveal = config.get("show_results", True) is not False or my_vote is not None or closed
        options = []
        for index, label in enumerate(labels):
            votes = tallies.get(index, 0)
            options.append({
                "index": index,
                "label": label,
                "votes": votes if reveal else None,
                "percent": (round(votes * 100 / total) if total else 0) if reveal else None,
            })
        return PollResult(
            question=str(config.get("question") or ""),
            status="closed" if closed else "open",
            total_votes=total if reveal else 0,
            show_results=reveal,
            options=options,
            my_vote=my_vote,
        )

    def get(self, block_id: uuid.UUID, session_id: str | None) -> PollResult:
        block = self._block(block_id)
        return self._result(block, self._repo.current_poll_id(block), session_id)

    def vote(self, block_id: uuid.UUID, option_index: int, session_id: str) -> PollResult:
        block = self._block(block_id)
        if self._is_closed(block.config):
            raise PollClosedError("This poll has closed.")
        if not 0 <= option_index < len(block.config.get("options") or []):
            raise ValidationError("That option does not exist.")
        poll_id = self._repo.ensure_poll(block)
        if not self._repo.add_poll_vote(poll_id, option_index, session_id):
            raise AlreadyVotedError("You have already voted in this poll.")
        return self._result(block, poll_id, session_id)


class PublicComments:
    def __init__(self, repo: PublicSiteRepository, captcha: CaptchaVerifier) -> None:
        self._repo = repo
        self._captcha = captcha

    def list(self, post_id: uuid.UUID) -> list[dict]:
        rows = self._repo.approved_comments(post_id)
        tops: dict[uuid.UUID, dict] = {}
        for row in rows:
            if row.parent_id is None:
                tops[row.id] = {**row.__dict__, "replies": []}
        for row in rows:
            if row.parent_id in tops:
                tops[row.parent_id]["replies"].append(row.__dict__)
        return list(tops.values())

    def add(
        self, *, post_id: uuid.UUID, comments_open: bool, parent_id: uuid.UUID | None, name: str, email: str | None,
        content: str, token: str | None, ip: str | None, honeypot: str | None,
    ) -> None:
        if not comments_open:
            raise CommentsClosedError("Comments are closed on this post.")
        if honeypot:  # a bot filled the hidden field: pretend it worked
            return
        if not self._captcha.verify(token, ip):
            raise CaptchaFailedError("The spam check did not pass. Please try again.")
        if parent_id is not None and self._repo.comment_post_id(parent_id) != post_id:
            raise ValidationError("That comment isn't on this post.")
        self._repo.add_comment(post_id=post_id, parent_id=parent_id, name=name, email=email, content=content)


class SubmitContactMessage:
    def __init__(
        self, repo: PublicSiteRepository, activity: ActivityLogRepository, captcha: CaptchaVerifier,
        email: EmailSender, notify_to: str,
    ) -> None:
        self._repo = repo
        self._activity = activity
        self._captcha = captcha
        self._email = email
        self._notify_to = notify_to

    def execute(
        self, *, name: str, email: str, subject: str, message: str, token: str | None, ip: str | None,
        honeypot: str | None,
    ) -> None:
        if honeypot:
            return
        if not self._captcha.verify(token, ip):
            raise CaptchaFailedError("The spam check did not pass. Please try again.")
        # Saved first: if the notification email fails, the message is still in the Inbox.
        self._repo.add_contact_message(name=name, email=email, subject=subject, message=message)
        self._activity.record(
            action_type="contact_received",
            description=f"New message from {name}: {subject}",
            entity_type="contact_message",
        )
        if self._notify_to:
            self._email.send(
                to=self._notify_to,
                subject=f"New message: {subject}",
                reply_to=email,
                html=(
                    f"<p><strong>{html.escape(name)}</strong> &lt;{html.escape(email)}&gt;</p>"
                    f"<p>{html.escape(message).replace(chr(10), '<br>')}</p>"
                ),
            )


class Newsletter:
    def __init__(
        self, repo: PublicSiteRepository, activity: ActivityLogRepository, captcha: CaptchaVerifier,
        email: EmailSender, blog_url: str,
    ) -> None:
        self._repo = repo
        self._activity = activity
        self._captcha = captcha
        self._email = email
        self._blog_url = blog_url.rstrip("/")

    def subscribe(self, *, email: str, token: str | None, ip: str | None, honeypot: str | None) -> None:
        if honeypot:
            return
        if not self._captcha.verify(token, ip):
            raise CaptchaFailedError("The spam check did not pass. Please try again.")
        existing = self._repo.subscriber_by_email(email)
        if existing and existing.status == "active":
            return  # same answer as a new address, so nobody can test who's subscribed
        confirm = secrets.token_urlsafe(32)
        self._repo.save_pending_subscriber(email, confirm, _now() + CONFIRM_LIFETIME)
        link = f"{self._blog_url}/newsletter/confirm?token={confirm}"
        self._email.send(
            to=email,
            subject="Confirm your subscription to LighthouseInfo",
            html=(
                "<p>Please confirm you'd like new notes from LighthouseInfo by email.</p>"
                f'<p><a href="{html.escape(link)}">Confirm my subscription</a></p>'
                "<p>If this wasn't you, ignore this email and nothing will happen.</p>"
            ),
        )

    def confirm(self, token: str) -> None:
        subscriber = self._repo.subscriber_by_confirm_token(token)
        expires = subscriber.confirm_expires_at if subscriber else None
        if subscriber is None or expires is None or expires <= _now():
            raise TokenExpiredError("This confirmation link has expired. Please subscribe again.")
        self._repo.activate_subscriber(subscriber.id, _now())
        self._activity.record(
            action_type="subscriber_added",
            description="New newsletter subscriber confirmed.",
            entity_type="subscriber",
            entity_id=subscriber.id,
        )

    def unsubscribe(self, token: str) -> None:
        # Repeating, or an unknown token, is still a success: there's nothing to undo.
        self._repo.unsubscribe(token, _now())
