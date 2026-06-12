# wechat-article-reader

Cursor Agent Skill — 微信公众号文章读取器。

当用户提供 `mp.weixin.qq.com` 文章链接时，自动抓取并返回结构化的解析结果（标题、作者、发布时间、正文）。

## 安装

```bash
npm i -g skills
npx skills add wang1733238039/wechat-article-reader@wechat-article-reader -g -y
```

## 本地开发

```bash
git clone https://github.com/wang1733238039/wechat-article-reader.git
cd wechat-article-reader
uv sync
```

## 使用

```bash
uv run python skills/wechat-article-reader/scripts/read_wechat_article.py "https://mp.weixin.qq.com/s/..."
```

- Python 3.10+
- [curl-cffi](https://github.com/IFE-TEAM/curl-cffi) — 浏览器指纹请求
- BeautifulSoup4 — HTML 解析
