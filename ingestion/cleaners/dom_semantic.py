"""
Semantic extraction utilities for full-page DOM snapshots.

This module intentionally avoids brittle CSS selectors. It takes an entire
`document.body.outerHTML` payload, removes common UI noise, and extracts a
stable, structured summary for downstream ingestion.
"""

from __future__ import annotations

from html import unescape
import hashlib
import re
from typing import Any, Dict, List


_NOISE_TAG_RE = re.compile(
    r"<(script|style|svg|nav|footer|noscript|button|form|aside|iframe)[^>]*>.*?</\1>",
    re.IGNORECASE | re.DOTALL,
)
_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")

_SKILL_HINTS = [
    "webflow",
    "wordpress",
    "shopify",
    "react",
    "nextjs",
    "node",
    "python",
    "fastapi",
    "django",
    "laravel",
    "ui ux",
    "figma",
    "seo",
    "automation",
    "ai",
    "chatbot",
    "landing page",
    "saas",
]


def _strip_noise_html(raw_html: str) -> str:
    html = raw_html or ""
    html = _COMMENT_RE.sub(" ", html)
    html = _NOISE_TAG_RE.sub(" ", html)
    return html


def _html_to_text(clean_html: str) -> str:
    text = _TAG_RE.sub(" ", clean_html)
    text = unescape(text)
    return _WS_RE.sub(" ", text).strip()


def _classify_page(url: str, text: str) -> str:
    u = (url or "").lower()
    t = (text or "").lower()

    if "/messages/" in u or "messages room" in t:
        return "conversation"
    if "/jobs/" in u or "/freelance-jobs/" in u or "/job-details" in u:
        return "job"
    if "/proposals/" in u or "cover letter" in t:
        return "proposal"
    if "/profile/" in u or "/freelancers/~" in u:
        return "profile"
    if "/contracts/" in u:
        return "contract"
    if "/search/jobs" in u:
        return "job_search"
    return "generic"


def _extract_title(clean_html: str, clean_text: str) -> str:
    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", clean_html, re.IGNORECASE | re.DOTALL)
    if h1:
        title = _WS_RE.sub(" ", _TAG_RE.sub(" ", unescape(h1.group(1)))).strip()
        if title:
            return title[:300]

    # Fallback: first meaningful line from cleaned text
    for part in re.split(r"[|•\n]", clean_text):
        candidate = part.strip()
        if 6 <= len(candidate) <= 300:
            return candidate
    return "Untitled Context"


def _extract_budget(text: str) -> str:
    t = text.lower()
    range_match = re.search(
        r"\$[\d,]+(?:\.\d+)?\s*(?:-|to)\s*\$[\d,]+(?:\.\d+)?(?:\s*/\s*hr)?", t
    )
    if range_match:
        return range_match.group(0)

    single_match = re.search(r"\$[\d,]+(?:\.\d+)?(?:\s*/\s*hr)?", t)
    if single_match:
        return single_match.group(0)
    return ""


def _extract_hire_rate(text: str) -> int | None:
    m = re.search(r"(\d{1,3})\s*%\s*hire rate", text.lower())
    if not m:
        return None
    try:
        val = int(m.group(1))
        return max(0, min(100, val))
    except Exception:
        return None


def _extract_total_spend(text: str) -> str | None:
    m = re.search(
        r"(\$[\d,]+(?:\.\d+)?(?:\s*[km]\+?)?)\s*(?:total\s+spent|spent)",
        text.lower(),
    )
    return m.group(1) if m else None


def _extract_keywords(text: str, limit: int = 12) -> List[str]:
    tl = text.lower()
    found: List[str] = []
    for hint in _SKILL_HINTS:
        if hint in tl:
            found.append(hint)
        if len(found) >= limit:
            break
    return found


def extract_semantic_snapshot(url: str, html: str, page_text: str = "") -> Dict[str, Any]:
    """
    Convert raw DOM snapshot into structured intelligence payload.
    """
    clean_html = _strip_noise_html(html or "")
    clean_text = _html_to_text(clean_html)

    # Fallback when DOM is sparse but page_text exists.
    if page_text and len(clean_text) < 120:
        clean_text = _WS_RE.sub(" ", page_text).strip()

    page_type = _classify_page(url, clean_text)
    title = _extract_title(clean_html, clean_text)
    budget = _extract_budget(clean_text)
    hire_rate = _extract_hire_rate(clean_text)
    total_spend = _extract_total_spend(clean_text)
    keywords = _extract_keywords(clean_text)

    stable_excerpt = re.sub(r"\d{1,2}:\d{2}\s*(?:am|pm)?", " ", clean_text[:400], flags=re.IGNORECASE)
    stable_excerpt = _WS_RE.sub(" ", stable_excerpt).strip().lower()
    fp_seed = f"{url}|{page_type}|{title}|{stable_excerpt}"
    page_fingerprint = hashlib.sha1(fp_seed.encode("utf-8", "ignore")).hexdigest()[:20]

    return {
        "url": url,
        "page_type": page_type,
        "title": title,
        "budget": budget,
        "client_hire_rate": hire_rate,
        "client_total_spend": total_spend,
        "keywords": keywords,
        "clean_text": clean_text[:120000],
        "page_fingerprint": page_fingerprint,
    }


def infer_profile_from_snapshot(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    """
    Best-effort freelancer profile extraction from semantic snapshot text.
    """
    text = snapshot.get("clean_text", "") or ""
    title = snapshot.get("title", "") or ""

    # Very lightweight heuristic extraction (LLM refinement happens downstream).
    hourly_rate = None
    rate_match = re.search(r"\$(\d+(?:\.\d+)?)\s*/\s*hr", text.lower())
    if rate_match:
        try:
            hourly_rate = float(rate_match.group(1))
        except Exception:
            hourly_rate = None

    # "Name" fallback: first 2-3 capitalized words in title-like region.
    name_match = re.search(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})\b", title)
    name = name_match.group(1) if name_match else "Freelancer"

    skills = snapshot.get("keywords", [])[:10]

    return {
        "name": name,
        "title": title[:400],
        "overview": text[:2000],
        "hourly_rate": hourly_rate,
        "skills": skills,
        "niches": skills[:5],
    }
