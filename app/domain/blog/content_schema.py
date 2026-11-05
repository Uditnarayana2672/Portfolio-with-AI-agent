"""Blog content schema (domain layer).

The post body is a TipTap/ProseMirror JSON document. This module is the single
allowlist for it:

  * ``normalize_document`` validates node and mark types (unknown → 422
    INVALID_CONTENT), cleans every attribute through a rule (unknown attributes
    are dropped, unsafe values rejected), enforces size limits, and returns the
    cleaned document plus ``ContentFacts`` the checklist needs.
  * The constants (languages, palette, callout variants, limits) feed the
    editor-config endpoint, so the editor and the server share one list.

Adding a block type later = one ``NodeSpec`` entry here + one render function in
the renderer + one entry in the frontend registry.
"""
from __future__ import annotations

import json
import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from app.domain.blog.embeds import resolve_embed
from app.domain.exceptions import BlogRuleError, ContentTooLargeError

SCHEMA_VERSION = 1

MAX_CONTENT_BYTES = 1_048_576
MAX_NODES = 5_000
MAX_DEPTH = 8
MAX_TEXT_CHARS = 20_000
MAX_TABLES = 30
MAX_GALLERIES = 20
MAX_MEDIA_EMBEDS = 20
TABLE_MAX_ROWS = 200
TABLE_MAX_COLS = 20
GALLERY_MAX_ITEMS = 20

CODE_LANGUAGES: tuple[tuple[str, str], ...] = (
    ("python", "Python"), ("typescript", "TypeScript"), ("javascript", "JavaScript"),
    ("tsx", "TSX"), ("bash", "Bash"), ("sql", "SQL"), ("json", "JSON"), ("yaml", "YAML"),
    ("html", "HTML"), ("css", "CSS"), ("go", "Go"), ("rust", "Rust"), ("java", "Java"),
    ("dockerfile", "Dockerfile"), ("diff", "Diff"), ("plaintext", "Plain text"),
)
CODE_LANGUAGE_IDS = frozenset(lang for lang, _ in CODE_LANGUAGES)

# Colours are stored as token names so posts follow theme changes.
PALETTE: tuple[tuple[str, str, str, str], ...] = (
    # token, label, background, foreground
    ("ink", "Ink", "#21201c", "#f5f1e8"),
    ("paper", "Paper", "#f5f1e8", "#21201c"),
    ("paper-dark", "Paper dark", "#ebe4d3", "#21201c"),
    ("highlight", "Highlight", "#f4e07a", "#21201c"),
    ("accent", "Accent", "#c1432a", "#ffffff"),
    ("accent-soft", "Accent soft", "#f3dcd5", "#21201c"),
    ("ok-soft", "Green soft", "#dcebd3", "#21201c"),
    ("warn-soft", "Amber soft", "#fcebc8", "#21201c"),
    ("info-soft", "Blue soft", "#d6e1ef", "#21201c"),
)
PALETTE_TOKENS = frozenset(token for token, *_ in PALETTE)

CALLOUT_VARIANTS: tuple[tuple[str, str, str], ...] = (
    # variant, label, default icon
    ("note", "Note (yellow)", "✏︎"),
    ("info", "Info", "ℹ"),
    ("tip", "Tip", "★"),
    ("warning", "Warning", "!"),
    ("danger", "Danger", "⚠"),
)
CALLOUT_VARIANT_IDS = frozenset(v for v, *_ in CALLOUT_VARIANTS)

_YOUTUBE_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_MEDIA_HOSTS = ("res.cloudinary.com",)

# ── attribute rules ──────────────────────────────────────────────────────────
# A rule takes (raw value, json path) and returns the cleaned value, or raises.

Rule = Callable[[Any, str], Any]


def _invalid(path: str, reason: str) -> BlogRuleError:
    return BlogRuleError("INVALID_CONTENT", f"Invalid content at {path}: {reason}",
                         {"path": path, "reason": reason})


def _enum(values, default=None) -> Rule:
    def rule(v, path):
        return v if v in values else default
    return rule


def _int(lo: int, hi: int, default: int | None = None) -> Rule:
    def rule(v, path):
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            return default
        return max(lo, min(hi, int(v)))
    return rule


def _bool(default: bool = False) -> Rule:
    def rule(v, path):
        return v if isinstance(v, bool) else default
    return rule


