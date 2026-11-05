"""Tests for the public site and admin inbox APIs, using in-memory fakes."""
from __future__ import annotations

import datetime
import uuid
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from app.api.v1.dependencies.auth import get_current_admin, get_current_user
from app.api.v1.dependencies.providers import (
    get_inbox_repository,
    get_list_public_projects,
    get_public_polls,
    get_public_site_repository,
    get_site_builds,
    get_submit_contact_message,
    get_newsletter,
)
from app.api.v1.dependencies.rate_limit import reset_rate_limits
from app.application.use_cases.public_site.interactions import (
    CaptchaFailedError,
    Newsletter,
    PublicComments,
    PublicPolls,
    SubmitContactMessage,
    TokenExpiredError,
)
from app.application.use_cases.public_site.projects import ListPublicProjects
from app.application.use_cases.public_site.site_builds import SiteBuilds
from app.domain.entities.project import Project
from app.domain.portfolio_document import PROJECT_COUNT_SOURCE, resolve_stats, upgrade_document
from app.domain.repositories.public_site_repository import PollBlock, PublicComment, Subscriber
from app.domain.repositories.site_build_repository import SiteBuildState
from app.infrastructure.persistence.orm.models import UserRole
from app.main import app

_NOW = datetime.datetime(2026, 11, 5, 12, 0, tzinfo=datetime.timezone.utc)
_ADMIN = SimpleNamespace(id=uuid.uuid4(), name="Udit")


def _project(slug: str, *, featured=False, meta=None, tech=("Python",), thumb=None) -> Project:
    return Project(
        id=uuid.uuid4(), title=slug.title(), slug=slug, excerpt="x", thumbnail_url=thumb, tech_stack=list(tech),
        template_id="narrative", github_url=None, demo_url=None, status="published", visibility="public",
        is_featured=featured, views=0, seo={}, meta=meta or {}, author_id=_ADMIN.id, published_at=_NOW,
        created_at=_NOW, updated_at=_NOW,
    )


@pytest.fixture(autouse=True)
def _clean():
    reset_rate_limits()
    yield
    app.dependency_overrides.clear()
    reset_rate_limits()


# ── portfolio document ───────────────────────────────────────────────────────


def _old_doc() -> dict:
    return {
        "hero": {"eyebrow": "x", "currently_building": {"title": "Jerry"}},
        "about": {"stats": [
            {"id": "a", "value": "40", "suffix": "%", "label": "less reporting"},
            {"id": "b", "value": "1000", "suffix": "+", "label": "student conversations on career paths"},
        ]},
    }


def test_upgrade_removes_card_and_converts_student_stat():
    doc = upgrade_document(_old_doc())
    assert "currently_building" not in doc["hero"]
    assert doc["hero"]["portrait"] is None
    assert doc["about"]["stats"][0]["source"] == "manual"
    converted = doc["about"]["stats"][1]
    assert converted["source"] == PROJECT_COUNT_SOURCE
    assert converted["value"] is None and converted["label"] == "scalable projects"


def test_upgrade_is_stable_and_leaves_edited_labels_alone():
    once = upgrade_document(_old_doc())
    once["about"]["stats"][1]["label"] = "real projects"
    assert upgrade_document(once) == once


def test_upgrade_keeps_only_the_first_tech_category():
    doc = upgrade_document({"tech": [{"id": "d", "name": "Docker", "categories": ["backend", "cloud"]}]})
    assert doc["tech"][0]["category"] == "backend"
    assert "categories" not in doc["tech"][0]


def test_upgrade_does_not_overwrite_a_chosen_category():
    doc = upgrade_document({"tech": [{"id": "d", "category": "cloud", "categories": ["backend"]}]})
    assert doc["tech"][0]["category"] == "cloud"


