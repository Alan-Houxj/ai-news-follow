# 定时自动化指南

> **读完后你将获得**：每天早上 8 点，无需任何手动操作，日报自动写入表格、推送到飞书私聊、归档到云文档。
>
> **前提**：已完成 [setup.md](setup.md)（飞书落地配置已跑通）。
>
> 本技能无状态、无守护进程，任何调度器都能驱动它。下面是三种常见方式，先看选型表再挑一种照做。

## 先选型

| | 方式一：Agent 内定时 | 方式二：GitHub Actions | 方式三：系统 cron |
|---|---|---|---|
| 电脑需要开机吗 | ✅ 需要 | ❌ 不需要（云端跑） | ✅ 需要 |
| 谁来做"筛选摘要" | 你的 Agent（自带 LLM）✅ | 需要额外接 LLM API ⚠️ | 需要能唤起 Agent ⚠️ |
| 配置难度 | ⭐ 一句话 | ⭐⭐ 加一个 yml + 几个 Secrets | ⭐⭐ 写一行 crontab |
| 适合谁 | 电脑常开、已在用某个 AI Agent | 不想开机、有 GitHub 账号 | 有服务器 / 常开机器 |

> **一个关键认知**：每日流程里的"筛选摘要、写当日总评"是 LLM 的活。Agent 内定时天然带着 LLM；另外两种方式需要你自己解决这一环（各自章节里给了办法）。

---

## 方式一：在你的 Agent 里设定时任务（推荐，最省事）

主流 AI Agent 都带定时能力（Claude Code 的 scheduled tasks、ZCode 的定时任务、其他 Agent 的 cron 集成等），做法都是一句话——**设一个每天 8 点的任务，触发内容就是**：

> 按 ai-news 技能完整执行今日 AI 日报流程。

具体在哪个菜单、怎么设，随你的 Agent 略有不同。直接对你的 Agent 说一句"帮我设一个每天早上 8 点跑 AI 日报的定时任务"即可，它会替你配好。

如需一份可复制的触发语，用 [examples/cron-prompt.txt](../examples/cron-prompt.txt) 模板——开箱即用，唯一可能需改的是 lark-cli 非标准安装时的 `LARK_CLI` 路径。

**怎么验证**：创建后等第二天 8 点看飞书；或先让 Agent"立即执行一次这个流程"确认跑通。
**管理**：之后想改时间 / 暂停，直接对 Agent 说"把 AI 日报定时任务改成 9 点 / 暂停"。

---

## 方式二：GitHub Actions（电脑不开机）

**适合**：有 GitHub 账号、希望完全托管在云端的人。

### 第 1 小步：推送仓库到 GitHub

```bash
git init && git add -A && git commit -m "init"
gh repo create ai-news-follow --private --source . --push
```

### 第 2 小步：配置 Secrets

仓库页面 → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**，逐个添加：

| Secret 名 | 值 |
|---|---|
| `FEISHU_APP_ID` | 飞书应用 App ID（setup 第 2 步） |
| `FEISHU_APP_SECRET` | 飞书应用 App Secret |
| `FEISHU_BASE_TOKEN` | config.json 里的 base_token |
| `FEISHU_TABLE_ID` | config.json 里的 table_id |
| `FEISHU_USER_OPEN_ID` | config.json 里的 user_open_id |
| `FEISHU_BASE_URL` | config.json 里的 base_url（表格完整链接） |

### 第 3 小步：创建工作流文件

新建 `.github/workflows/daily.yml`，内容如下（可直接复制）：

```yaml
name: ai-news-daily
on:
  schedule:
    - cron: "0 0 * * *"    # UTC 0 点 = 北京时间 8 点
  workflow_dispatch:         # 允许手动触发，方便测试
permissions: write-all
jobs:
  run:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: 20 }
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install feedparser requests
      - run: npm install -g @larksuite/cli@latest
      - name: 绑定飞书应用
        env:
          APP_ID: ${{ secrets.FEISHU_APP_ID }}
          APP_SECRET: ${{ secrets.FEISHU_APP_SECRET }}
        run: printf '%s' "$APP_SECRET" | lark-cli config init --app-id "$APP_ID" --app-secret-stdin --brand feishu
      - name: 采集
        run: python skills/ai-news/scripts/fetch_sources.py --hours 26
      - name: 直通写表（无 LLM 筛选的降级模式）
        env:
          FEISHU_BASE_TOKEN: ${{ secrets.FEISHU_BASE_TOKEN }}
          FEISHU_TABLE_ID: ${{ secrets.FEISHU_TABLE_ID }}
          FEISHU_USER_OPEN_ID: ${{ secrets.FEISHU_USER_OPEN_ID }}
          FEISHU_BASE_URL: ${{ secrets.FEISHU_BASE_URL }}
        run: |
          # 把采集结果直接透传为 curated（标题即摘要，无 LLM 筛选）
          python - <<'PY'
          import json
          d = json.load(open('skills/ai-news/scripts/items.json', encoding='utf-8'))
          items = [{'title': it['title'], 'summary': it['title'], 'url': it['url'],
                    'source': it['source'], 'category': it['category'],
                    'importance': '中', 'tags': [], 'published': it.get('published')}
                   for it in d['items']]
          json.dump({'digest': None, 'items': items},
                    open('skills/ai-news/scripts/curated.json', 'w', encoding='utf-8'),
                    ensure_ascii=False)
          PY
          python skills/ai-news/scripts/run_daily.py skills/ai-news/scripts/curated.json
```

**⚠️ 注意**：上面的 yml 是**无 LLM 的直通模式**——条目不经筛选摘要直接写表（条数等于采集数，可能较多）。要完整体验（去噪、摘要、当日总评），在"采集"和"落地"之间加一步调用 LLM API 生成 selection.json，再执行 make_curated.py。

**怎么验证**：仓库 Actions 页 → 选 `ai-news-daily` → **Run workflow** 手动跑一次，看日志和飞书。

---

## 方式三：系统 cron（有服务器 / 常开机器）

**适合**：习惯命令行、有 Linux/macOS 常开机器的人。

```bash
crontab -e
```

加一行（把路径换成你的实际路径；环境变量即 config.json 的外置版）：

```cron
0 8 * * * cd /path/to/ai-news-follow/skills/ai-news/scripts && \
  LARK_CLI=/usr/local/bin/lark-cli \
  FEISHU_BASE_TOKEN=xxx FEISHU_TABLE_ID=xxx FEISHU_USER_OPEN_ID=xxx FEISHU_BASE_URL=https://xxx.feishu.cn/base/xxx \
  python3 fetch_sources.py --hours 26 && \
  python3 make_curated.py && \
  python3 run_daily.py curated.json >> daily.log 2>&1
```

**⚠️ 与方式二同样的注意**：纯 cron 没有 LLM。解法：
- 让 cron 唤起一个有 LLM 的无头 Agent（如 `zcode -p "按 examples/cron-prompt.txt 执行"` 之类，取决于你的 Agent CLI）
- 或接受"无摘要直通写表"的降级模式

**怎么验证**：先把 cron 表达式临时改成 `*/2 * * * *`（每 2 分钟）看 `daily.log` 有没有正常产出，调通后改回 `0 8 * * *`。

---

## 改推送时间

三种方式分别改：Agent 里对 Agent 说改时间；yml 里的 `cron` 值（注意是 UTC，北京时间减 8 小时）；crontab 第一列。工作日推送等进阶玩法同理。