def _str(max_len: int) -> Rule:
    def rule(v, path):
        if v is None:
            return None
        if not isinstance(v, str):
            raise _invalid(path, "expected text")
        v = v.strip()
        if len(v) > max_len:
            raise BlogRuleError("CONTENT_LIMIT_EXCEEDED", f"Text at {path} is over {max_len} characters.",
                                {"path": path, "limit": max_len})
        return v or None
    return rule


def _uuid(required: bool) -> Rule:
    def rule(v, path):
        if v in (None, ""):
            if required:
                raise _invalid(path, "missing asset id")
            return None
        try:
            return str(uuid.UUID(str(v)))
        except ValueError as exc:
            raise _invalid(path, "bad asset id") from exc
    return rule


def _https(required: bool = False, media_only: bool = False) -> Rule:
    def rule(v, path):
        if v in (None, ""):
            if required:
                raise _invalid(path, "missing URL")
            return None
        parsed = urlparse(str(v))
        if parsed.scheme != "https" or not parsed.netloc:
            raise _invalid(path, "URL must be https")
        if media_only and parsed.netloc.lower() not in _MEDIA_HOSTS:
            raise _invalid(path, "media must come from the Cloudinary library")
        return str(v)
    return rule


def is_safe_href(href: str) -> bool:
    """https/http/mailto, a site-relative path, or an in-page #anchor."""
    if href.startswith("#"):
        return re.fullmatch(r"#[A-Za-z0-9_-]+", href) is not None
    if href.startswith("/"):
        return not href.startswith("//")
    return urlparse(href).scheme in ("https", "http", "mailto")


def _href(v, path):
    if not isinstance(v, str) or not v.strip():
        raise BlogRuleError("INVALID_LINK", f"Link at {path} has no address.", {"path": path})
    v = v.strip()
    if not is_safe_href(v):
        raise BlogRuleError("INVALID_LINK", f"Link at {path} uses a blocked scheme.", {"path": path})
    return v


def _optional_href(v, path):
    return None if v in (None, "") else _href(v, path)


def _token(v, path):
    return v if v in PALETTE_TOKENS else None


def _col_widths(v, path):
    if not isinstance(v, list):
        return None
    return [int(x) if isinstance(x, (int, float)) and 20 <= x <= 2000 else None for x in v][:TABLE_MAX_COLS]


def _internal_ref(v, path):
    if not isinstance(v, dict) or v.get("type") not in ("blog", "project"):
        return None
    try:
        return {"type": v["type"], "id": str(uuid.UUID(str(v.get("id"))))}
    except ValueError:
        return None


_GALLERY_ITEM_RULES: dict[str, Rule] = {
    "asset_id": _uuid(True),
    "public_id": _str(300),
    "src": _https(required=True, media_only=True),
    "alt": _str(250),
    "caption": _str(300),
    "width": _int(1, 20000),
    "height": _int(1, 20000),
}


def _gallery_items(v, path):
    if not isinstance(v, list) or not v:
        raise _invalid(path, "a gallery needs images")
    if len(v) > GALLERY_MAX_ITEMS:
        raise BlogRuleError("CONTENT_LIMIT_EXCEEDED", f"A gallery holds at most {GALLERY_MAX_ITEMS} images.",
                            {"path": path, "limit": GALLERY_MAX_ITEMS})
    items = []
    for i, raw in enumerate(v):
        if not isinstance(raw, dict):
            raise _invalid(f"{path}[{i}]", "expected an image")
        items.append({k: rule(raw.get(k), f"{path}[{i}].{k}") for k, rule in _GALLERY_ITEM_RULES.items()})
    return items


# ── node specs ───────────────────────────────────────────────────────────────

INLINE = frozenset({"text", "hardBreak"})
BLOCKS = frozenset({
    "paragraph", "heading", "bulletList", "orderedList", "blockquote", "callout",
    "codeBlock", "table", "image", "imageGallery", "video", "embed", "horizontalRule",
})
_LIST_ITEM_CHILDREN = frozenset({
    "paragraph", "bulletList", "orderedList", "codeBlock", "image", "callout", "blockquote",
})
_RICH_CHILDREN = frozenset({"paragraph", "bulletList", "orderedList"})


