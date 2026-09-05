#!/usr/bin/env python3
"""日报主执行脚本：把 curated.json 写入飞书多维表格、机器人卡片推送、云文档归档。

依赖 lark-cli 已配置（config init + auth login 完成）。

用法：
    python run_daily.py curated.json            # 写表 + 推送 + 归档
    python run_daily.py curated.json --dry-run  # 只打印，不执行
"""
import html
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).parent


def _load_config():
    """用户配置：config.json（复制自 config.example.json 或由首次配置引导生成）。
    未配置时返回 None（调用方据此走"仅输出日报"分支），环境变量可覆盖。"""
    f = HERE / "config.json"
    if not f.exists():
        return None
    cfg = json.loads(f.read_text(encoding="utf-8"))
    for env, key in [("FEISHU_BASE_TOKEN", "base_token"), ("FEISHU_TABLE_ID", "table_id"),
                     ("FEISHU_USER_OPEN_ID", "user_open_id"), ("FEISHU_ARCHIVE_DOC_ID", "archive_doc_id"),
                     ("FEISHU_ARCHIVE_ANCHOR_BLOCK", "archive_anchor_block")]:
        if os.environ.get(env):
            cfg[key] = os.environ[env]
    if not all(cfg.get(k) for k in ("base_token", "table_id", "user_open_id", "base_url")):
        return None
    return cfg


CONFIG = _load_config()
CONFIGURED = CONFIG is not None
BASE_TOKEN = CONFIG.get("base_token", "") if CONFIG else ""
TABLE_ID = CONFIG.get("table_id", "") if CONFIG else ""
USER_OPEN_ID = CONFIG.get("user_open_id", "") if CONFIG else ""
BASE_URL = CONFIG.get("base_url", "") if CONFIG else ""
# 日报归档云文档（可选）：每日 block_insert_after 到锚点块之后，最新永远在最上
ARCHIVE_DOC_ID = CONFIG.get("archive_doc_id", "") if CONFIG else ""
ARCHIVE_ANCHOR_BLOCK = CONFIG.get("archive_anchor_block", "") if CONFIG else ""

LARK = os.environ.get("LARK_CLI", "lark-cli")


def _resolve_lark():
    """定位 lark-cli 可执行文件。优先环境变量 LARK_CLI，其次 which，
    最后探测 Windows npm 全局包内 exe（PATH 缺失时的兜底）。"""
    if os.environ.get("LARK_CLI"):
        return [os.environ["LARK_CLI"]]
    exe = shutil.which(LARK) or shutil.which(LARK + ".exe")
    if exe:
        return [exe]
    guesses = [
        Path.home() / "AppData/Roaming/npm/node_modules/@larksuite/cli/bin/lark-cli.exe",
        Path("/usr/local/bin/lark-cli"),
        Path.home() / ".local/bin/lark-cli",
    ]
    for g in guesses:
        if g.exists():
            return [str(g)]
    return [LARK]


LARK_CMD = _resolve_lark()
FIELDS = ("标题", "摘要", "原文链接", "来源", "分类", "标签", "重要度", "日期")
# curated.json 的英文键 -> 表格中文字段
KEY_MAP = {"title": "标题", "summary": "摘要", "url": "原文链接",
           "source": "来源", "category": "分类", "tags": "标签",
           "importance": "重要度", "published": "日期"}
# 源站名 -> 表格"来源"单选选项；未匹配的一律归"其他"
SOURCE_ALIASES = {
    "OpenAI 官方新闻": "OpenAI", "Google DeepMind 博客": "DeepMind",
    "Anthropic 新闻": "Anthropic",
    "Hugging Face 博客": "HuggingFace", "Hacker News AI 热帖": "Hacker News",
    "TechCrunch AI": "TechCrunch", "The Verge AI": "The Verge",
    "MIT Tech Review AI": "MIT TR", "InfoQ 中文": "InfoQ",
    "arXiv cs.AI 新论文": "arXiv", "arXiv cs.CL 新论文": "arXiv",
}
KNOWN_SOURCES = {"OpenAI", "DeepMind", "Anthropic", "HuggingFace",
                 "Hacker News", "TechCrunch", "The Verge", "MIT TR",
                 "InfoQ", "arXiv", "其他"}