def test_upgrade_adds_job_media_slots_without_touching_existing_ones():
    doc = upgrade_document({"experience": [
        {"id": "a", "company": "IBM"},
        {"id": "b", "company": "X", "logo": {"url": "https://x.test/l.png"}, "images": [{"url": "https://x.test/i.jpg"}]},
    ]})
    assert doc["experience"][0]["logo"] is None and doc["experience"][0]["images"] == []
    assert doc["experience"][1]["logo"] == {"url": "https://x.test/l.png"}
    assert doc["experience"][1]["images"] == [{"url": "https://x.test/i.jpg"}]


def test_upgrade_seeds_education_once_and_keeps_later_edits():
    doc = upgrade_document(_old_doc())
    assert [e["start_year"] for e in doc["education"]] == [2016, 2023]
    doc["education"] = []
    doc["education_section"]["title"] = "Mine"
    again = upgrade_document(doc)
    assert again["education"] == [] and again["education_section"]["title"] == "Mine"


def test_upgrade_drops_removed_through_line_labels():
    doc = upgrade_document({"about": {"stats": [], "through_line": ["A", "B", "C"]}})
    assert "through_line" not in doc["about"]


def test_upgrade_does_not_share_defaults_between_documents():
    first = upgrade_document({})
    first["education"][0]["highlights"].append("changed")
    assert "changed" not in upgrade_document({})["education"][0]["highlights"]


def test_resolve_fills_in_real_project_count():
    resolved = resolve_stats(upgrade_document(_old_doc()), 12)
    assert resolved["about"]["stats"][1]["value"] == "12"
    assert resolved["about"]["stats"][0]["value"] == "40"


# ── project list ─────────────────────────────────────────────────────────────


def _projects_repo(*rows):
    repo = Mock()
    repo.list_public_projects.return_value = list(rows)
    return repo


def test_featured_first_then_newest_keeps_order():
    repo = _projects_repo(
        (_project("new"), None), (_project("star", featured=True), None), (_project("old"), None),
    )
    cards, total, _ = ListPublicProjects(repo).execute(
        featured=None, category=None, tech=None, sort="featured", limit=3, offset=0,
    )
    assert [c.project.slug for c in cards] == ["star", "new", "old"] and total == 3


def test_thumbnail_wins_then_hero_then_nothing():
    repo = _projects_repo(
        (_project("a", thumb="https://t"), "https://h"), (_project("b"), "https://h"), (_project("c"), None),
    )
    cards, _, _ = ListPublicProjects(repo).execute(
        featured=None, category=None, tech=None, sort="newest", limit=3, offset=0,
    )
    assert [c.image_url for c in cards] == ["https://t", "https://h", None]


def test_filters_and_category_counts():
    repo = _projects_repo(
        (_project("a", meta={"category": "AI"}, tech=("Python",)), None),
        (_project("b", meta={"category": "Web"}, tech=("React",)), None),
    )
    use_case = ListPublicProjects(repo)
    cards, total, categories = use_case.execute(featured=None, category="AI", tech=None, sort="newest", limit=5, offset=0)
    assert [c.project.slug for c in cards] == ["a"] and total == 1
    assert categories == [("AI", 1), ("Web", 1)]
    cards, _, _ = use_case.execute(featured=None, category=None, tech="react", sort="newest", limit=5, offset=0)
    assert [c.project.slug for c in cards] == ["b"]


def test_project_list_endpoint_shape_and_card_stat():
    repo = _projects_repo((_project("a", meta={"card_stat_value": "12k", "card_stat_label": "chats"}), None))
    app.dependency_overrides[get_list_public_projects] = lambda: ListPublicProjects(repo)
    res = TestClient(app).get("/api/v1/projects")
    assert res.status_code == 200
    item = res.json()["items"][0]
    assert item["card_stat"] == {"value": "12k", "label": "chats"}
    assert "status" not in item and "visibility" not in item


# ── polls ────────────────────────────────────────────────────────────────────


def _poll_repo(*, config=None, tallies=None, my_vote=None, added=True):
    repo = Mock()
    cfg = {"question": "Q?", "options": ["A", "B"], "show_results": True, **(config or {})}
    repo.public_poll_block.return_value = PollBlock(uuid.uuid4(), cfg)
    repo.ensure_poll.return_value = uuid.uuid4()
    repo.poll_tallies.return_value = tallies or {}
    repo.poll_vote_of.return_value = my_vote
    repo.add_poll_vote.return_value = added
    return repo