@dataclass(frozen=True)
class NodeSpec:
    attrs: dict[str, Rule] = field(default_factory=dict)
    children: frozenset[str] | None = None   # None → leaf node


NODE_SPECS: dict[str, NodeSpec] = {
    "doc": NodeSpec(children=BLOCKS),
    "paragraph": NodeSpec(children=INLINE),
    "heading": NodeSpec({"level": _int(2, 4, 2), "numbered": _bool(False)}, INLINE),
    "bulletList": NodeSpec(children=frozenset({"listItem"})),
    "orderedList": NodeSpec({"start": _int(1, 10_000, 1)}, frozenset({"listItem"})),
    "listItem": NodeSpec(children=_LIST_ITEM_CHILDREN),
    "blockquote": NodeSpec(
        {"attribution": _str(120), "cite_url": _https(), "variant": _enum({"default", "pull"}, "default")},
        _RICH_CHILDREN,
    ),
    "callout": NodeSpec(
        {"variant": _enum(CALLOUT_VARIANT_IDS, "note"), "icon": _str(8), "title": _str(120)},
        _RICH_CHILDREN | {"codeBlock"},
    ),
    "codeBlock": NodeSpec(
        {
            "language": _enum(CODE_LANGUAGE_IDS, "plaintext"),
            "filename": _str(80),
            "show_line_numbers": _bool(False),
        },
        frozenset({"text"}),
    ),
    "table": NodeSpec(
        {
            "header_style": lambda v, p: v if v in PALETTE_TOKENS else "ink",
            "striped": _bool(False),
            "border": _enum({"grid", "rows", "none"}, "grid"),
        },
        frozenset({"tableRow"}),
    ),
    "tableRow": NodeSpec(children=frozenset({"tableCell", "tableHeader"})),
    "tableCell": NodeSpec(
        {"colspan": _int(1, TABLE_MAX_COLS, 1), "rowspan": _int(1, TABLE_MAX_ROWS, 1),
         "colwidth": _col_widths, "background": _token,
         "align": _enum({"left", "center", "right"})},
        _RICH_CHILDREN,
    ),
    "image": NodeSpec({
        "asset_id": _uuid(True),
        "public_id": _str(300),
        "src": _https(required=True, media_only=True),
        "alt": _str(250),
        "caption": _str(300),
        "width": _int(1, 20000),
        "height": _int(1, 20000),
        # small/medium added for the Blog Manager build; "normal" stays the
        # default so existing posts render unchanged (the editor inserts medium).
        "size": _enum({"small", "medium", "normal", "wide", "full"}, "normal"),
        "link_href": _optional_href,
    }),
    "imageGallery": NodeSpec({
        "items": _gallery_items,
        "height": _enum({"sm", "md", "lg"}, "md"),
        "caption": _str(300),
    }),
    "video": NodeSpec({
        "source": _enum({"cloudinary", "youtube"}),
        "asset_id": _uuid(True),
        # Checked per source in _count_and_check (YouTube's is derived server-side).
        "src": lambda v, p: v if isinstance(v, str) else None,
        "external_id": _str(20),
        "poster_url": _https(),
        "title": _str(200),
        "duration_seconds": _int(0, 86_400),
        "caption": _str(300),
        "start_seconds": _int(0, 86_400),
        "size": _enum({"small", "medium", "normal"}, "normal"),
    }),
    "embed": NodeSpec({
        "provider": _str(30),
        "original_url": _https(required=True),
        "embed_url": _https(),
        "title": _str(200),
        "height": _int(200, 900, 420),
    }),
    "horizontalRule": NodeSpec(),
}
NODE_SPECS["tableHeader"] = NODE_SPECS["tableCell"]

MARK_SPECS: dict[str, dict[str, Rule]] = {
    "bold": {},
    "italic": {},
    "underline": {},
    "strike": {},
    "code": {},
    "highlight": {"color": lambda v, p: v if v in PALETTE_TOKENS else "highlight"},
    "link": {"href": _href, "target": _enum({"_blank"}), "internal": _internal_ref},
}


# ── normalization ────────────────────────────────────────────────────────────


@dataclass
class ContentFacts:
    """What the checklist and media lookups need to know about a document."""

    asset_ids: set[str] = field(default_factory=set)
    images_missing_alt: list[str] = field(default_factory=list)
    empty_blocks: list[str] = field(default_factory=list)
    heading_order_ok: bool = True
    internal_links: list[dict] = field(default_factory=list)


