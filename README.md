# wechat-article-reader

Cursor Agent Skill — 微信公众号文章读取器。

当用户提供 `mp.weixin.qq.com` 文章链接时，自动抓取并返回结构化的解析结果（标题、作者、发布时间、正文）。

## 安装

### 1. 克隆仓库

```bash
git clone https://github.com/wang1733238039/wechat-article-reader.git
cd wechat-article-reader
```

### 2. 安装 uv（如未安装）

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### 3. 安装依赖

```bash
uv sync
```

## 使用

```bash
uv run python scripts/read_wechat_article.py "https://mp.weixin.qq.com/s/..."
```

### 参数

| 参数 | 默认值 | 说明 |
|---|---|---|
| `--timeout` | 20 | 单次请求超时秒数 |
| `--max-retries` | 3 | 最大尝试次数 |
| `--retry-delay` | 1.0 | 重试等待秒数（指数退避）|

### 输出示例

```json
{
  "title": "文章标题",
  "author": "作者名",
  "pub_time": "2024-01-01T12:00:00+00:00",
  "content": "正文内容...",
  "source_url": "https://mp.weixin.qq.com/s/...",
  "strategy": "curl_cffi",
  "logs": { "http_status": 200, "attempts": [...] }
}
```

## Cursor Agent 集成

在 Cursor Agent 的 skill 配置中添加本仓库路径，Agent 会自动识别 `mp.weixin.qq.com` 链接并调用本 skill。

## 技术栈

- Python 3.10+
- [curl-cffi](https://github.com/IFE-TEAM/curl-cffi) — 浏览器指纹请求
- BeautifulSoup4 — HTML 解析
