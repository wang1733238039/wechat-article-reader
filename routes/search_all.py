#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (C) 2026 wang1733238039
# Licensed under the GNU Affero General Public License v3.0
# See LICENSE file in the project root for full license text.
# SPDX-License-Identifier: AGPL-3.0-only
"""
微信搜一搜 - 全网关键词文章搜索
通过 searchbiz 发现公众号，再逐个调用 appmsgpublish 搜文章，
最后合并去重、按时间排序返回。
"""

import asyncio
import json
import logging
import time
import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import httpx
from fastapi import APIRouter, Query, Request
from pydantic import BaseModel

from utils.auth_manager import auth_manager
from utils.image_proxy import proxy_image_url

logger = logging.getLogger(__name__)

router = APIRouter()

WECHAT_SEARCH_BIZ_URL = "https://mp.weixin.qq.com/cgi-bin/searchbiz"
WECHAT_APPMSGPUBLISH_URL = "https://mp.weixin.qq.com/cgi-bin/appmsgpublish"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


class ArticleResult(BaseModel):
    aid: str = ""
    title: str = ""
    link: str = ""
    digest: str = ""
    cover: str = ""
    author_name: str = ""
    update_time: int = 0
    create_time: int = 0
    fakeid: str = ""
    source: str = ""
    alias: str = ""


class SearchAllResponse(BaseModel):
    success: bool
    data: Optional[Dict] = None
    error: Optional[str] = None


def get_base_url(request: Optional[Request]) -> str:
    if not request:
        return ""
    proto = request.headers.get("X-Forwarded-Proto", "http")
    host = request.headers.get("X-Forwarded-Host") or request.headers.get("Host", "localhost:5001")
    return f"{proto}://{host}"


def get_credentials() -> Tuple[Optional[str], Optional[str], Optional[str]]:
    creds = auth_manager.get_credentials()
    if not creds:
        return None, None, "服务器未登录，请先扫码登录"
    token = creds.get("token")
    cookie = creds.get("cookie")
    if not token or not cookie:
        return None, None, "登录信息不完整，请重新扫码登录"
    return token, cookie, None


def wechat_headers(cookie: str) -> Dict[str, str]:
    return {
        "Cookie": cookie,
        "User-Agent": USER_AGENT,
        "Referer": "https://mp.weixin.qq.com/",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }


def parse_publish_page(result: Dict) -> Tuple[List[Dict], int]:
    publish_page = result.get("publish_page", {})
    if isinstance(publish_page, str):
        try:
            publish_page = json.loads(publish_page or "{}")
        except (json.JSONDecodeError, ValueError):
            return [], 0
    if not isinstance(publish_page, dict):
        return [], 0

    articles = []
    for item in publish_page.get("publish_list", []):
        publish_info = item.get("publish_info", {})
        if isinstance(publish_info, str):
            try:
                publish_info = json.loads(publish_info or "{}")
            except (json.JSONDecodeError, ValueError):
                continue
        if not isinstance(publish_info, dict):
            continue

        for article in publish_info.get("appmsgex", []):
            articles.append({
                "aid": article.get("aid", ""),
                "title": article.get("title", ""),
                "link": article.get("link", ""),
                "digest": article.get("digest", ""),
                "cover": article.get("cover", ""),
                "author_name": article.get("author_name", ""),
                "update_time": article.get("update_time", 0),
                "create_time": article.get("create_time", 0),
            })

    return articles, int(publish_page.get("total_count") or len(articles))


def strip_highlight(html: str) -> str:
    """去掉 <em class="highlight"> 标签，保留内容"""
    if not html:
        return ""
    return re.sub(r'<em[^>]*class="highlight"[^>]*>(.*?)</em>', r'\1', html)


def format_wechat_error(base_resp: Dict) -> str:
    ret_code = base_resp.get("ret")
    err_msg = base_resp.get("err_msg", "未知错误")
    if ret_code == 200003 or "login" in str(err_msg).lower():
        return "登录已过期或需要重新扫码登录"
    if ret_code == 200002:
        return "公众号可能已注销、改名或 fakeid 失效"
    return f"微信接口错误: ret={ret_code}, msg={err_msg}"


async def search_wechat_accounts(
    keyword: str,
    cookie: str,
    token: str,
    count: int = 20,
) -> Tuple[bool, List[Dict], Optional[str]]:
    """通过 searchbiz 搜索公众号列表"""
    params = {
        "action": "search_biz",
        "token": token,
        "lang": "zh_CN",
        "f": "json",
        "ajax": 1,
        "random": time.time(),
        "query": keyword,
        "begin": 0,
        "count": count,
    }

    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            response = await client.get(
                WECHAT_SEARCH_BIZ_URL,
                params=params,
                headers=wechat_headers(cookie),
            )
            response.raise_for_status()
            result = response.json()
    except httpx.HTTPStatusError as e:
        return False, [], f"HTTP错误 {e.response.status_code}"
    except Exception as exc:
        return False, [], f"搜索公众号失败: {exc}"

    base_resp = result.get("base_resp", {})
    if base_resp.get("ret") != 0:
        return False, [], format_wechat_error(base_resp)

    accounts = result.get("list", [])
    authors = []
    for account in accounts:
        fakeid = account.get("fakeid", "")
        if not fakeid:
            continue
        authors.append({
            "fakeid": fakeid,
            "nickname": account.get("nickname", ""),
            "alias": account.get("alias", ""),
            "username": account.get("username", ""),
            "round_head_img": account.get("round_head_img", ""),
            "service_type": account.get("service_type", 0),
            "signature": account.get("signature", ""),
        })

    return True, authors, None


