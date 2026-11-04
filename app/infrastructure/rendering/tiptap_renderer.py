"""TipTap JSON → HTML renderer (infrastructure layer).

Implements the ``BlogContentRenderer`` port. Input is a document that already
passed ``normalize_document`` (allowlisted nodes, cleaned attributes), and every
piece of text and every attribute is HTML-escaped here, so the output is safe
to serve as-is. Class names are prefixed ``bp-`` (blog post) and styled by the
public article stylesheet.

Interactive bits (gallery arrows, YouTube click-to-load, code copy) are plain
markup with data attributes; a small script on the page wires them up.
"""
from __future__ import annotations

import re
from html import escape

from app.application.interfaces.blog_content_renderer import (
    BlogContentRenderer,
    LinkResolver,
    RenderedContent,
    TocEntry,
)
from app.domain.blog.content_schema import CALLOUT_VARIANTS, CODE_LANGUAGES
from app.domain.blog.slug import slugify

_LANG_LABELS = dict(CODE_LANGUAGES)
_CALLOUT_ICONS = {v: icon for v, _label, icon in CALLOUT_VARIANTS}
_IMAGE_WIDTHS = (640, 960, 1280, 1920)
_IMAGE_SIZES = "(max-width: 760px) 100vw, 760px"
# Display caps in px for each media size; None = the size's layout width
# (column, wide or full bleed). Never larger than the file itself.
_MEDIA_MAX_PX = {"small": 360, "medium": 560, "normal": 760}
_IMAGE_SIZE_HINTS = {
    "small": "(max-width: 400px) 100vw, 360px",
    "medium": "(max-width: 600px) 100vw, 560px",
    "wide": "(max-width: 880px) 100vw, 880px",
    "full": "100vw",
}
_ZOOM_TRANSFORM = "f_auto,q_auto,w_2000,c_limit"
_GALLERY_HEIGHTS = {"sm": 240, "md": 360, "lg": 480}
_WORD = re.compile(r"[\w'’-]+", re.UNICODE)


def _a(value) -> str:
    """Escape an attribute value."""
    return escape(str(value), quote=True)


def _cld(url: str, transform: str) -> str:
    marker = "/upload/"
    if "res.cloudinary.com" not in url or marker not in url:
        return url
    head, tail = url.split(marker, 1)
    return f"{head}{marker}{transform}/{tail}"


class _RenderState:
    def __init__(self, link_resolver: LinkResolver | None) -> None:
        self.link_resolver = link_resolver
        self.text_parts: list[str] = []
        self.toc: list[TocEntry] = []
        self.used_ids: set[str] = set()
        self.counters: dict[int, int] = {}
        self.image_count = 0

    def unique_id(self, text: str) -> str:
        base = slugify(text) or "section"
        candidate, n = base, 2
        while candidate in self.used_ids:
            candidate = f"{base}-{n}"
            n += 1
        self.used_ids.add(candidate)
        return candidate