def test_poll_counts_are_real_not_invented():
    result = PublicPolls(_poll_repo(tallies={0: 3, 1: 1})).get(uuid.uuid4(), None)
    assert result.total_votes == 4
    assert [(o["votes"], o["percent"]) for o in result.options] == [(3, 75), (1, 25)]


def test_reading_a_poll_never_writes():
    repo = _poll_repo()
    repo.current_poll_id.return_value = None
    result = PublicPolls(repo).get(uuid.uuid4(), "session-1")
    repo.ensure_poll.assert_not_called()
    repo.poll_tallies.assert_not_called()
    assert result.total_votes == 0 and result.my_vote is None


def test_poll_with_no_votes_shows_zero():
    result = PublicPolls(_poll_repo()).get(uuid.uuid4(), None)
    assert result.total_votes == 0 and result.options[0]["votes"] == 0


def test_hidden_results_until_voted():
    hidden = PublicPolls(_poll_repo(config={"show_results": False}, tallies={0: 3})).get(uuid.uuid4(), "session-1")
    assert hidden.options[0]["votes"] is None and hidden.total_votes == 0
    voted = PublicPolls(_poll_repo(config={"show_results": False}, tallies={0: 3}, my_vote=0)).get(uuid.uuid4(), "session-1")
    assert voted.options[0]["votes"] == 3


def _poll_client(repo):
    app.dependency_overrides[get_public_polls] = lambda: PublicPolls(repo)
    return TestClient(app)


def test_vote_endpoint_and_double_vote():
    url = f"/api/v1/project-blocks/{uuid.uuid4()}/poll/votes"
    body = {"option_index": 0, "session_id": "session-123"}
    assert _poll_client(_poll_repo()).post(url, json=body).status_code == 201
    res = _poll_client(_poll_repo(added=False)).post(url, json=body)
    assert res.status_code == 409 and res.json()["detail"]["error"] == "ALREADY_VOTED"


def test_vote_for_missing_option_is_rejected():
    res = _poll_client(_poll_repo()).post(
        f"/api/v1/project-blocks/{uuid.uuid4()}/poll/votes", json={"option_index": 9, "session_id": "session-123"},
    )
    assert res.status_code == 422


def test_closed_poll_rejects_votes():
    res = _poll_client(_poll_repo(config={"expiry_date": "2020-01-01"})).post(
        f"/api/v1/project-blocks/{uuid.uuid4()}/poll/votes", json={"option_index": 0, "session_id": "session-123"},
    )
    assert res.status_code == 409 and res.json()["detail"]["error"] == "POLL_CLOSED"


def test_poll_on_unpublished_project_is_404():
    repo = _poll_repo()
    repo.public_poll_block.return_value = None
    assert _poll_client(repo).get(f"/api/v1/project-blocks/{uuid.uuid4()}/poll").status_code == 404


# ── contact ──────────────────────────────────────────────────────────────────


def _contact(captcha_ok=True, notify="me@example.com"):
    repo, activity, captcha, email = Mock(), Mock(), Mock(), Mock()
    captcha.verify.return_value = captcha_ok
    email.send.return_value = True
    return SubmitContactMessage(repo, activity, captcha, email, notify), repo, activity, email


_MESSAGE = dict(name="A", email="a@b.co", subject="Hi", message="<b>Hello</b>", token="t", ip="1.1.1.1")


def test_contact_saves_logs_and_emails_with_reply_to():
    use_case, repo, activity, email = _contact()
    use_case.execute(**_MESSAGE, honeypot=None)
    repo.add_contact_message.assert_called_once()
    assert activity.record.call_args.kwargs["action_type"] == "contact_received"
    sent = email.send.call_args.kwargs
    assert sent["reply_to"] == "a@b.co" and "<b>" not in sent["html"]


