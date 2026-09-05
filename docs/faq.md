# 常见问题（FAQ）

> 遇到问题先看这里——按症状对号入座。配置类问题大多可以在对话里让 Agent 重新执行"首次配置引导"解决（幂等，已建成的资源不受影响）。
> 还解决不了？把报错信息完整发给你的 Agent，让它对照本文件排查。

## 快速索引

| 你看到的症状 | 跳转 |
|---|---|
| 表格记录只有日期，其他全空 | [#1](#1-表格记录只有日期其他全空) |
| 写入报 option not_found | [#2](#2-写入报-option_not_found) |
| Bot ability is not activated | [#3](#3-bot-ability-is-not-activated) |
| app_scope_not_applied / 开权限失败 | [#4](#4-app_scope_not_applied-或开权限弹窗报错) |
| Python 找不到 lark-cli（WinError 2）| [#5](#5-python-找不到-lark-cli-winerror-2) |
| 海外源全挂 / TLS connect error | [#6](#6-海外源全部失败--tls-connect-error) |
| arXiv 502 | [#7](#7-arxiv-偶发-502) |
| 归档文档插入/删除报错 | [#8](#8-云文档归档操作报错) |
| 表格推送正常，云文档归档突然失败 | [#9](#9-表格推送正常云文档归档突然失败) |
| 授权协作者报 1063003 Invalid operation | [#10](#10-授权协作者报-1063003-invalid-operation) |

---

## 1. 表格记录只有日期，其他全空

**原因**：写入的数据没到飞书。两种可能——
a) curated.json 的字段键与脚本映射不匹配（正常不会发生，除非你改过生成逻辑）；
b) **Windows 高发**：Python 通过 `.cmd` 垫片调用 lark-cli，中文参数被 GBK 编码破坏，飞书静默丢弃了损坏字段。

**解决**：不要经过 `.cmd` 垫片，让脚本直接调用真实程序：

```bash
export LARK_CLI="C:\Users\<你>\AppData\Roaming\npm\node_modules\@larksuite\cli\bin\lark-cli.exe"
```

验证方法：`python run_daily.py curated.json --dry-run`，第一行能正确打印中文标题就是通的。

## 2. 写入报 option not_found

**原因**：单选/多选字段写入了不在预置选项里的值。飞书的选项字段不接受"随便的新词"。

**解决**：
- "来源/分类/重要度"三个字段：按 [setup.md](setup.md) 第 ③ 步的建表命令预置选项（命令里已带）
- "标签"字段：无需处理——脚本每次写入前会自动把新标签合并进选项池
- 自己加了新选项字段：参考 `run_daily.py` 里的 `ensure_tag_options`，或手动去表格界面把选项加上

## 3. Bot ability is not activated

**原因**：应用没开"机器人"能力，发消息的通道不存在。

**解决**：开发者后台 → 你的应用 → **添加应用能力** → 机器人卡片点 **添加** → **创建版本并发布**。发布后生效。

## 4. app_scope_not_applied 或开权限弹窗报错

**原因分三种**：
- 应用还没发布过任何版本 → 先去 **版本管理与发布** 发布一版（见 setup.md 第 ② 步）
- 申请了聚合权限 `im:message`，它捆绑"读全部群消息"等敏感子权限，个人账号开不了，整单失败 → 改用细粒度的 `im:message:send_as_bot`
- 权限开通了但没发新版 → 再发布一版

**最省事的做法**：跑 `lark-cli auth scopes`，报错信息里有预填好权限的申请链接（console_url），打开点开通，循环到 ok 为止。

## 5. Python 找不到 lark-cli（WinError 2）

**原因**：Windows 上 npm 安装的是 `.cmd` 垫片脚本，Python 的 subprocess 不能直接执行。

**解决**：`export LARK_CLI=<lark-cli.exe 完整路径>`。路径通常是：

```
C:\Users\<你>\AppData\Roaming\npm\node_modules\@larksuite\cli\bin\lark-cli.exe
```

## 6. 海外源全部失败 / TLS connect error

**原因**：国内网络直连 OpenAI/DeepMind/Anthropic/arXiv 不通，需要代理。

**解决**：

```bash
export HTTPS_PROXY=http://127.0.0.1:7897   # 换成你的代理端口
```

中文源（InfoQ、Hacker News）强制直连，不受影响；反过来，如果你全局挂了代理导致中文源反而失败，脚本对中文源已做直连保护，一般无需处理。git push 失败（Connection reset）通常也是同一原因。

## 7. arXiv 偶发 502

**现象**：采集日志里 `[fail] arxiv_xxx: 502 Server Error`。

**说明**：arXiv 官方 API 的正常抖动。脚本会重试 3 次后跳过，并在 items.json 的 errors 里记录，不影响其他源和整体流程。第二天通常自愈，无需处理。

## 8. 云文档归档操作报错

- **插入报层级/结构错误**：归档文档的头部结构被手动改过。按 setup.md 第 ⑤ 步的方式重建一篇，更新 config.json 的两个归档配置项
- **删除块报 "no document changes"**：传了截断的 block id（要用完整 id），或选中的范围里包含没有独立 id 的中间块。单块操作时先 `+fetch --detail with-ids` 拿完整 id

## 9. 表格推送正常，云文档归档突然失败

**原因**：归档用的是你本人的用户身份（user token），有效期约 30 天，过期后机器人侧的表格/推送不受影响，但归档会开始报权限错。

**解决**：重新授权一次即可，秒级完成：

```bash
lark-cli auth login --recommend
```

按提示扫码确认，第二天的归档自动恢复。

## 10. 授权协作者报 1063003 Invalid operation

**原因**：`drive +member-add` 以 bot 身份执行时，新应用缺 drive 系 bot 权限，且需发布新版本才生效。

**解决**：换 user 身份执行（用户对自己建的文档天然有管理权），member-type 用 appid 授权给应用：

```bash
lark-cli drive +member-add --token <base_token> --type bitable   --member-type appid --member-id <AppID> --perm full_access --as user --yes
```

**更推荐**：建表时就 `--as user`（表归用户所有），再把应用授权进表，一次到位。

---

## 想调整信息源？

编辑 `skills/ai-news/scripts/sources.json`，每个源两个关键属性：`url`（抓取地址）和 `network`（`proxy` 走代理 / `direct` 直连）。加新源照着现有条目写即可。

⚠️ 机器之心、量子位的免费接口已关闭（RSS 和 API 都跳转产品页），不要浪费时间尝试。

## 想换表格 / 换归档文档 / 换推送对象？

改 `skills/ai-news/scripts/config.json` 对应字段即可，不用动代码。每个字段去哪拿值，看 `config.example.json` 里的注释。
