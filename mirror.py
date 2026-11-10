#!/usr/bin/env python3
"""Archive public assets for a faithful static snapshot of one Shopify page.

The page's live Shopify operations (inventory/cart/checkout) are not replicated.
"""

import concurrent.futures
import hashlib
import html
import json
import pathlib
import re
import urllib.error
import urllib.parse
import urllib.request


ROOT = pathlib.Path(__file__).resolve().parent
SOURCE = ROOT / "source.html"
ORIGIN = "https://thechristmaspalace.com"

# Only first-party Shopify CDN files are archived. Live commerce and customer
# services deliberately remain on their original domains.
ASSET_PATTERN = re.compile(
    r"(?:https?:)?//thechristmaspalace\.com/cdn/(?:shop|shopifycloud)/[^\s\"'<>),\\]+"
    r"|(?<![\w:])/cdn/(?:shop|shopifycloud)/[^\s\"'<>),\\]+",
    re.IGNORECASE,
)


def canonical(raw):
    candidate = html.unescape(raw).replace("\\/", "/")
    if candidate.startswith("//"):
        candidate = "https:" + candidate
    elif candidate.startswith("/"):
        candidate = ORIGIN + candidate
    parsed = urllib.parse.urlsplit(candidate)
    if parsed.hostname != "thechristmaspalace.com":
        return None
    if not parsed.path.startswith(("/cdn/shop/", "/cdn/shopifycloud/")):
        return None
    return parsed


def asset_type(path):
    suffix = pathlib.PurePosixPath(path).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif", ".svg"}:
        return "images", suffix
    if suffix in {".mp4", ".webm", ".mov", ".m4v"}:
        return "videos", suffix
    if suffix in {".css", ".js", ".woff", ".woff2", ".ttf", ".otf"}:
        return "code", suffix
    return "misc", suffix or ".bin"


def download_one(item):
    key, candidates, local_path, category = item
    target = ROOT / local_path
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_file() and target.stat().st_size:
        return key, target.stat().st_size, None

    # For image srcsets, prefer the highest version up to 1500px across source
    # variants. Identical photos only need one downloaded file.
    def rank(url):
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
        width = int(q.get("width", ["0"])[0] or 0)
        return (0 if 0 < width <= 1500 else 1, -width if width else 0)

    sorted_candidates = sorted(candidates, key=rank)
    last_error = "No candidate URL"
    for chosen in sorted_candidates:
        try:
            request = urllib.request.Request(
                chosen,
                headers={"User-Agent": "Mozilla/5.0 (compatible; SiteArchive/1.0)"},
            )
            with urllib.request.urlopen(request, timeout=28) as response:
                body = response.read(15 * 1024 * 1024 + 1)
                if len(body) > 15 * 1024 * 1024:
                    raise ValueError("asset exceeds 15 MB")
                if not body:
                    raise ValueError("empty download")
                target.write_bytes(body)
                return key, len(body), None
        except (OSError, ValueError, urllib.error.URLError) as error:
            last_error = str(error)
    return key, 0, last_error


def main():
    source = SOURCE.read_text(encoding="utf-8")
    urls = {}
    for found in ASSET_PATTERN.finditer(source):
        parsed = canonical(found.group(0))
        if parsed is None:
            continue
        key = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        url = urllib.parse.urlunsplit(parsed)
        urls.setdefault(key, set()).add(url)

    registry = {}
    tasks = []
    for key, candidates in urls.items():
        parsed = urllib.parse.urlsplit(key)
        category, suffix = asset_type(parsed.path)
        name_hash = hashlib.sha1(key.encode()).hexdigest()[:16]
        name = pathlib.PurePosixPath(parsed.path).stem
        name = re.sub(r"[^\w-]+", "-", name)[:42].strip("-") or "asset"
        destination = f"assets/{category}/{name}-{name_hash}{suffix}"
        registry[key] = destination
        tasks.append((key, candidates, destination, category))

    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=14) as pool:
        for key, size, error in pool.map(download_one, tasks):
            results[key] = {"bytes": size, "error": error, "path": registry[key]}

    # Keep links to other storefront pages on the original shop. This snapshot
    # has no cloned backend or product-detail pages.
    updated = re.sub(
        r'(?P<attr>\b(?:href|action|formaction|src)\s*=\s*["\'])/(?!(?:/|assets/|#))',
        lambda match: match.group("attr") + ORIGIN + "/",
        source,
        flags=re.IGNORECASE,
    )

    def replace(match):
        original = match.group(0)
        parsed = canonical(original)
        if not parsed:
            return original
        key = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        entry = results.get(key)
        if entry and not entry["error"]:
            return entry["path"]
        # If a resource can't be archived, the remote original still renders.
        return urllib.parse.urlunsplit(parsed).replace("&", "&amp;")

    updated = ASSET_PATTERN.sub(replace, updated)

    # A few Shopify stylesheet references live in inline CSS. Keep the CSS's
    # relative image/font URLs pointing to the original host.
    for key, entry in results.items():
        if entry["error"] or not entry["path"].endswith(".css"):
            continue
        style_file = ROOT / entry["path"]
        try:
            content = style_file.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        content = re.sub(
            r"url\(\s*([\"']?)(?!data:|https?:|//|#)([^)\"']+)\1\s*\)",
            lambda m: "url('" + urllib.parse.urljoin(key, m.group(2).strip()) + "')",
            content,
            flags=re.IGNORECASE,
        )
        style_file.write_text(content, encoding="utf-8")

    (ROOT / "index.html").write_text(updated, encoding="utf-8")
    (ROOT / "assets-manifest.json").write_text(
        json.dumps(
            {"original": ORIGIN + "/pages/up-to-50-off-sale", "files": results},
            indent=2,
        ),
        encoding="utf-8",
    )
    failed = [(key, result["error"]) for key, result in results.items() if result["error"]]
    stats = {}
    for task in tasks:
        category = task[3]
        stats.setdefault(category, {"files": 0, "bytes": 0})
        if not results[task[0]]["error"]:
            stats[category]["files"] += 1
            stats[category]["bytes"] += results[task[0]]["bytes"]
    print(json.dumps({"total": len(tasks), "stats": stats, "failed": failed[:20], "failed_count": len(failed)}, indent=2))


if __name__ == "__main__":
    main()