def test_contact_saved_even_when_email_fails():
    use_case, repo, _, email = _contact()
    email.send.return_value = False
    use_case.execute(**_MESSAGE, honeypot=None)
    repo.add_contact_message.assert_called_once()


def test_contact_honeypot_saves_nothing():
    use_case, repo, _, email = _contact()
    use_case.execute(**_MESSAGE, honeypot="bot")
    repo.add_contact_message.assert_not_called()
    email.send.assert_not_called()


def test_contact_failed_captcha():
    use_case, repo, _, _ = _contact(captcha_ok=False)
    with pytest.raises(CaptchaFailedError):
        use_case.execute(**_MESSAGE, honeypot=None)
    repo.add_contact_message.assert_not_called()


def test_contact_endpoint_validates_and_rate_limits():
    use_case, *_ = _contact()
    app.dependency_overrides[get_submit_contact_message] = lambda: use_case
    client = TestClient(app)
    body = {"name": "A", "email": "a@b.co", "subject": "Hi", "message": "Hello"}
    assert client.post("/api/v1/contact-messages", json={**body, "email": "nope"}).status_code == 422
    codes = [client.post("/api/v1/contact-messages", json=body).status_code for _ in range(11)]
    assert codes[0] == 202 and codes[-1] == 429


# ── comments ─────────────────────────────────────────────────────────────────


def test_comments_nest_replies_and_never_expose_email():
    top, reply = uuid.uuid4(), uuid.uuid4()
    repo = Mock()
    repo.approved_comments.return_value = [
        PublicComment(top, None, "Maya", False, "Hi", _NOW),
        PublicComment(reply, top, "Udit", True, "Thanks", _NOW),
    ]
    items = PublicComments(repo, Mock()).list(uuid.uuid4())
    assert len(items) == 1 and items[0]["replies"][0]["is_author"] is True
    assert "author_email" not in items[0]


def test_comment_reply_must_be_on_the_same_post():
    repo, captcha = Mock(), Mock()
    captcha.verify.return_value = True
    repo.comment_post_id.return_value = uuid.uuid4()
    with pytest.raises(Exception, match="isn't on this post"):
        PublicComments(repo, captcha).add(
            post_id=uuid.uuid4(), comments_open=True, parent_id=uuid.uuid4(), name="A", email=None,
            content="x", token="t", ip=None, honeypot=None,
        )
    repo.add_comment.assert_not_called()


# ── newsletter ───────────────────────────────────────────────────────────────


def _newsletter(existing=None):
    repo, activity, captcha, email = Mock(), Mock(), Mock(), Mock()
    captcha.verify.return_value = True
    repo.subscriber_by_email.return_value = existing
    return Newsletter(repo, activity, captcha, email, "https://lighthouseinfo.com"), repo, activity, email


def test_subscribe_sends_a_confirmation_link_and_is_not_active_yet():
    use_case, repo, activity, email = _newsletter()
    use_case.subscribe(email="r@x.co", token="t", ip=None, honeypot=None)
    repo.save_pending_subscriber.assert_called_once()
    assert "https://lighthouseinfo.com/newsletter/confirm?token=" in email.send.call_args.kwargs["html"]
    activity.record.assert_not_called()


def test_already_active_subscriber_gets_no_email_and_same_response():
    use_case, repo, _, email = _newsletter(Subscriber(uuid.uuid4(), "r@x.co", "active", None))
    use_case.subscribe(email="r@x.co", token="t", ip=None, honeypot=None)
    repo.save_pending_subscriber.assert_not_called()
    email.send.assert_not_called()


def test_expired_or_unknown_confirm_link():
    use_case, repo, _, _ = _newsletter()
    repo.subscriber_by_confirm_token.return_value = None
    with pytest.raises(TokenExpiredError):
        use_case.confirm("token-123")
    repo.subscriber_by_confirm_token.return_value = Subscriber(uuid.uuid4(), "r@x.co", "pending", _NOW)
    with pytest.raises(TokenExpiredError):
        use_case.confirm("token-123")
    repo.activate_subscriber.assert_not_called()


