"""Ports for the external services the public site uses (application layer)."""
from __future__ import annotations

from abc import ABC, abstractmethod


class EmailSender(ABC):
    @abstractmethod
    def send(self, *, to: str, subject: str, html: str, reply_to: str | None = None) -> bool:
        """Send one email. Returns False on failure instead of raising, because
        email must never undo work that is already saved."""


class CaptchaVerifier(ABC):
    @abstractmethod
    def verify(self, token: str | None, remote_ip: str | None) -> bool:
        """True when the token proves a human."""


class SiteDeployer(ABC):
    @abstractmethod
    def trigger(self, site: str) -> bool:
        """Ask the host to rebuild a site. False when it could not be requested."""
