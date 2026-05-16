"""
CookieJar Bot — Site Crawler
Ingests an entire website into the knowledge base, one entry per page/section.

Supports two crawl strategies:
  - "spa"    : Uses Playwright (headless Chromium) to render JavaScript SPAs.
               Auto-discovers sections from the sidebar/nav and clicks through each.
  - "static" : Uses requests + BeautifulSoup to crawl static/server-rendered sites.
               Follows internal links up to a configurable depth and page limit.

The crawler is called by the /cj crawl admin command.
"""

import logging
import re
import time
from typing import Optional
from urllib.parse import urljoin, urlparse

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

def _ok(pages: list) -> dict:
    return {"success": True, "pages": pages, "count": len(pages)}

def _err(msg: str) -> dict:
    return {"success": False, "error": msg, "pages": [], "count": 0}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _same_origin(base_url: str, url: str) -> bool:
    """Return True if url is on the same host as base_url."""
    base = urlparse(base_url)
    target = urlparse(url)
    return base.netloc == target.netloc


def _clean_text(text: str) -> str:
    """Normalise whitespace in extracted text."""
    lines = [line.strip() for line in text.splitlines()]
    lines = [l for l in lines if l]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Strategy 1: Static crawler (requests + BeautifulSoup)
# ---------------------------------------------------------------------------

def crawl_static(
    start_url: str,
    max_pages: int = 30,
    max_depth: int = 3,
    same_origin_only: bool = True,
) -> dict:
    """
    Crawl a static/server-rendered site by following links.
    Returns a list of {url, title, content} dicts.
    """
    try:
        import requests
        from bs4 import BeautifulSoup
    except ImportError:
        return _err("requests or beautifulsoup4 not installed")

    visited = set()
    queue = [(start_url, 0)]
    pages = []
    headers = {"User-Agent": "CookieJarBot/1.0 (community knowledge crawler)"}

    while queue and len(pages) < max_pages:
        url, depth = queue.pop(0)
        if url in visited:
            continue
        visited.add(url)

        try:
            resp = requests.get(url, headers=headers, timeout=15)
            resp.raise_for_status()
            ct = resp.headers.get("content-type", "")
            if "html" not in ct:
                continue

            soup = BeautifulSoup(resp.text, "html.parser")

            # Extract title
            title = ""
            if soup.title:
                title = soup.title.string or ""
            if not title:
                h1 = soup.find("h1")
                title = h1.get_text(strip=True) if h1 else url

            # Remove nav/header/footer/script/style noise
            for tag in soup(["script", "style", "nav", "header", "footer",
                              "aside", "noscript", "iframe"]):
                tag.decompose()

            # Get main content
            main = (soup.find("main") or soup.find("article") or
                    soup.find(id="content") or soup.find(class_="content") or
                    soup.find("body"))
            text = _clean_text(main.get_text(separator="\n") if main else "")

            if len(text) > 100:
                pages.append({"url": url, "title": title.strip(), "content": text})
                log.info("Crawled (static): %s (%d chars)", url, len(text))

            # Enqueue internal links
            if depth < max_depth:
                for a in soup.find_all("a", href=True):
                    href = urljoin(url, a["href"])
                    href = href.split("#")[0]  # strip fragments for static crawl
                    if href not in visited and (not same_origin_only or _same_origin(start_url, href)):
                        queue.append((href, depth + 1))

        except Exception as exc:
            log.warning("Static crawl error for %s: %s", url, exc)

    return _ok(pages)


# ---------------------------------------------------------------------------
# Strategy 2: SPA crawler (Playwright)
# ---------------------------------------------------------------------------

def _playwright_available() -> bool:
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
        return True
    except ImportError:
        return False