async def search_articles_for_account(
    author: Dict,
    keyword: str,
    cookie: str,
    token: str,
    begin: int,
    count: int,
    search_field: int = 7,
) -> Tuple[List[Dict], int, Optional[str]]:
    """在指定公众号内按关键词搜索文章"""
    params = {
        "sub": "search",
        "search_field": search_field,
        "begin": begin,
        "count": count,
        "query": keyword,
        "fakeid": author["fakeid"],
        "type": "101_1",
        "free_publish_type": 1,
        "sub_action": "list_ex",
        "token": token,
        "lang": "zh_CN",
        "f": "json",
        "ajax": 1,
    }

    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.get(
                WECHAT_APPMSGPUBLISH_URL,
                params=params,
                headers=wechat_headers(cookie),
            )
            response.raise_for_status()
            result = response.json()
    except httpx.HTTPStatusError as e:
        return [], 0, f"HTTP错误 {e.response.status_code}"
    except Exception as exc:
        return [], 0, f"获取文章失败: {exc}"

    base_resp = result.get("base_resp", {})
    if base_resp.get("ret") != 0:
        return [], 0, f"{author.get('nickname') or author['fakeid']}: {format_wechat_error(base_resp)}"

    articles, total = parse_publish_page(result)

    enriched = []
    for article in articles:
        enriched.append({
            **article,
            "fakeid": author["fakeid"],
            "source": author.get("nickname") or author["fakeid"],
            "alias": author.get("alias", ""),
        })

    return enriched, total, None


def dedupe_articles(articles: List[Dict]) -> List[Dict]:
    seen = set()
    unique = []
    for article in articles:
        key = article.get("link") or f"{article.get('fakeid')}:{article.get('aid')}"
        if key in seen:
            continue
        seen.add(key)
        unique.append(article)
    return unique


@router.get("/search-all/articles", response_model=SearchAllResponse, summary="微信搜一搜 - 全网关键词文章搜索")
async def search_all_articles(
    keyword: str = Query(..., description="文章关键词", min_length=1, max_length=100),
    max_accounts: int = Query(10, ge=1, le=20, description="最多搜索多少个公众号"),
    articles_per_account: int = Query(5, ge=1, le=20, description="每个公众号最多返回文章数"),
    request: Request = None,
):
    """
    微信搜一搜：输入关键词，搜索全网公众号文章。

    工作流程：
    1. 通过 searchbiz 接口搜索包含该关键词的公众号列表
    2. 并行对每个公众号调用 appmsgpublish 搜索文章
    3. 合并所有结果，去重并按时间排序

    注意：需要已登录微信后台才能使用。
    """
    token, cookie, error = get_credentials()
    if error:
        return SearchAllResponse(success=False, error=error)

    base_url = get_base_url(request)

    # Step 1: 搜索公众号
    ok, authors, search_err = await search_wechat_accounts(
        keyword=keyword,
        cookie=cookie,
        token=token,
        count=max_accounts,
    )
    if not ok:
        return SearchAllResponse(success=False, error=search_err)

    if not authors:
        return SearchAllResponse(
            success=True,
            data={
                "keyword": keyword,
                "accounts": [],
                "articles": [],
                "total": 0,
                "errors": [],
            }
        )

    # Step 2: 并行搜索每个公众号的文章
    tasks = [
        search_articles_for_account(
            author=author,
            keyword=keyword,
            cookie=cookie,
            token=token,
            begin=0,
            count=articles_per_account,
            search_field=7,
        )
        for author in authors
    ]
    results = await asyncio.gather(*tasks)

    articles = []
    errors = []
    author_totals = {}
    for author, (items, total, error) in zip(authors, results):
        author_totals[author["fakeid"]] = total
        if error:
            errors.append(error)
        articles.extend(items)

    # 去重 + 排序
    articles = dedupe_articles(articles)
    articles.sort(key=lambda a: a.get("update_time") or a.get("create_time") or 0, reverse=True)

    # 清理标题中的高亮标签，处理封面图
    for article in articles:
        article["title"] = strip_highlight(article.get("title", ""))
        if article.get("cover"):
            article["cover"] = proxy_image_url(article["cover"], base_url)
        # 处理 link 中的 HTML 实体
        article["link"] = article.get("link", "").replace("&amp;", "&")

    return SearchAllResponse(
        success=True,
        data={
            "keyword": keyword,
            "accounts": [
                {
                    "fakeid": a["fakeid"],
                    "nickname": a["nickname"],
                    "alias": a.get("alias", ""),
                    "username": a.get("username", ""),
                    "round_head_img": proxy_image_url(a.get("round_head_img", ""), base_url),
                    "service_type": a.get("service_type", 0),
                    "signature": a.get("signature", ""),
                    "article_count": author_totals.get(a["fakeid"], 0),
                }
                for a in authors
            ],
            "articles": articles,
            "total": len(articles),
            "author_totals": author_totals,
            "errors": errors,
        },
    )

