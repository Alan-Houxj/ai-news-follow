# 飞书落地配置指南

> **读完后你将获得**：技能每天把日报写进你自己的飞书多维表格、机器人私聊推送消息卡片、云文档时间线归档。
>
> **你需要准备**：一台电脑、一个飞书账号（个人版即可）、约 5 分钟。
>
> 推荐方式是**全程在对话里完成**：你对 Agent 说一句话，Agent 带你点两次浏览器，其余全自动。

---

## 方式一：对话内配置（推荐）

前置：Agent 里已装好本 Skill，且电脑上有 Python 3.10+、Node.js 18+（装过 lark-cli 的环境两者都已就绪）。

直接对 Agent 说：

> 把日报接入我的飞书

Agent 会按 SKILL.md 的"首次配置引导"依次执行：

1. 发给你一个**创建应用的链接** → 浏览器打开、点一次确认（应用与凭证自动创建保存）
2. 发给你一个**授权二维码** → 飞书扫码确认（所需权限自动申请自动审批）
3. 自动建表「AI资讯库 / AI日报」（8 字段、选项全预置）→ 把应用授权进表 → 建归档文档 → 写 `config.json`
4. 给你的飞书发一条测试消息

收到测试消息即配置完成。之后对 Agent 说"跑今天的 AI 日报"，日报就会同时写表、推送、归档。

## 方式二：终端手动配置（兜底）

Agent 无法执行命令、或你想自己控制每一步时，按顺序执行以下命令。

**① 绑定或创建应用**（二选一）：

```bash
# 没有应用：一键创建（浏览器点一次确认，凭证自动保存）
lark-cli config init --new

# 已有应用：手动绑定（App Secret 走 stdin）
printf '%s' "<AppSecret>" | lark-cli config init --app-id <AppID> --app-secret-stdin --brand feishu
```

**② 用户授权**（扫码，所需权限自动申请自动审批；已有应用若权限不全，报错里会带预填申请链接，点开通后重跑）：

```bash
lark-cli auth login --recommend
```

**③ 建表**（以你自己的身份，表归你所有；整条复制执行）：

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

**④ 把应用授权进表**（技能写入记录走 bot 身份，需要这一步；`--member-id` 填你的 App ID）：

```bash
lark-cli drive +member-add --token <base_token> --type bitable   --member-type appid --member-id <AppID> --perm full_access --as user --yes
```

> ⚠️ 不要用 `--as bot` 给别人授权——新建应用缺 drive 系 bot 权限且需发版生效，会报 1063003。
> 也不要漏掉这一步——表是你建的，应用看不到它，写入会报错。

**⑤ 建归档文档**（可选，不要归档功能可跳过）：

```bash
lark-cli docs +create --title "AI 日报归档"   --content "本文档由 ai-news 技能每日自动维护：最新日报始终在最上方。"   --doc-format markdown --as user

# 取"说明段落"的块 id 作为插入锚点（<p id="这里就是锚点">本文档由 ai-news...）：
lark-cli docs +fetch --doc <文档token> --detail with-ids --as user
```

**⑥ 写配置文件**：

```bash
cd skills/ai-news/scripts
cp config.example.json config.json
```

按 `config.example.json` 内的注释逐项填写，值的来源对照：

| 配置项 | 哪里来 |
|---|---|
| `base_token` | 表格网址 `.../base/` 后、`?table=` 前那串 |
| `table_id` | 表格网址 `?table=` 后那串（tbl 开头） |
| `user_open_id` | `lark-cli auth status` 输出里的 ou_ 字符串 |
| `base_url` | 表格页面地址栏完整复制 |
| `archive_doc_id` / `archive_anchor_block` | 步骤 ⑤（可选） |

**⑦ 验证**：对 Agent 说"跑今天的 AI 日报"，表格、推送、归档三处应同时更新。

---

## 常见问题

出问题先查 [faq.md](faq.md)。配置相关的问题修好后重跑即可，已建成的资源不会冲突。