def test_valid_confirm_activates():
    use_case, repo, activity, _ = _newsletter()
    future = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1)
    repo.subscriber_by_confirm_token.return_value = Subscriber(uuid.uuid4(), "r@x.co", "pending", future)
    use_case.confirm("token-123")
    repo.activate_subscriber.assert_called_once()
    assert activity.record.call_args.kwargs["action_type"] == "subscriber_added"


def test_subscribe_endpoint_says_the_same_thing_either_way():
    use_case, *_ = _newsletter(Subscriber(uuid.uuid4(), "r@x.co", "active", None))
    app.dependency_overrides[get_newsletter] = lambda: use_case
    res = TestClient(app).post("/api/v1/newsletter/subscriptions", json={"email": "r@x.co"})
    assert res.status_code == 202 and res.json() == {"status": "check_your_email"}


# ── site builds ──────────────────────────────────────────────────────────────


def test_flush_triggers_due_sites_and_keeps_failures_queued():
    repo, deployer = Mock(), Mock()
    repo.claim_due.return_value = ["portfolio", "lighthouse"]
    deployer.trigger.side_effect = lambda site: site == "portfolio"
    assert SiteBuilds(repo, deployer, clock=lambda: _NOW).flush() == ["portfolio"]
    repo.mark_triggered.assert_called_once_with("portfolio", _NOW)


def test_site_build_status_endpoint():
    repo = Mock()
    repo.list.return_value = [
        SiteBuildState("portfolio", None, None, None),
        SiteBuildState("lighthouse", _NOW, _NOW, None),
    ]
    app.dependency_overrides[get_current_admin] = lambda: _ADMIN
    app.dependency_overrides[get_site_builds] = lambda: SiteBuilds(repo, Mock())
    items = TestClient(app).get("/api/v1/admin/site-builds").json()["items"]
    assert [i["state"] for i in items] == ["up_to_date", "waiting"]


# ── access control ───────────────────────────────────────────────────────────

_ADMIN_ROUTES = [
    ("get", "/inbox/counts"), ("get", "/comments"), ("get", "/contact-messages"), ("get", "/subscribers"),
    ("get", "/site-builds"), ("post", "/site-builds"),
    ("patch", f"/comments/{uuid.uuid4()}"), ("delete", f"/comments/{uuid.uuid4()}"),
    ("post", f"/comments/{uuid.uuid4()}/replies"), ("patch", f"/contact-messages/{uuid.uuid4()}"),
    ("delete", f"/contact-messages/{uuid.uuid4()}"), ("delete", f"/subscribers/{uuid.uuid4()}"),
    ("post", f"/blogs/{uuid.uuid4()}/newsletter-sends"),
]


@pytest.mark.parametrize(("method", "path"), _ADMIN_ROUTES)
def test_admin_routes_need_a_token(method, path):
    assert TestClient(app).request(method, f"/api/v1/admin{path}").status_code == 401


@pytest.mark.parametrize(("method", "path"), _ADMIN_ROUTES)
def test_viewers_are_refused(method, path):
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(role=UserRole.VIEWER)
    assert TestClient(app).request(method, f"/api/v1/admin{path}").status_code == 403


def test_flush_needs_the_cron_secret():
    assert TestClient(app).post("/api/v1/internal/site-builds/flush").status_code in (401, 404)


def test_inbox_counts_and_missing_comment():
    repo = Mock()
    repo.counts.return_value = {"comments_pending": 1, "messages_unread": 2, "subscribers_confirmed": 3}
    repo.set_comment_approved.return_value = None
    app.dependency_overrides[get_current_admin] = lambda: _ADMIN
    app.dependency_overrides[get_inbox_repository] = lambda: repo
    client = TestClient(app)
    assert client.get("/api/v1/admin/inbox/counts").json()["messages_unread"] == 2
    assert client.patch(f"/api/v1/admin/comments/{uuid.uuid4()}", json={"status": "approved"}).status_code == 404
