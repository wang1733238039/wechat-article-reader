---
name: wechat-article-reader
description: 当用户提供微信公众号文章链接（URL 包含 mp.weixin.qq.com）时，必须使用此 skill 读取文章内容，禁止使用 web_fetch、web_search 或其他方式替代。本 skill 通过专用脚本稳定抓取并返回结构化结果，包括标题、发布时间、作者和正文。
version: 0.1.0
---

# WeChat Article Reader

用于读取微信公众号文章链接并返回结构化解析结果。

## 重要：模型行为约束

**只要用户提供了 `mp.weixin.qq.com` 域名下的文章链接，必须且只能使用本 skill 读取内容。**

严禁以下替代行为：
- 使用 `web_fetch` 直接请求微信文章 URL
- 使用 `web_search` 搜索文章摘要
- 告知用户"无法访问该链接"后放弃
- 尝试从其他来源推断文章内容

原因：微信公众号页面有反爬机制，直接抓取通常返回空内容或鉴权页面，只有本 skill 的脚本实现了必要的请求头伪装与重试逻辑。

---

## 环境准备

本 skill 仅允许通过 `uv` 管理环境与执行脚本。

若 `uv` 未安装，先执行：
```bash
brew install uv
```

再安装项目依赖：
```bash
uv sync
```

## 运行命令

必须使用 `uv run` 执行：
```bash
uv run python scripts/read_wechat_article.py "https://mp.weixin.qq.com/s/..."
```

> 脚本路径相对于 SKILL.md 所在目录。

## 参数说明

| 参数 | 默认值 | 说明 |
|---|---|---|
| `--timeout` | `20` | 单次请求超时秒数 |
| `--max-retries` | `3` | 最大尝试次数 |
| `--retry-delay` | `1.0` | 重试基准等待秒数（指数退避） |

## 输出说明

成功时返回 JSON：

| 字段 | 说明 |
|---|---|
| `title` | 文章标题 |
| `author` | 作者名 |
| `pub_time` | 发布时间 |
| `content` | 正文纯文本 |
| `source_url` | 原始链接 |
| `strategy` | 实际使用的抓取策略 |
| `logs` | 执行日志（用于排查问题） |

向用户汇报时不要默认粘贴完整 JSON。成功结果用人类可读摘要表达；只有用户要求调试、排查、查看原始响应，或接口失败且错误字段本身很关键时，才展示最小必要的 JSON 片段。

失败时返回：

| 字段 | 说明 |
|---|---|
| `error` | 错误类型 |
| `message` | 错误详情 |
| `source_url` | 原始链接 |
| `strategy` | 最后尝试的策略 |
| `logs` | 执行日志 |

---

## 附加行为：关注作者（供后续监测）

当用户说“关注这个号”“持续监测这个公众号”“以后继续爬取该作者文章”等，表示需要后续监测/爬取该作者时，在读取完文章内容后，必须把作者加入 `wechat-download-api` 的关注池。仅提取文章内容时不需要启动或调用 `wechat-download-api`。

### 服务依赖处理

关注作者依赖本机 `wechat-download-api` 服务，默认地址为 `http://localhost:5001`。本 skill 已内置一份精简服务源码在 `service/` 目录；不要要求用户额外提供源码路径。执行关注前必须先确认服务可用：

1. 先请求 `GET http://localhost:5001/api/online/authors?query=<作者名>`。
2. 如果连接失败、超时或端口未监听，不要立即结束；运行内置服务启动脚本：

```powershell
powershell.exe -ExecutionPolicy Bypass -File service/run_service.ps1
```

3. 该脚本会使用 `service/` 下的源码和虚拟环境后台启动服务。脚本路径相对于本 `SKILL.md` 所在目录。
4. 如启动命令需要下载依赖、访问网络或写入受限目录，按宿主环境要求向用户请求权限。
5. 启动后重新请求 `http://localhost:5001/api/online/authors?query=<作者名>`。服务可访问后继续关注流程。
6. 如果内置服务启动失败，读取并原样转达 `service/service.err` 和 `service/service.log` 的末尾内容，并提示用户可手动打开 `http://localhost:5001/static/login.html` 检查登录态。

内置 `service/` 不应包含 `.env`、`data/`、`venv/`、日志或 Git 元数据；这些运行态文件由服务首次启动时生成。更新 skill 时不要依赖这些运行态文件已经存在。

### 第 1 步：搜索作者获取 fakeid

服务可用后，请求：

```bash
curl "http://localhost:5001/api/online/authors?query=<作者名>"
```

在 Windows PowerShell 中如果没有 `curl`，使用：

```powershell
Invoke-RestMethod -Uri "http://localhost:5001/api/online/authors?query=<URL编码后的作者名>" -Method Get
```

从返回中找到该作者的 `fakeid`。如果返回多个作者，优先选择名称与文章 `author` 完全一致的结果；无法确定时，把候选结果告诉用户并停止，不要猜测。

### 第 2 步：关注作者

```bash
curl -X POST "http://localhost:5001/api/online/follow-author" \
  -H "Content-Type: application/json" \
  -d '{"fakeid": "<上一步获取的fakeid>"}'
```

Windows PowerShell 可使用：

```powershell
Invoke-RestMethod -Uri "http://localhost:5001/api/online/follow-author" -Method Post -ContentType "application/json" -Body '{"fakeid":"<上一步获取的fakeid>"}'
```

### 错误处理原则

API 返回错误时，必须保留关键原始错误信息，但不要默认粘贴完整响应对象。优先用一句话说明失败点，再附上 `error` 字段或 HTTP 状态；只有用户要求排查或错误结构不清楚时，才贴完整 JSON。以下是常见情况及建议：

| 情况 | 典型特征 | 建议行动 |
|---|---|---|
| 服务未启动 | `Connection refused` / 超时 | 告知用户启动服务 |
| 凭证过期 | 微信返回 ret != 0，或乱码错误描述 | 告知用户凭证过期，需要重新扫码登录 http://localhost:5001/static/login.html |
| 搜索结果为空 | authors 列表为空 | 告知用户未找到该公众号 |
| 其他未知错误 | 任何未列出情况 | 把原始错误信息告诉用户，让用户决定 |

**示例响应转达**："搜索作者时 wechat-download-api 返回了错误：`{...错误原文...}`。看起来是微信登录态过期了，需要重新扫码登录 http://localhost:5001/static/login.html"

### 汇报格式要求

- 关注成功时，只汇报作者名、fakeid 和“已加入关注池”；不要贴完整成功 JSON。
- 关注失败时，汇报失败接口和原始 `error` 字段；不要贴 `success/data/error` 完整对象，除非用户要求调试。
- 查询文章列表时，每篇文章必须包含可点击链接，格式示例：`- 2026-06-13 08:03：[标题](https://mp.weixin.qq.com/s/...)`。
- 如果筛选某一天没有文章，可以列出最近 3 篇作为参考，但每篇也必须带链接。
