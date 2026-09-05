#!/usr/bin/env python3
"""AI 资讯采集脚本：从各信息源抓取近 N 小时条目，输出结构化 JSON。

用法（任意目录均可）：
    python fetch_sources.py [--hours 24] [--out items.json]

输出的每条记录包含：source, category, title, url, published, summary_raw。
本脚本只负责"抓原文、给原始链接"，不做摘要与筛选——那是 Agent/LLM 的职责。

网络策略：每个源在 sources.json 里声明 network=proxy|direct。
  proxy  -> 使用环境变量 HTTPS_PROXY/HTTP_PROXY（无则直连）
  direct -> 强制直连（中文站点，走代理反而会被重置）
"""
import argparse
import json
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from xml.etree import ElementTree

import feedparser
import requests

HERE = Path(__file__).parent
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128.0 Safari/537.36"}


def make_session(network):
    s = requests.Session()
    s.headers.update(UA)
    if network == "direct":
        s.trust_env = False  # 忽略环境代理，强制直连
    return s


def within_hours(entry_dt, hours):
    if entry_dt is None:
        return True
    return (datetime.now(timezone.utc) - entry_dt) < timedelta(hours=hours)


def parse_published(parsed):
    if not parsed:
        return None
    try:
        return datetime(*parsed[:6], tzinfo=timezone.utc)
    except Exception:
        return None


def get_with_retry(session, url, params=None, attempts=3):
    last = None
    for i in range(attempts):
        try:
            return session.get(url, params=params, timeout=30)
        except requests.RequestException as exc:
            last = exc
            time.sleep(2 * (i + 1))
    raise last


def fetch_rss(src, hours):
    resp = get_with_retry(make_session(src.get("network")), src["url"])
    resp.raise_for_status()
    feed = feedparser.parse(resp.content)
    items = []
    for e in feed.entries:
        dt = parse_published(getattr(e, "published_parsed", None))
        if not within_hours(dt, hours):
            continue
        items.append({
            "source": src["name"],
            "category": src["category"],
            "title": e.get("title", "").strip(),
            "url": e.get("link", ""),
            "published": dt.isoformat() if dt else None,
            "summary_raw": (e.get("summary") or "")[:2000],
        })
    return items


AI_WORDS = ("ai", "llm", "gpt", "claude", "gemini", "openai", "anthropic",
            "deepmind", "agent", "transformer", "diffusion", "machine learning",
            "deep learning", "neural net", "copilot", "deepseek", "llama",
            "mistral", "foundation model", "inference")
# 词边界正则：避免 "ai" 子串误伤 said/email/detail 等
AI_WORDS_RE = re.compile(r"\b(?:" + "|".join(w.replace(" ", r"\s+") for w in AI_WORDS) + r")\b", re.I)


def fetch_hn(src, hours):
    # 按热度排序 + 动态时间窗口 + 最低票数；关键词过滤交给下游 LLM 做精准分类
    since = time.time() - hours * 3600
    params = {"tags": "story", "hitsPerPage": "30",
              "numericFilters": f"created_at_i>{int(since)},points>20"}
    resp = get_with_retry(make_session(src.get("network")), src["url"], params=params)
    resp.raise_for_status()
    items = []
    for hit in resp.json().get("hits", []):
        if hit.get("created_at_i", 0) < since:
            continue
        if not AI_WORDS_RE.search(hit.get("title") or ""):
            continue
        items.append({
            "source": src["name"],
            "category": src["category"],
            "title": hit.get("title") or hit.get("story_title") or "",
            "url": hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}",
            "published": datetime.fromtimestamp(
                hit.get("created_at_i", 0), tz=timezone.utc).isoformat(),
            "summary_raw": (hit.get("story_text") or "")[:2000],
        })
    return items


def fetch_sitemap(src, hours):
    """从 sitemap.xml 抓取新闻 URL（无 RSS 的站点用）。lastmod 在窗口内才收录。"""
    resp = get_with_retry(make_session(src.get("network")), src["url"])
    resp.raise_for_status()
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    root = ElementTree.fromstring(resp.content)
    prefix = src.get("url_prefix", "")
    items = []
    for url_el in root.findall("sm:url", ns):
        loc = (url_el.findtext("sm:loc", "", ns) or "").strip()
        if not loc.startswith(prefix):
            continue
        lastmod = url_el.findtext("sm:lastmod", "", ns)
        dt = None
        if lastmod:
            try:
                dt = datetime.fromisoformat(lastmod.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
            except ValueError:
                pass
        if not within_hours(dt, hours):
            continue
        slug = loc.rstrip("/").rsplit("/", 1)[-1]
        title = re.sub(r"[-_]", " ", slug).strip()
        items.append({
            "source": src["name"],
            "category": src["category"],
            "title": title,
            "url": loc,
            "published": dt.isoformat() if dt else None,
            "summary_raw": "",
        })
    return items


fetchers = {"rss": fetch_rss, "hn": fetch_hn, "arxiv": fetch_rss, "sitemap": fetch_sitemap}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=int, default=24, help="时间窗口，默认 24 小时")
    ap.add_argument("--out", default=str(HERE / "items.json"))
    args = ap.parse_args()

    cfg = json.loads((HERE / "sources.json").read_text(encoding="utf-8"))
    all_items, errors = [], []
    for src in cfg["sources"]:
        try:
            got = fetchers[src["type"]](src, args.hours)
            all_items.extend(got)
            print(f"[ok] {src['id']}: {len(got)} items", file=sys.stderr)
        except Exception as exc:
            errors.append({"source": src["id"], "error": str(exc)})
            print(f"[fail] {src['id']}: {exc}", file=sys.stderr)

    seen, deduped = set(), []
    for it in all_items:
        if it["url"] and it["url"] not in seen:
            seen.add(it["url"])
            deduped.append(it)

    Path(args.out).write_text(
        json.dumps({"fetched_at": datetime.now(timezone.utc).isoformat(),
                    "window_hours": args.hours,
                    "errors": errors,
                    "items": deduped},
                   ensure_ascii=False, indent=2),
        encoding="utf-8")
    print(f"total {len(deduped)} items -> {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