@dataclass
class _Counters:
    nodes: int = 0
    tables: int = 0
    galleries: int = 0
    media_embeds: int = 0


def empty_document() -> dict:
    return {"type": "doc", "schema_version": SCHEMA_VERSION, "content": []}


def normalize_document(doc: Any) -> tuple[dict, ContentFacts]:
    """Validate + clean a TipTap document. Raises ``BlogRuleError`` /
    ``ContentTooLargeError``; returns (clean doc, facts)."""
    if doc is None:
        doc = empty_document()
    if not isinstance(doc, dict) or doc.get("type") != "doc":
        raise _invalid("content", "the body must be a document")
    if len(json.dumps(doc, ensure_ascii=False).encode("utf-8")) > MAX_CONTENT_BYTES:
        raise ContentTooLargeError(MAX_CONTENT_BYTES)

    facts = ContentFacts()
    counters = _Counters()
    clean = _clean_node(doc, "content", 0, counters, facts)
    clean["schema_version"] = SCHEMA_VERSION
    _check_heading_order(clean, facts)
    facts.internal_links = [
        mark["attrs"]["internal"]
        for marks in iter_text_marks(clean)
        for mark in marks
        if mark["type"] == "link" and mark["attrs"].get("internal")
    ]
    return clean, facts


def _clean_node(node: Any, path: str, depth: int, counters: _Counters, facts: ContentFacts) -> dict:
    if not isinstance(node, dict) or not isinstance(node.get("type"), str):
        raise _invalid(path, "expected a node")
    ntype = node["type"]
    counters.nodes += 1
    if counters.nodes > MAX_NODES:
        raise BlogRuleError("CONTENT_LIMIT_EXCEEDED", f"A post can hold at most {MAX_NODES} blocks.",
                            {"limit": MAX_NODES})
    if depth > MAX_DEPTH:
        raise BlogRuleError("CONTENT_LIMIT_EXCEEDED", "Lists and blocks are nested too deeply.",
                            {"path": path, "limit": MAX_DEPTH})

    if ntype == "text":
        return _clean_text(node, path)
    if ntype == "hardBreak":
        return {"type": "hardBreak"}

    spec = NODE_SPECS.get(ntype)
    if spec is None:
        raise BlogRuleError("INVALID_CONTENT", f"Unknown block type '{ntype}'.",
                            {"path": path, "reason": f"unknown node '{ntype}'"})

    out: dict[str, Any] = {"type": ntype}
    raw_attrs = node.get("attrs") or {}
    if not isinstance(raw_attrs, dict):
        raw_attrs = {}
    if spec.attrs:
        out["attrs"] = {k: rule(raw_attrs.get(k), f"{path}.attrs.{k}") for k, rule in spec.attrs.items()}

    _count_and_check(ntype, out, path, counters)

    children = node.get("content") or []
    if children and spec.children is None:
        raise _invalid(path, f"'{ntype}' cannot contain other blocks")
    if children:
        cleaned = []
        for i, child in enumerate(children):
            child_path = f"{path}[{i}]" if ntype == "doc" else f"{path}.content[{i}]"
            ctype = child.get("type") if isinstance(child, dict) else None
            if ctype not in spec.children:
                raise BlogRuleError(
                    "INVALID_CONTENT",
                    f"'{ctype}' is not allowed inside '{ntype}'.",
                    {"path": child_path, "reason": f"'{ctype}' not allowed in '{ntype}'"},
                )
            cleaned.append(_clean_node(child, child_path, depth + 1, counters, facts))
        if ntype == "codeBlock":
            # Code is plain text: strip any marks a paste may have carried.
            cleaned = [{"type": "text", "text": c["text"]} for c in cleaned if c["type"] == "text"]
        out["content"] = cleaned

    _collect_facts(ntype, out, path, facts)
    return out


