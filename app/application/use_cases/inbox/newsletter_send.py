"""Email a published post to confirmed subscribers (application layer)."""
from __future__ import annotations

import html
import time
import uuid
from dataclasses import dataclass

from app.application.interfaces.site_services import EmailSender
from app.application.use_cases.blog.post_workflow import BlogPostWorkflow
from app.domain.exceptions import ConflictError, InvalidStateError
from app.domain.repositories.inbox_repository import InboxRepository, Recipient

# The free email plan allows 100 messages a day. Sending stops short of a half-sent list.
DAILY_RECIPIENT_LIMIT = 100
SECONDS_BETWEEN_SENDS = 0.6


class NewsletterLimitError(ConflictError):
    """More subscribers than the plan can email in a day."""


class NewsletterAlreadySentError(ConflictError):
    """This post has already been emailed."""


@dataclass(frozen=True)
class PreparedSend:
    slug: str
    subject: str
    body: str
    url: str
    recipients: list[Recipient]


class PrepareNewsletterSend:
    def __init__(self, repo: InboxRepository, workflow: BlogPostWorkflow) -> None:
        self._repo = repo
        self._wf = workflow

    def execute(self, post_id: uuid.UUID, actor_id: uuid.UUID, version: int) -> PreparedSend:
        post = self._wf.load(post_id, actor_id)
        self._wf.check_version(post, version)
        if post.status != "published":
            raise InvalidStateError("NOT_PUBLISHED", "Only a published post can be emailed.")
        if self._repo.newsletter_already_sent(post_id):
            raise NewsletterAlreadySentError("This post has already been emailed to subscribers.")
        recipients = self._repo.active_recipients()
        if len(recipients) > DAILY_RECIPIENT_LIMIT:
            raise NewsletterLimitError(
                f"You have {len(recipients)} subscribers, but the email plan allows {DAILY_RECIPIENT_LIMIT} a day."
            )
        self._repo.record_newsletter_send(post_id, len(recipients))
        return PreparedSend(
            slug=post.slug,
            subject=post.title,
            body=post.excerpt or post.subtitle or "",
            url=self._wf.settings.public_url(post.slug),
            recipients=recipients,
        )


def deliver_newsletter(send: PreparedSend, email: EmailSender, blog_url: str) -> None:
    """Runs after the response, so it holds no database session."""
    for recipient in send.recipients:
        unsubscribe = f"{blog_url.rstrip('/')}/newsletter/unsubscribe?token={recipient.unsubscribe_token}"
        email.send(
            to=recipient.email,
            subject=send.subject,
            html=(
                f"<h2>{html.escape(send.subject)}</h2><p>{html.escape(send.body)}</p>"
                f'<p><a href="{html.escape(send.url)}">Read the note</a></p>'
                f'<p style="font-size:12px;color:#777"><a href="{html.escape(unsubscribe)}">Unsubscribe</a></p>'
            ),
        )
        time.sleep(SECONDS_BETWEEN_SENDS)