def crawl_spa(
    start_url: str,
    max_pages: int = 30,
    wait_ms: int = 3500,
) -> dict:
    """
    Crawl a JavaScript SPA by:
      1. Loading the page with Playwright (headless Chromium).
      2. Auto-discovering navigation links (sidebar, nav, hash anchors).
      3. Clicking/navigating to each discovered section and extracting text.

    Falls back to static crawl if Playwright is not available.
    """
    if not _playwright_available():
        log.warning("Playwright not available — falling back to static crawl")
        return crawl_static(start_url, max_pages=max_pages)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return crawl_static(start_url, max_pages=max_pages)

    pages = []
    base = urlparse(start_url)
    base_origin = f"{base.scheme}://{base.netloc}"

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = context.new_page()

            # Load the start URL
            log.info("SPA crawl: loading %s", start_url)
            try:
                page.goto(start_url, wait_until="networkidle", timeout=30000)
            except Exception:
                try:
                    page.goto(start_url, wait_until="load", timeout=30000)
                except Exception:
                    page.goto(start_url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(1000)

            # --- Discover navigation targets ---
            nav_targets = _discover_spa_nav(page, start_url, base_origin)
            log.info("SPA crawl: discovered %d nav targets", len(nav_targets))

            # If no nav targets found, scrape the current page plus follow same-origin links
            if not nav_targets:
                log.info("SPA crawl: no nav targets found, scraping page directly")
                content = _extract_spa_content(page)
                if not content:
                    # Last resort: grab all visible text
                    try:
                        content = _clean_text(page.inner_text("body"))
                    except Exception:
                        content = ""
                if content:
                    title = _get_page_title(page, start_url)
                    pages.append({"url": start_url, "title": title, "content": content})
                    log.info("SPA crawl: single-page fallback got %d chars", len(content))
                # Also try to follow any same-origin links on the page
                try:
                    links = page.evaluate("""
                        () => Array.from(document.querySelectorAll('a[href]'))
                            .map(a => a.href)
                            .filter(h => h.startsWith(window.location.origin))
                    """)
                    for lnk in list(dict.fromkeys(links))[:max_pages - 1]:
                        if lnk != start_url:
                            nav_targets.append({"url": lnk, "label": lnk, "type": "url"})
                except Exception:
                    pass

            # --- Visit each target ---
            for target in nav_targets[:max_pages]:
                try:
                    label = target.get("label", target["url"])
                    url = target["url"]
                    t_type = target.get("type", "url")

                    log.info("SPA crawl: visiting %s (%s)", label, url)

                    if t_type == "hash":
                        # Navigate to the hash anchor
                        try:
                            page.goto(url, wait_until="networkidle", timeout=15000)
                        except Exception:
                            page.goto(url, wait_until="load", timeout=15000)
                        page.wait_for_timeout(500)
                        # Try clicking the nav item if it exists
                        try:
                            fragment = urlparse(url).fragment
                            page.click(
                                f'a[href="#{fragment}"], [data-section="{fragment}"]',
                                timeout=2000,
                            )
                            page.wait_for_timeout(1000)
                        except Exception:
                            pass
                    else:
                        try:
                            page.goto(url, wait_until="networkidle", timeout=15000)
                        except Exception:
                            page.goto(url, wait_until="load", timeout=15000)
                        page.wait_for_timeout(500)

                    content = _extract_spa_content(page)

                    if len(content) > 80:
                        # Get a clean title from the page or label
                        title = _get_page_title(page, label)
                        pages.append({"url": url, "title": title, "content": content})
                        log.info("SPA crawl: got %d chars for '%s'", len(content), title)

                except Exception as exc:
                    log.warning("SPA crawl error for %s: %s", target.get("url"), exc)

            browser.close()

    except Exception as exc:
        log.error("SPA crawl fatal error: %s", exc)
        return _err(f"SPA crawl failed: {exc}")

    if not pages:
        return _err("No content could be extracted from the site")

    return _ok(pages)


def _discover_spa_nav(page, start_url: str, base_origin: str) -> list:
    """
    Discover all navigation targets on a SPA page.
    Returns a list of {url, label, type} dicts.
    """
    targets = []
    seen_urls = set()

    try:
        # Get all <a> elements
        links = page.evaluate("""
            () => Array.from(document.querySelectorAll('a[href]')).map(a => ({
                href: a.href,
                text: a.textContent.trim().substring(0, 80),
                isNav: !!(a.closest('nav') || a.closest('[class*="sidebar"]') ||
                          a.closest('[class*="nav"]') || a.closest('[class*="menu"]') ||
                          a.closest('[class*="toc"]') || a.closest('[class*="doc"]'))
            }))
        """)

        for link in links:
            href = link.get("href", "")
            text = link.get("text", "").strip()
            is_nav = link.get("isNav", False)

            if not href or not text:
                continue

            parsed = urlparse(href)

            # Hash-based SPA navigation (e.g. /docs#introduction)
            if parsed.fragment and parsed.netloc == urlparse(start_url).netloc:
                url = href
                if url not in seen_urls:
                    seen_urls.add(url)
                    targets.append({"url": url, "label": text, "type": "hash"})

            # Same-origin page links
            elif (parsed.netloc == urlparse(start_url).netloc and
                  parsed.path and parsed.path != urlparse(start_url).path and
                  is_nav):
                url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
                if url not in seen_urls:
                    seen_urls.add(url)
                    targets.append({"url": url, "label": text, "type": "url"})

    except Exception as exc:
        log.warning("Nav discovery error: %s", exc)

    # Deduplicate by fragment (keep first occurrence)
    seen_frags = set()
    deduped = []
    for t in targets:
        frag = urlparse(t["url"]).fragment or t["url"]
        if frag not in seen_frags:
            seen_frags.add(frag)
            deduped.append(t)

    return deduped


def _extract_spa_content(page) -> str:
    """Extract the main text content from the current SPA page state."""
    # Try progressively broader selectors
    selectors = [
        "main article",
        "main",
        "article",
        "[class*='content']:not(nav):not(header):not(footer)",
        "[class*='prose']",
        "[class*='markdown']",
        "[class*='doc-content']",
        "[class*='page-content']",
        "#content",
        "#root",
    ]

    for selector in selectors:
        try:
            el = page.query_selector(selector)
            if el:
                text = el.inner_text()
                cleaned = _clean_text(text)
                if len(cleaned) > 100:
                    return cleaned
        except Exception:
            continue

    # Final fallback: full body minus nav/header/footer
    try:
        text = page.evaluate("""
            () => {
                const clone = document.body.cloneNode(true);
                clone.querySelectorAll('nav, header, footer, script, style, noscript').forEach(e => e.remove());
                return clone.innerText || clone.textContent || '';
            }
        """)
        return _clean_text(text)
    except Exception:
        return ""


def _get_page_title(page, fallback: str) -> str:
    """Get the best available title for the current page."""
    try:
        # Try h1 first
        h1 = page.query_selector("h1")
        if h1:
            text = h1.inner_text().strip()
            if text and len(text) < 120:
                return text
        # Then page title
        title = page.title()
        if title:
            return title.strip()
    except Exception:
        pass
    return fallback


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def crawl_site(
    url: str,
    max_pages: int = 30,
    force_mode: Optional[str] = None,
) -> dict:
    """
    Main entry point. Auto-detects whether to use SPA or static crawl.

    Args:
        url: The starting URL to crawl.
        max_pages: Maximum number of pages/sections to ingest.
        force_mode: "spa" or "static" to override auto-detection.

    Returns:
        {success, pages: [{url, title, content}], count}
    """
    if force_mode == "static":
        return crawl_static(url, max_pages=max_pages)
    if force_mode == "spa":
        return crawl_spa(url, max_pages=max_pages)

    # Auto-detect: if Playwright is available, always use SPA mode
    # (it handles both static and dynamic sites gracefully)
    if _playwright_available():
        log.info("Auto-selected SPA crawl mode for %s", url)
        return crawl_spa(url, max_pages=max_pages)
    else:
        log.info("Auto-selected static crawl mode for %s (Playwright unavailable)", url)
        return crawl_static(url, max_pages=max_pages)
