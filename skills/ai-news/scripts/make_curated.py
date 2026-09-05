#!/usr/bin/env python3
"""把人工/LLM 的筛选结果与 items.json 合成 curated.json。
selection.json 格式:
  {"digest": "今日总评：2-3 句话概括当天爆点与大势（LLM 撰写，可选）",
   "items": [{idx, title, summary, importance, category, tags, source_override}]}
输出 curated.json: {"digest": ..., "items": [...]}（run_daily 兼容两种结构）
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).parent
items = {i: it for i, it in enumerate(
    json.loads((HERE / "items.json").read_text(encoding="utf-8"))["items"])}
raw = json.loads((HERE / "selection.json").read_text(encoding="utf-8"))
if isinstance(raw, list):          # 兼容旧格式（纯数组）
    raw = {"digest": None, "items": raw}
sel = raw["items"]

out = []
for s in sel:
    idx = s.get("idx")
    if idx not in items:
        sys.exit(f"[curate] selection.json 引用了不存在的 idx={idx}（items.json 共 {len(items)} 条，0 起）")
    src = items[idx]
    out.append({
        "title": s.get("title") or src["title"],
        "summary": s.get("summary", ""),
        "url": src["url"],
        "source": s.get("source_override") or src["source"],
        "category": s.get("category") or src["category"],
        "tags": s.get("tags", []),
        "importance": s.get("importance", "中"),
        "published": src.get("published"),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    })

(HERE / "curated.json").write_text(
    json.dumps({"digest": raw.get("digest"), "items": out},
               ensure_ascii=False, indent=2), encoding="utf-8")
print(f"curated {len(out)} items -> curated.json")
