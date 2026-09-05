---
name: ai-news
description: 生成每日 AI 新闻日报并推送到飞书。当用户想要 AI 每日热点、AI 日报、AI 新闻，或想把日报接入飞书时使用。
---

# AI 每日资讯采集技能

> **什么时候用这个技能**：用户提到"AI 日报 / AI 新闻 / 今天 AI 圈有什么动态 / 推送日报 / 写入飞书表格"等意图时，按本文件流程执行。
>
> **用户可能怎么说**："帮我跑一下今天的 AI 日报" / "看看今天 AI 圈有什么大事" / "把日报推到我飞书"。

抓取当日 AI 资讯，筛选摘要成日报；若已配置飞书则同步落地三件套（多维表格 / 机器人推送 / 云文档归档）。**每条信息保留原始链接，可溯源**。

## 工作流程（Agent 严格按此执行）

### 第 0 步：环境准备

```bash
cd <skill目录>/scripts
python -c "import feedparser, requests" || pip install feedparser requests
```

lark-cli 无需手动指定：脚本自动探测 PATH 和常见安装位置（含 Windows npm 全局目录）。确实找不到且用户要做飞书配置时，先 `npx @larksuite/cli@latest install`。

### 第 1 步：采集原始条目

```bash
python fetch_sources.py --hours 24        # 输出 items.json（每日定时跑建议 --hours 26）
```

- 每个源在 `sources.json` 声明 `network: proxy|direct`：海外源走代理，中文源强制直连
- 个别源失败会记入 `items.json` 的 `errors`，继续执行，不要中断

### 第 2 步：筛选与摘要（Agent/LLM 的职责）

读取 `items.json` 全部条目，然后：

1. **去噪**：剔除与 AI 无关的条目（HN/InfoQ 混入大量非 AI 内容）
2. **去重合并**：同一事件多源报道合并，保留最权威的原文链接
3. **摘要**：每条 2-3 句中文，只陈述事实
4. **打标**：`category`（前沿动态/社区热点/中文资讯/论文速递/产品动态）、`importance`（高=行业级发布·融资·政策 / 中 / 低）、自由 `tags`
5. **当日总评**：写 2-3 句 `digest`，概括今天的爆点与大势

把结果写入 `scripts/selection.json`，格式如下（`idx` 引用 items.json 的数组下标；`source_override` 可选，用于把来源归一为表格选项名）：

```json
{
  "digest": "2-3 句当日总评",
  "items": [
    {"idx": 0, "title": "可覆盖标题", "summary": "摘要", "importance": "高",
     "category": "前沿动态", "tags": ["标签"], "source_override": "OpenAI"}
  ]
}
```

然后：

```bash
python make_curated.py       # 合成 curated.json（10-30 条）
```

**铁律**：`url` 只能取自 items.json 原文，不得改写或猜测——可溯源是本技能的核心价值。

### 第 3 步：落地（按配置分支，必须先判断）

**先检查 `scripts/config.json` 是否存在且 `base_token`/`table_id`/`user_open_id`/`base_url` 齐全：**

#### 分支 A：已配置 → 执行落地

```bash
python run_daily.py curated.json    # 写表格 + 卡片推送 + 云文档归档
```

- 写入前自动合并来源/标签选项池，逐条写入
- 推送三级降级保送达（卡片→markdown→纯文本）；归档未配置自动跳过
- 重复运行会重复写入，勿重跑

#### 分支 B：未配置 → 对话输出 + 现场引导

1. 把 curated.json 整理成日报正文直接回复用户（总评 + 每条"标题 / 摘要 / 原文链接"）
2. 然后问一句："要不要接入你的飞书？接入后日报会写进你的表格、每天推送到你私聊。"
3. 用户同意 → 执行「首次配置引导」（见下节），完成后再跑上面的落地命令
4. 用户拒绝 → 到此为止，不追问

### 首次配置引导（仅在用户同意接入飞书时执行）

前置：lark-cli 未安装则先 `npx @larksuite/cli@latest install`（需 Node.js）。

按顺序执行，每步把产物/链接直接发给用户：

1. **创建应用**：`lark-cli config init --new`（阻塞命令，输出授权链接和二维码）→
   把链接发给用户点确认。完成后凭证自动保存，应用权限与机器人能力自动就绪
2. **用户授权**：`lark-cli auth login --recommend`（同样输出链接/二维码）→
   用户扫码确认，所需权限自动申请自动审批。从输出提取 `ou_` 开头的 open_id