# 表格"来源"字段的完整选项池（ensure_source_options 用）
SOURCE_OPTIONS = list(KNOWN_SOURCES)


def run(args):
    """执行 lark-cli 命令；对瞬时错误（如选项池更新后的索引延迟）间隔重试一次。"""
    for attempt in (1, 2):
        r = subprocess.run(LARK_CMD + args, capture_output=True, text=True,
                           encoding="utf-8", shell=False)
        if r.returncode == 0 and '"ok": false' not in (r.stdout or ""):
            return json.loads(r.stdout)
        if attempt == 1:
            time.sleep(2)
        else:
            print(r.stdout or r.stderr, file=sys.stderr)
            raise RuntimeError(f"command failed: {args[0]} {args[1]} ...")


def to_fields(it):
    # 英文键归一成中文字段名（两种命名都兼容）
    it = {KEY_MAP.get(k, k): v for k, v in it.items()}
    rec = {k: it[k] for k in FIELDS if k in it and it[k]}
    if isinstance(rec.get("分类"), str):
        rec["分类"] = [rec["分类"]]
    if isinstance(rec.get("来源"), list):
        rec["来源"] = rec["来源"][:1]
    if rec.get("来源"):
        src = rec["来源"][0] if isinstance(rec["来源"], list) else rec["来源"]
        rec["来源"] = [SOURCE_ALIASES.get(src, src if src in KNOWN_SOURCES else "其他")]
    if isinstance(rec.get("重要度"), str):
        rec["重要度"] = [rec["重要度"]]
    if not rec.get("日期"):
        rec["日期"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    else:
        try:  # ISO(含Z) -> 本地时间字符串，CLI 兼容性最好
            dt = datetime.fromisoformat(str(rec["日期"]).replace("Z", "+00:00"))
            rec["日期"] = dt.astimezone().strftime("%Y-%m-%d %H:%M")
        except ValueError:
            pass
    return rec


def ensure_source_options():
    """把 SOURCE_OPTIONS 合并进表格"来源"字段选项池（幂等，只增不减）。"""
    d = run(["base", "+field-get", "--base-token", BASE_TOKEN,
             "--table-id", TABLE_ID, "--field-id", "来源", "--as", "bot"])
    field = d.get("data", {}).get("field", {})
    opts = [o.get("name") for o in field.get("options", []) if o.get("name")]
    merged = opts + [s for s in SOURCE_OPTIONS if s not in opts]
    if merged == opts:
        return
    run(["base", "+field-update", "--base-token", BASE_TOKEN, "--table-id", TABLE_ID,
         "--field-id", "来源", "--json", json.dumps(
             {"name": "来源", "type": "select", "multiple": False,
              "options": [{"name": t} for t in merged]}, ensure_ascii=False),
         "--as", "bot", "--yes"])
    print(f"[feishu] source options: +{len(merged) - len(opts)}")


def ensure_tag_options(items):
    """标签是自由词：写入前把本次出现的标签合并进"标签"字段选项池，避免 option not_found。"""
    new_tags = sorted({t for it in items for t in (it.get("tags") or [])})
    if not new_tags:
        return
    d = run(["base", "+field-get", "--base-token", BASE_TOKEN,
             "--table-id", TABLE_ID, "--field-id", "标签", "--as", "bot"])
    field = d.get("data", {}).get("field", {})
    opts = [o.get("name") for o in field.get("options", []) if o.get("name")]
    merged = opts + [t for t in new_tags if t not in opts]
    if merged == opts:
        return
    run(["base", "+field-update", "--base-token", BASE_TOKEN, "--table-id", TABLE_ID,
         "--field-id", "标签", "--json", json.dumps(
             {"name": "标签", "type": "select", "multiple": True,
              "options": [{"name": t} for t in merged]}, ensure_ascii=False),
         "--as", "bot", "--yes"])
    print(f"[feishu] tag options: +{len(merged) - len(opts)}")


def write_records(items):
    # 逐条写入：批量 payload 经命令行传参在部分环境下会静默丢字段，
    # 单条已实测稳定；每天 <30 条，串行调用开销可忽略
    ensure_source_options()
    ensure_tag_options(items)
    total = 0
    for x in items:
        payload = json.dumps({"create_records": [to_fields(x)]}, ensure_ascii=False)
        data = run(["base", "+record-batch-create",
                    "--base-token", BASE_TOKEN, "--table-id", TABLE_ID,
                    "--json", payload, "--as", "bot"])
        total += len(data.get("data", {}).get("record_id_list", []))
    print(f"[feishu] wrote {total} records")
    return total


WEEKDAYS = "日一二三四五六"  # %w: 0=周日


def _card_row(imp, title, url, cat, summary):
    title_md = f"[{title}]({url})" if url else f"**{title}**"
    main = [{'tag': 'markdown', 'content': title_md}]
    if summary:
        main.append({'tag': 'markdown', 'content': summary})
    return {'tag': 'column_set', 'flex_mode': 'bisect', 'columns': [
        {'tag': 'column', 'width': 'auto',
         'elements': [{'tag': 'markdown', 'content': imp}]},
        {'tag': 'column', 'width': 'weighted', 'weight': 1, 'vertical_align': 'top',
         'elements': main},
        {'tag': 'column', 'width': 'auto', 'vertical_align': 'top',
         'elements': [{'tag': 'markdown', 'content': cat}]},
    ]}


def push_digest(items, digest=None):
    """卡片(column_set 分栏) → markdown → text 三级降级，日报必达。"""
    today = time.strftime("%Y-%m-%d")
    weekday = WEEKDAYS[int(time.strftime("%w")) % 7]
    n_high = sum(1 for i in items if i.get("importance") == "高")
    if not digest:
        tops = [it["title"] for it in items if it.get("importance") == "高"]
        digest = ("**今日重点：**" + "；".join(tops[:3]) + "。") if tops else "今日无高重要度条目。"

    card = {
        'config': {'wide_screen_mode': True},
        'header': {'template': 'blue', 'title': {
            'tag': 'plain_text', 'content': f'📰 AI 日报 · {today}（周{weekday}）'}},
        'elements': [
            {'tag': 'markdown',
             'content': f"共 **{len(items)}** 条 · 🔥 高关注 **{n_high}** 条\n\n**今日爆点**\n{digest}"},
            {'tag': 'hr'},
        ],
    }
    for i, it in enumerate(items[:30], 1):
        card['elements'].append(_card_row(
            imp="🔥" if it.get("importance") == "高" else f"{i}.",
            title=it['title'], url=it.get("url", ""),
            cat=it.get("category", ""), summary=it.get("summary", "")))
        card['elements'].append({'tag': 'hr'})
    card['elements'].append({
        'tag': 'markdown',
        'content': "📊 完整数据（筛选 / 分组 / 回溯）👉 [AI资讯库 · 多维表格](" + BASE_URL + ")"})

    md = (f"# 📰 AI 日报 · {today}（周{weekday}）\n共 {len(items)} 条\n\n**今日爆点**\n{digest}\n---\n" +
          "\n".join(f"{i}. {'' if (x := it.get('importance')) != '高' else '🔥 '}{it['title']}\n"
                    f"{it.get('summary', '')}\n👉 [阅读原文]({it.get('url', '')})"
                    for i, it in enumerate(items[:30], 1)) +
          f"\n---\n📊 完整数据 👉 [AI资讯库]({BASE_URL})")
    try:
        run(["im", "+messages-send", "--user-id", USER_OPEN_ID, "--msg-type",
             "interactive", "--content", json.dumps(card, ensure_ascii=False), "--as", "bot"])
    except Exception:
        try:
            run(["im", "+messages-send", "--user-id", USER_OPEN_ID,
                 "--markdown", md, "--as", "bot"])
        except Exception:
            plain = md.replace("**", "")
            for seg in range(0, len(plain), 9000):
                run(["im", "+messages-send", "--user-id", USER_OPEN_ID,
                     "--text", plain[seg:seg + 9000], "--as", "bot"])
    print("[feishu] digest pushed")


CAT_EMOJI = {"前沿动态": "🧪", "社区热点": "💬", "中文资讯": "🇨🇳",
             "论文速递": "📄", "产品动态": "🚀"}


def _esc(s):
    return html.escape(str(s or ""), quote=False)


def archive_to_doc(items, digest=None):
    """把当日日报插入归档云文档锚点块之后（最新在最上方）。未配置归档则跳过。"""
    if not (ARCHIVE_DOC_ID and ARCHIVE_ANCHOR_BLOCK):
        print("[feishu] archive skipped (not configured)")
        return
    today = time.strftime("%Y-%m-%d")
    weekday = WEEKDAYS[int(time.strftime("%w")) % 7]
    if not digest:
        digest = "（无总评）"
    for prefix in ("今日爆点：", "今日爆点:", "今日爆点"):
        digest = digest.removeprefix(prefix)

    xml = [f"<hr/>",
           f"<h2>📰 {today}（周{weekday}）· {len(items)} 条</h2>",
           f'<callout emoji="🔥" background-color="light-orange">'
           f"<p><b>今日爆点</b>　{_esc(digest)}</p></callout>"]

    by_cat = {}
    for it in items:
        by_cat.setdefault(it.get("category", "其他"), []).append(it)
    n = 0
    for cat, group in by_cat.items():
        emoji = CAT_EMOJI.get(cat, "📌")
        xml.append(f"<h3>{emoji} {_esc(cat)} · {len(group)}</h3><ul>")
        for it in group:
            n += 1
            star = "🔥 " if it.get("importance") == "高" else ""
            title = _esc(it["title"])
            if it.get("url"):
                head = f'<a href="{html_href(it["url"])}"><b>{title}</b></a>'
            else:
                head = f"<b>{title}</b>"
            line = f"<li><p>{star}{head}"
            if it.get("summary"):
                line += f'<br/><span text-color="gray">{_esc(it["summary"])}</span>'
            line += "</p></li>"
            xml.append(line)
        xml.append("</ul>")

    xml.append(f'<p><span text-color="gray">完整数据与历史回溯 👉 '
               f'<a href="{BASE_URL}">AI资讯库 · 多维表格</a></span></p>')
    f = Path(__file__).parent / "today_doc.xml"
    f.write_text("".join(xml), encoding="utf-8")
    run(["docs", "+update", "--doc", ARCHIVE_DOC_ID,
         "--command", "block_insert_after", "--block-id", ARCHIVE_ANCHOR_BLOCK,
         "--content", f"@{f}", "--as", "user"])
    print("[feishu] archived to doc")


def html_href(url):
    return html.escape(url, quote=True)


def main():
    dry = "--dry-run" in sys.argv
    path = Path(sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-")
                else HERE / "curated.json")
    raw = json.loads(path.read_text(encoding="utf-8"))
    digest = None
    if isinstance(raw, dict):
        digest = raw.get("digest")
        items = raw.get("items", [])
    else:
        items = raw
    if not CONFIGURED:
        # 未配置飞书：输出日报 JSON 供 Agent 整理回复，不报错、不写任何东西
        print(json.dumps({"mode": "chat_only", "digest": digest, "items": items},
                         ensure_ascii=False, indent=2))
        print("[run_daily] 未配置飞书（config.json 缺失或不完整），已跳过落地。", file=sys.stderr)
        return
    if dry:
        print(f"[digest] {digest}")
        for it in items:
            print(json.dumps(to_fields(it), ensure_ascii=False))
        return
    write_records(items)
    push_digest(items, digest)
    try:
        archive_to_doc(items, digest)
    except Exception as exc:  # 归档失败不影响推送主链路
        print(f"[warn] archive failed: {exc}", file=sys.stderr)


if __name__ == "__main__":
    main()