def _clean_text(node: dict, path: str) -> dict:
    text = node.get("text")
    if not isinstance(text, str) or text == "":
        raise _invalid(path, "empty text node")
    if len(text) > MAX_TEXT_CHARS:
        raise BlogRuleError("CONTENT_LIMIT_EXCEEDED", f"Text at {path} is over {MAX_TEXT_CHARS} characters.",
                            {"path": path, "limit": MAX_TEXT_CHARS})
    out: dict[str, Any] = {"type": "text", "text": text}
    marks = []
    for j, mark in enumerate(node.get("marks") or []):
        mtype = mark.get("type") if isinstance(mark, dict) else None
        rules = MARK_SPECS.get(mtype)
        if rules is None:
            raise BlogRuleError("INVALID_CONTENT", f"Unknown formatting '{mtype}'.",
                                {"path": f"{path}.marks[{j}]", "reason": f"unknown mark '{mtype}'"})
        attrs = mark.get("attrs") or {}
        clean_mark: dict[str, Any] = {"type": mtype}
        if rules:
            clean_mark["attrs"] = {k: r(attrs.get(k), f"{path}.marks[{j}].{k}") for k, r in rules.items()}
        marks.append(clean_mark)
    if marks:
        out["marks"] = marks
    return out


def _count_and_check(ntype: str, out: dict, path: str, counters: _Counters) -> None:
    attrs = out.get("attrs", {})
    if ntype == "table":
        counters.tables += 1
        if counters.tables > MAX_TABLES:
            raise BlogRuleError("CONTENT_LIMIT_EXCEEDED", f"At most {MAX_TABLES} tables per post.",
                                {"limit": MAX_TABLES})
    elif ntype == "imageGallery":
        counters.galleries += 1
        if counters.galleries > MAX_GALLERIES:
            raise BlogRuleError("CONTENT_LIMIT_EXCEEDED", f"At most {MAX_GALLERIES} galleries per post.",
                                {"limit": MAX_GALLERIES})
    elif ntype in ("video", "embed"):
        counters.media_embeds += 1
        if counters.media_embeds > MAX_MEDIA_EMBEDS:
            raise BlogRuleError("CONTENT_LIMIT_EXCEEDED", f"At most {MAX_MEDIA_EMBEDS} videos and embeds per post.",
                                {"limit": MAX_MEDIA_EMBEDS})

    if ntype == "video":
        if attrs.get("source") == "youtube":
            vid = attrs.get("external_id") or ""
            if not _YOUTUBE_ID.match(vid):
                raise _invalid(path, "bad YouTube video id")
            # Never trust a client iframe src — derive it.
            attrs["src"] = f"https://www.youtube-nocookie.com/embed/{vid}"
        elif attrs.get("source") == "cloudinary":
            _https(required=True, media_only=True)(attrs.get("src"), f"{path}.attrs.src")
        else:
            raise _invalid(path, "video source must be cloudinary or youtube")
    elif ntype == "embed":
        resolved = resolve_embed(attrs["original_url"])
        attrs["provider"] = resolved.provider
        attrs["embed_url"] = resolved.embed_url


def _node_text(node: dict) -> str:
    if node.get("type") == "text":
        return node.get("text", "")
    return "".join(_node_text(c) for c in node.get("content", []))


def _collect_facts(ntype: str, out: dict, path: str, facts: ContentFacts) -> None:
    attrs = out.get("attrs", {})
    if ntype == "image":
        facts.asset_ids.add(attrs["asset_id"])
        if not attrs.get("alt") or len(attrs["alt"]) < 3:
            facts.images_missing_alt.append(path)
    elif ntype == "imageGallery":
        for i, item in enumerate(attrs["items"]):
            facts.asset_ids.add(item["asset_id"])
            if not item.get("alt") or len(item["alt"]) < 3:
                facts.images_missing_alt.append(f"{path}.attrs.items[{i}]")
    elif ntype == "video":
        facts.asset_ids.add(attrs["asset_id"])
    elif ntype in ("heading", "codeBlock") and not _node_text(out).strip():
        facts.empty_blocks.append(path)
    elif ntype == "table" and not _node_text(out).strip():
        facts.empty_blocks.append(path)


def _check_heading_order(doc: dict, facts: ContentFacts) -> None:
    for node in doc.get("content", []):
        if node["type"] == "heading":
            facts.heading_order_ok = node["attrs"]["level"] == 2
            return


def iter_text_marks(doc: dict):
    """Yield every text node's marks (used to collect internal link refs)."""
    stack = [doc]
    while stack:
        node = stack.pop()
        if node.get("type") == "text":
            yield node.get("marks", [])
        stack.extend(node.get("content", []))