3. **建表（--as user，表归用户所有）**：
   ```bash
   lark-cli base +base-create --name "AI资讯库" --table-name "AI日报" --time-zone "Asia/Shanghai" --as user --fields '[
    {"name":"标题","type":"text"},
    {"name":"摘要","type":"text"},
    {"name":"原文链接","type":"text"},
    {"name":"来源","type":"select","options":[{"name":"OpenAI"},{"name":"DeepMind"},{"name":"Anthropic"},{"name":"HuggingFace"},{"name":"Hacker News"},{"name":"TechCrunch"},{"name":"The Verge"},{"name":"MIT TR"},{"name":"InfoQ"},{"name":"arXiv"},{"name":"其他"}]},
    {"name":"分类","type":"select","multiple":true,"options":[{"name":"前沿动态"},{"name":"社区热点"},{"name":"中文资讯"},{"name":"论文速递"},{"name":"产品动态"}]},
    {"name":"标签","type":"select","multiple":true},
    {"name":"重要度","type":"select","options":[{"name":"高"},{"name":"中"},{"name":"低"}]},
    {"name":"日期","type":"dateTime"}
   ]'
   ```
   记下输出里的 `base_token` 和 `url`；再用 `base +table-list --base-token <token> --as user` 取 `table_id`
4. **把应用授权进表**（bot 后续写入需要）：
   ```bash
   lark-cli drive +member-add --token <base_token> --type bitable      --member-type appid --member-id <该应用的AppID，形如 cli_xxx> --perm full_access --as user --yes
   ```
   ⚠️ 不要用 bot 身份建表再授用户——新应用 bot 缺 drive 系权限且需发版生效；
   user 建表 + 授权 app 是实测通畅的组合，且表天然归用户所有
5. **建归档文档**（可选）：
   ```bash
   lark-cli docs +create --title "AI 日报归档" --content "本文档由 ai-news 技能每日自动维护：最新日报始终在最上方。" --doc-format markdown --as user
   lark-cli docs +fetch --doc <doc_token> --detail with-ids --as user   # 取"本文档由…"段的 <p id="..."> 作锚点
   ```
6. **写 `scripts/config.json`**：
   ```json
   {"base_token": "…", "table_id": "tbl…", "user_open_id": "ou_…",
    "base_url": "表格完整链接", "archive_doc_id": "…或空", "archive_anchor_block": "…或空"}
   ```
7. **端到端验证**：`python run_daily.py curated.json`，并告诉用户去飞书查看测试消息

引导失败时：把报错原样告诉用户，指路仓库 `docs/faq.md`，不要自行反复重试。

### 完成后：向用户报告

- **分支 A（已配置）**：四项报告——**今日条数、分类分布、总评一句话、失败源**
- **分支 B（未配置）**：日报正文 + 配置引导结果

若端到端失败：报告具体错误即可，不要重试超过一次。

## 用户配置（scripts/config.json）

由首次配置引导自动生成，一般无需手改。字段含义与获取方式见 `config.example.json` 注释；全部字段支持环境变量覆盖（`FEISHU_BASE_TOKEN` 等）。**本 skill 不含任何密钥**，飞书凭据由 lark-cli 全局配置管理。

## 前置依赖

1. Python 3.10+：`pip install feedparser requests`（第 0 步会自检）
2. 飞书落地（第 3 步分支 A）需 lark-cli：`npx @larksuite/cli@latest install`（需 Node.js）

## 信息源清单（sources.json，可增删）

| 源 | 方式 | 网络 |
|---|---|---|
| OpenAI 官方新闻 | RSS | 代理 |
| Google DeepMind 博客 | RSS | 代理 |
| Anthropic 新闻 | sitemap（官方无 RSS） | 代理 |
| Hugging Face 博客 | RSS | 代理 |
| TechCrunch AI | RSS | 代理 |
| The Verge AI | RSS | 代理 |
| MIT Tech Review AI | RSS | 代理 |
| Hacker News AI 热帖 | Algolia API（时间窗+票数+词边界过滤） | 直连 |
| InfoQ 中文 | RSS（AI 相关由第 2 步筛） | 直连 |
| arXiv cs.AI | arXiv API | 代理 |
| arXiv cs.CL | arXiv API | 代理 |

失效处理：RSS 地址变更时先 curl 验证再更新 sources.json；机器之心/量子位（免费接口关闭）、xAI/Stability（反爬与导航页噪音）均已不可用，不要浪费时间重试。

## 定时执行

技能无状态，任意调度器可调。推荐每天 08:00（Asia/Shanghai）。各宿主配置方式见仓库 `docs/scheduling.md`，prompt 模板就是一句话："按 ai-news 技能完整执行今日 AI 日报流程"。
