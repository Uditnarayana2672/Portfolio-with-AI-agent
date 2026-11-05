"""HTTP adapters for Resend, Cloudflare Turnstile and Cloudflare Pages."""
from __future__ import annotations

import logging

import httpx

from app.application.interfaces.site_services import CaptchaVerifier, EmailSender, SiteDeployer

logger = logging.getLogger("app.site_services")
_TIMEOUT = 10.0


class ResendEmailSender(EmailSender):
    def __init__(self, api_key: str, sender: str) -> None:
        self._api_key = api_key
        self._sender = sender

    def send(self, *, to: str, subject: str, html: str, reply_to: str | None = None) -> bool:
        if not self._api_key:
            logger.info("Email not sent (RESEND_API_KEY is empty): %s", subject)
            return False
        body = {"from": self._sender, "to": [to], "subject": subject, "html": html}
        if reply_to:
            body["reply_to"] = reply_to
        try:
            res = httpx.post(
                "https://api.resend.com/emails",
                json=body,
                headers={"Authorization": f"Bearer {self._api_key}"},
                timeout=_TIMEOUT,
            )
            res.raise_for_status()
            return True
        except httpx.HTTPError as exc:
            logger.warning("Email failed: %s", exc)
            return False


class TurnstileVerifier(CaptchaVerifier):
    def __init__(self, secret: str) -> None:
        self._secret = secret

    def verify(self, token: str | None, remote_ip: str | None) -> bool:
        if not self._secret:  # local development
            return True
        if not token:
            return False
        try:
            res = httpx.post(
                "https://challenges.cloudflare.com/turnstile/v0/siteverify",
                data={"secret": self._secret, "response": token, "remoteip": remote_ip or ""},
                timeout=_TIMEOUT,
            )
            return bool(res.json().get("success"))
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("Turnstile check failed: %s", exc)
            return False


class CloudflareDeployer(SiteDeployer):
    def __init__(self, hooks: dict[str, str]) -> None:
        self._hooks = hooks

    def trigger(self, site: str) -> bool:
        hook = self._hooks.get(site)
        if not hook:
            logger.info("No deploy hook set for %s; rebuild stays queued.", site)
            return False
        try:
            httpx.post(hook, timeout=_TIMEOUT).raise_for_status()
            return True
        except httpx.HTTPError as exc:
            logger.warning("Deploy hook failed for %s: %s", site, exc)
            return False