class TipTapHtmlRenderer(BlogContentRenderer):
    def render(self, doc: dict, *, link_resolver: LinkResolver | None = None) -> RenderedContent:
        st = _RenderState(link_resolver)
        blocks = doc.get("content", [])
        html = "".join(self._block(node, st) for node in blocks)
        text = "\n".join(p for p in st.text_parts if p)
        block_count = sum(
            1 for n in blocks if not (n["type"] == "paragraph" and not n.get("content"))
        )
        return RenderedContent(
            html=html,
            text=text,
            toc=st.toc,
            word_count=len(_WORD.findall(text)),
            block_count=block_count,
            image_count=st.image_count,
        )

    # ── blocks ────────────────────────────────────────────────────────────

    def _children(self, node: dict, st: _RenderState) -> str:
        return "".join(self._block(c, st) for c in node.get("content", []))

    def _block(self, node: dict, st: _RenderState) -> str:
        t = node["type"]
        attrs = node.get("attrs", {})
        method = getattr(self, f"_n_{t}", None)
        if method is None:  # normalize_document makes this unreachable
            return ""
        return method(node, attrs, st)

    def _n_paragraph(self, node, attrs, st):
        st.text_parts.append(self._plain(node))
        return f"<p>{self._inline(node, st)}</p>"

    def _n_heading(self, node, attrs, st):
        level = attrs.get("level", 2)
        text = self._plain(node)
        st.text_parts.append(text)
        for deeper in [lvl for lvl in st.counters if lvl > level]:
            del st.counters[deeper]
        number = None
        if attrs.get("numbered"):
            st.counters[level] = st.counters.get(level, 0) + 1
            number = str(st.counters[level])
        hid = st.unique_id(text)
        st.toc.append(TocEntry(id=hid, text=text, level=level, number=number))
        num_html = f'<span class="bp-h__num">{number}.</span> ' if number else ""
        cls = "bp-h bp-h--numbered" if number else "bp-h"
        return f'<h{level} id="{_a(hid)}" class="{cls}">{num_html}{self._inline(node, st)}</h{level}>'

    def _n_bulletList(self, node, attrs, st):
        return f'<ul class="bp-list">{self._children(node, st)}</ul>'

    def _n_orderedList(self, node, attrs, st):
        start = attrs.get("start", 1)
        start_attr = f' start="{int(start)}"' if start != 1 else ""
        return f'<ol class="bp-list"{start_attr}>{self._children(node, st)}</ol>'

    def _n_listItem(self, node, attrs, st):
        return f"<li>{self._children(node, st)}</li>"

    def _n_blockquote(self, node, attrs, st):
        variant = " bp-quote--pull" if attrs.get("variant") == "pull" else ""
        cite = f' cite="{_a(attrs["cite_url"])}"' if attrs.get("cite_url") else ""
        caption = ""
        if attrs.get("attribution"):
            who = escape(attrs["attribution"])
            if attrs.get("cite_url"):
                who = f'<a href="{_a(attrs["cite_url"])}" rel="noopener noreferrer" target="_blank">{who}</a>'
            caption = f"<figcaption>— {who}</figcaption>"
            st.text_parts.append(attrs["attribution"])
        return (f'<figure class="bp-quote{variant}"><blockquote{cite}>{self._children(node, st)}'
                f"</blockquote>{caption}</figure>")

    def _n_callout(self, node, attrs, st):
        variant = attrs.get("variant", "note")
        icon = attrs.get("icon") or _CALLOUT_ICONS.get(variant, "")
        title = ""
        if attrs.get("title"):
            st.text_parts.append(attrs["title"])
            title = f'<p class="bp-callout__title">{escape(attrs["title"])}</p>'
        return (
            f'<aside class="bp-callout bp-callout--{_a(variant)}" role="note">'
            f'<span class="bp-callout__icon" aria-hidden="true">{escape(icon)}</span>'
            f'<div class="bp-callout__body">{title}{self._children(node, st)}</div></aside>'
        )

    def _n_codeBlock(self, node, attrs, st):
        lang = attrs.get("language") or "plaintext"
        code = "".join(c.get("text", "") for c in node.get("content", []))
        st.text_parts.append(code)
        label = _LANG_LABELS.get(lang, lang)
        name = f'<span class="bp-code__file">{escape(attrs["filename"])}</span> · ' if attrs.get("filename") else ""
        lines = " bp-code--lines" if attrs.get("show_line_numbers") else ""
        return (
            f'<figure class="bp-code{lines}" data-lang="{_a(lang)}">'
            f'<figcaption class="bp-code__bar">{name}<span class="bp-code__lang">{escape(label)}</span>'
            f'<button type="button" class="bp-code__copy" data-copy>Copy</button></figcaption>'
            f'<pre><code class="language-{_a(lang)}">{escape(code)}</code></pre></figure>'
        )

    def _n_horizontalRule(self, node, attrs, st):
        return '<hr class="bp-hr">'

    def _n_table(self, node, attrs, st):
        classes = [
            "bp-table",
            f"bp-table--{attrs.get('border', 'grid')}",
            f"bp-table--head-{attrs.get('header_style', 'ink')}",
        ]
        if attrs.get("striped"):
            classes.append("bp-table--striped")
        rows = node.get("content", [])
        colgroup = ""
        if rows:
            widths: list = []
            for cell in rows[0].get("content", []):
                cw = cell.get("attrs", {}).get("colwidth") or []
                span = cell.get("attrs", {}).get("colspan", 1)
                widths.extend((cw + [None] * span)[:span])
            if any(widths):
                colgroup = "<colgroup>" + "".join(
                    f'<col style="width:{int(w)}px">' if w else "<col>" for w in widths
                ) + "</colgroup>"
        body = "".join(self._row(r, st) for r in rows)
        return f'<div class="bp-table-wrap"><table class="{" ".join(classes)}">{colgroup}<tbody>{body}</tbody></table></div>'

    def _row(self, row, st):
        cells = []
        for cell in row.get("content", []):
            a = cell.get("attrs", {})
            tag = "th" if cell["type"] == "tableHeader" else "td"
            extra = ""
            if a.get("colspan", 1) > 1:
                extra += f' colspan="{int(a["colspan"])}"'
            if a.get("rowspan", 1) > 1:
                extra += f' rowspan="{int(a["rowspan"])}"'
            cls = []
            if a.get("background"):
                cls.append(f"bp-bg--{a['background']}")
            if a.get("align"):
                cls.append(f"bp-align--{a['align']}")
            if cls:
                extra += f' class="{" ".join(cls)}"'
            if tag == "th":
                extra += ' scope="col"'
            cells.append(f"<{tag}{extra}>{self._children(cell, st)}</{tag}>")
        return f"<tr>{''.join(cells)}</tr>"

    def _img(self, src: str, alt: str, width, height, *, sizes: str = _IMAGE_SIZES, cls: str = "",
             extra: str = "") -> str:
        srcset = ", ".join(f"{_a(_cld(src, f'f_auto,q_auto,w_{w}'))} {w}w" for w in _IMAGE_WIDTHS)
        dims = f' width="{int(width)}" height="{int(height)}"' if width and height else ""
        cls_attr = f' class="{cls}"' if cls else ""
        return (f'<img{cls_attr} src="{_a(_cld(src, "f_auto,q_auto,w_1280"))}" srcset="{srcset}" '
                f'sizes="{_a(sizes)}" alt="{_a(alt or "")}"{dims}{extra} loading="lazy" decoding="async">')

    @staticmethod
    def _max_width_style(size: str, natural_width) -> str:
        """Inline max-width for a figure: the size's cap, but never wider than
        the file (a 300 px screenshot is never stretched)."""
        caps = [c for c in (_MEDIA_MAX_PX.get(size), natural_width if size in _MEDIA_MAX_PX else None) if c]
        return f' style="max-width:{int(min(caps))}px"' if caps else ""

    def _n_image(self, node, attrs, st):
        st.image_count += 1
        size = attrs.get("size", "normal")
        img = self._img(
            attrs["src"], attrs.get("alt") or "", attrs.get("width"), attrs.get("height"),
            sizes=_IMAGE_SIZE_HINTS.get(size, _IMAGE_SIZES),
            extra=f' data-zoom-src="{_a(_cld(attrs["src"], _ZOOM_TRANSFORM))}"',
        )
        if attrs.get("link_href"):
            img = f'<a href="{_a(attrs["link_href"])}">{img}</a>'
        caption = ""
        if attrs.get("caption"):
            st.text_parts.append(attrs["caption"])
            caption = f"<figcaption>{escape(attrs['caption'])}</figcaption>"
        style = self._max_width_style(size, attrs.get("width"))
        return (f'<figure class="bp-image bp-image--{_a(size)}"{style}>'
                f'<div class="bp-image__frame">{img}</div>{caption}</figure>')

    def _n_imageGallery(self, node, attrs, st):
        height = _GALLERY_HEIGHTS.get(attrs.get("height", "md"), 360)
        items = []
        for item in attrs.get("items", []):
            st.image_count += 1
            w, h = item.get("width"), item.get("height")
            display_w = int(height * w / h) if w and h else height
            src = _cld(item["src"], f"f_auto,q_auto,h_{height * 2},c_limit")
            cap = f"<figcaption>{escape(item['caption'])}</figcaption>" if item.get("caption") else ""
            items.append(
                f'<figure class="bp-gallery__item"><img src="{_a(src)}" alt="{_a(item.get("alt") or "")}" '
                f'width="{display_w}" height="{height}" loading="lazy" decoding="async" '
                f'data-full="{_a(_cld(item["src"], "f_auto,q_auto,w_2000,c_limit"))}">{cap}</figure>'
            )
        caption = ""
        if attrs.get("caption"):
            st.text_parts.append(attrs["caption"])
            caption = f'<figcaption class="bp-gallery__caption">{escape(attrs["caption"])}</figcaption>'
        return (
            f'<figure class="bp-gallery bp-gallery--{_a(attrs.get("height", "md"))}" data-gallery>'
            f'<div class="bp-gallery__track" tabindex="0" role="region" aria-label="Image gallery">{"".join(items)}</div>'
            '<button type="button" class="bp-gallery__nav bp-gallery__nav--prev" data-gallery-prev aria-label="Previous image">‹</button>'
            '<button type="button" class="bp-gallery__nav bp-gallery__nav--next" data-gallery-next aria-label="Next image">›</button>'
            f"{caption}</figure>"
        )

    def _n_video(self, node, attrs, st):
        caption = ""
        if attrs.get("caption"):
            st.text_parts.append(attrs["caption"])
            caption = f"<figcaption>{escape(attrs['caption'])}</figcaption>"
        title = attrs.get("title") or "Video"
        size = attrs.get("size", "normal")
        cls = f"bp-video bp-video--{_a(size)}"
        style = self._max_width_style(size, None)
        if attrs.get("source") == "youtube":
            vid = attrs["external_id"]
            start = attrs.get("start_seconds") or 0
            embed = f"{attrs['src']}?autoplay=1&rel=0" + (f"&start={int(start)}" if start else "")
            watch = f"https://www.youtube.com/watch?v={vid}" + (f"&t={int(start)}s" if start else "")
            poster = attrs.get("poster_url") or f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"
            return (
                f'<figure class="{cls} bp-video--youtube"{style}>'
                f'<div class="bp-video__frame" data-youtube="{_a(embed)}" data-title="{_a(title)}">'
                f'<button type="button" class="bp-video__play" aria-label="Play video: {_a(title)}">'
                f'<img src="{_a(poster)}" alt="" loading="lazy"><span class="bp-video__icon" aria-hidden="true">▶</span>'
                f"</button></div>"
                f'<p class="bp-video__out"><a href="{_a(watch)}" target="_blank" rel="noopener noreferrer">'
                f"Watch on YouTube ↗</a></p>{caption}</figure>"
            )
        poster = f' poster="{_a(attrs["poster_url"])}"' if attrs.get("poster_url") else ""
        return (
            f'<figure class="{cls}"{style}><video controls preload="metadata" playsinline{poster} '
            f'src="{_a(attrs["src"])}" title="{_a(title)}"></video>{caption}</figure>'
        )

    def _n_embed(self, node, attrs, st):
        return (
            f'<figure class="bp-embed bp-embed--{_a(attrs.get("provider", ""))}">'
            f'<iframe src="{_a(attrs["embed_url"])}" height="{int(attrs.get("height", 420))}" '
            f'title="{_a(attrs.get("title") or attrs.get("provider", "Embed"))}" loading="lazy" '
            'sandbox="allow-scripts allow-same-origin allow-popups allow-forms" '
            'referrerpolicy="strict-origin-when-cross-origin" allowfullscreen></iframe></figure>'
        )

    # ── inline ────────────────────────────────────────────────────────────

    @staticmethod
    def _plain(node: dict) -> str:
        parts = []
        for c in node.get("content", []):
            if c["type"] == "text":
                parts.append(c["text"])
            elif c["type"] == "hardBreak":
                parts.append(" ")
        return "".join(parts)

    def _inline(self, node: dict, st: _RenderState) -> str:
        out = []
        for c in node.get("content", []):
            if c["type"] == "hardBreak":
                out.append("<br>")
                continue
            html = escape(c["text"])
            marks = c.get("marks", [])
            # Link wraps everything else so one anchor covers the formatted run.
            for mark in sorted(marks, key=lambda m: m["type"] == "link"):
                html = self._mark(mark, html, st)
            out.append(html)
        return "".join(out)

    def _mark(self, mark: dict, html: str, st: _RenderState) -> str:
        t = mark["type"]
        if t == "bold":
            return f"<strong>{html}</strong>"
        if t == "italic":
            return f"<em>{html}</em>"
        if t == "underline":
            return f"<u>{html}</u>"
        if t == "strike":
            return f"<s>{html}</s>"
        if t == "code":
            return f'<code class="bp-inline-code">{html}</code>'
        if t == "highlight":
            return f'<mark class="bp-hl bp-hl--{_a(mark["attrs"].get("color", "highlight"))}">{html}</mark>'
        if t == "link":
            attrs = mark["attrs"]
            href = attrs["href"]
            if attrs.get("internal") and st.link_resolver:
                href = st.link_resolver(attrs["internal"]) or href
            extra = ""
            if href.startswith(("http://", "https://")):
                extra = ' rel="noopener noreferrer"'
            if attrs.get("target") == "_blank":
                extra += ' target="_blank"'
            return f'<a href="{_a(href)}"{extra}>{html}</a>'
        return html
