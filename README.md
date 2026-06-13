# wechat-article-reader

Cursor/Codex Agent Skill — 微信公众号文章读取器。

当用户提供 `mp.weixin.qq.com` 文章链接时，自动抓取并返回结构化解析结果（标题、作者、发布时间、正文）。当用户要求“关注这个号”或“持续监测作者”时，skill 会使用内置的 `wechat-download-api` 服务加入关注池。

## 安装

推荐：

```bash
npm i -g skills
npx skills add wang1733238039/wechat-article-reader@master -g -y
```

兼容旧命令：

```bash
npx skills add wang1733238039/wechat-article-reader@wechat-article-reader -g -y
```

> 安装后需要重启 Codex/Cursor Agent，新的 skill 才会被加载。

## 无 Git 环境

`npx skills add` 在部分系统上会调用 `git`。如果报 `spawn git ENOENT`，请先安装 Git for Windows，并确认 `git.exe` 在 PATH 中：

https://git-scm.com/download/win

如果网络无法下载 GitHub ZIP，也需要先修复网络/代理后再安装。这个 skill 已把关注作者所需的 `wechat-download-api` 精简服务源码打包在 `skills/wechat-article-reader/service/`，不需要用户另外提供源码。

## 使用

```bash
uv run python skills/wechat-article-reader/scripts/read_wechat_article.py "https://mp.weixin.qq.com/s/..."
```

依赖：
- Python 3.10+
- uv
- curl-cffi
- BeautifulSoup4

## 输出约定

- 成功时面向用户输出摘要，不默认粘贴完整 JSON。
- 失败时保留关键原始错误字段，方便排查。
- 列出文章时必须附带文章链接，方便用户直接点击。
