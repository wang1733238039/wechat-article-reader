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

如果用户表示后续要**持续监测/爬取该作者的文章**，则在读取完文章内容后，**必须**自动完成以下两步，将作者加入关注池：

### 第 1 步：搜索作者获取 fakeid

```bash
curl "http://localhost:5001/api/online/authors?query=<作者名>"
```

从返回中找到该作者的 `fakeid`。

### 第 2 步：关注作者

```bash
curl -X POST "http://localhost:5001/api/online/follow-author" \
  -H "Content-Type: application/json" \
  -d '{"fakeid": "<上一步获取的fakeid>"}'
```

### 第 2 步：关注作者

```bash
curl -X POST "http://localhost:5001/api/online/follow-author" \
  -H "Content-Type: application/json" \
  -d '{"fakeid": "<上一步获取的fakeid>"}'
```

### 错误处理原则

API 返回的任何错误信息（无论是 HTTP 状态码、错误描述还是微信后端报错），**原样转达给用户，不要自己解读或省略**。以下是常见情况及建议：

| 情况 | 典型特征 | 建议行动 |
|---|---|---|
| 服务未启动 | `Connection refused` / 超时 | 告知用户启动服务 |
| 凭证过期 | 微信返回 ret != 0，或乱码错误描述 | 告知用户凭证过期，需要重新扫码登录 http://localhost:5001/static/login.html |
| 搜索结果为空 | authors 列表为空 | 告知用户未找到该公众号 |
| 其他未知错误 | 任何未列出情况 | 把原始错误信息告诉用户，让用户决定 |

**示例响应转达**："搜索作者时 wechat-download-api 返回了错误：`{...错误原文...}`。看起来是微信登录态过期了，需要重新扫码登录 http://localhost:5001/static/login.html"
