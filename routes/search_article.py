#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (C) 2026 wang1733238039
# Licensed under the GNU Affero General Public License v3.0
# See LICENSE file in the project root for full license text.
# SPDX-License-Identifier: AGPL-3.0-only
"""
在线检索微信公众号文章

这组接口基于已登录的微信公众号后台凭证：
1. searchbiz 搜索公众号/作者并拿 fakeid
2. appmsgpublish 在指定 fakeid 下在线检索文章或读取最新文章
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import httpx
from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field

from utils import rss_store
from utils.auth_manager import auth_manager
from utils.image_proxy import proxy_image_url

logger = logging.getLogger(__name__)

router = APIRouter()

WECHAT_SEARCH_BIZ_URL = "https://mp.weixin.qq.com/cgi-bin/searchbiz"
WECHAT_APPMSG_URL = "https://mp.weixin.qq.com/cgi-bin/appmsgpublish"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


class OnlineAuthor(BaseModel):
    fakeid: str
    nickname: str = ""
    alias: str = ""
    round_head_img: str = ""
    service_type: int = 0
    subscribed: bool = False


class OnlineArticle(BaseModel):
    fakeid: str
    source: str
    alias: str = ""
    aid: str = ""
    title: str = ""
    link: str = ""
    digest: str = ""
    cover: str = ""
    author: str = ""
    update_time: int = 0
    create_time: int = 0


class OnlineResponse(BaseModel):
    success: bool
    data: Optional[Dict] = None
    error: Optional[str] = None


class FollowAuthorRequest(BaseModel):
    fakeid: str = Field(..., description="公众号 FakeID")
    nickname: str = Field("", description="公众号名称")
    alias: str = Field("", description="公众号微信号")
    head_img: str = Field("", description="头像 URL")


def get_base_url(request: Optional[Request]) -> str:
    if not request:
        return ""
    proto = request.headers.get("X-Forwarded-Proto", "http")
    host = request.headers.get("X-Forwarded-Host") or request.headers.get("Host", "localhost:5001")
    return f"{proto}://{host}"


def get_wechat_credentials() -> Tuple[Optional[str], Optional[str], Optional[str]]:
    credentials = auth_manager.get_credentials()
    if not credentials:
        return None, None, "服务器未登录，请先访问管理页面扫码登录"

    token = credentials.get("token")
    cookie = credentials.get("cookie")
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
        publish_page = json.loads(publish_page or "{}")
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
                "author": article.get("author", ""),
                "update_time": article.get("update_time", 0),
                "create_time": article.get("create_time", 0),
            })

    return articles, int(publish_page.get("total_count") or len(articles))


def format_wechat_error(base_resp: Dict) -> str:
    ret_code = base_resp.get("ret")
    error_msg = base_resp.get("err_msg", "未知错误")
    if ret_code == 200003 or "login" in str(error_msg).lower():
        return "登录已过期或需要重新扫码登录"
    if ret_code == 200002 and "invalid arg" in str(error_msg).lower():
        return "该公众号在微信侧已无法访问，可能已注销、改名或 fakeid 失效"
    return f"微信接口返回错误: ret={ret_code}, msg={error_msg}"


async def search_wechat_authors(
    keyword: str,
    *,
    count: int,
    request: Optional[Request],
) -> Tuple[bool, List[Dict], Optional[str]]:
    token, cookie, error = get_wechat_credentials()
    if error:
        return False, [], error

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
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                WECHAT_SEARCH_BIZ_URL,
                params=params,
                headers=wechat_headers(cookie),
            )
            response.raise_for_status()
            result = response.json()
    except Exception as exc:
        logger.warning("WeChat author search failed: %s", exc)
        return False, [], f"搜索作者失败: {exc}"

    base_resp = result.get("base_resp", {})
    if base_resp.get("ret") != 0:
        return False, [], format_wechat_error(base_resp)

    base_url = get_base_url(request)
    subscriptions = {s["fakeid"] for s in rss_store.list_subscriptions()}
    blacklisted = set(rss_store.get_active_blacklist_fakeids())

    authors = []
    for account in result.get("list", []):
        fakeid = account.get("fakeid", "")
        if not fakeid or fakeid in blacklisted:
            continue
        authors.append({
            "fakeid": fakeid,
            "nickname": account.get("nickname", ""),
            "alias": account.get("alias", ""),
            "round_head_img": proxy_image_url(account.get("round_head_img", ""), base_url),
            "service_type": account.get("service_type", 0),
            "subscribed": fakeid in subscriptions,
        })

    return True, authors, None


async def fetch_online_articles_for_author(
    author: Dict,
    *,
    keyword: Optional[str],
    begin: int,
    count: int,
) -> Tuple[List[Dict], int, Optional[str]]:
    token, cookie, error = get_wechat_credentials()
    if error:
        return [], 0, error

    is_search = bool(keyword and keyword.strip())
    params = {
        "sub": "search" if is_search else "list",
        "search_field": "7" if is_search else "null",
        "begin": begin,
        "count": count,
        "query": keyword or "",
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
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                WECHAT_APPMSG_URL,
                params=params,
                headers=wechat_headers(cookie),
            )
            response.raise_for_status()
            result = response.json()
    except Exception as exc:
        logger.warning("WeChat article fetch failed: fakeid=%s error=%s", author["fakeid"][:8], exc)
        return [], 0, f"{author.get('nickname') or author['fakeid']} 请求失败: {exc}"

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


def followed_authors() -> List[Dict]:
    return [
        {
            "fakeid": sub["fakeid"],
            "nickname": sub.get("nickname") or sub["fakeid"],
            "alias": sub.get("alias", ""),
            "round_head_img": sub.get("head_img", ""),
            "subscribed": True,
        }
        for sub in rss_store.list_subscriptions()
    ]


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


@router.get("/online/authors", response_model=OnlineResponse, summary="在线搜索公众号作者")
async def online_search_authors(
    query: str = Query(..., description="公众号名称、作者名或关键词", min_length=1, max_length=100),
    count: int = Query(10, ge=1, le=20, description="返回数量"),
    request: Request = None,
):
    ok, authors, error = await search_wechat_authors(query, count=count, request=request)
    if not ok:
        return OnlineResponse(success=False, error=error)
    return OnlineResponse(success=True, data={"authors": authors, "total": len(authors)})


@router.get("/online/followed-authors", response_model=OnlineResponse, summary="获取已关注作者")
async def get_followed_authors(request: Request = None):
    base_url = get_base_url(request)
    authors = []
    for author in followed_authors():
        authors.append({
            **author,
            "round_head_img": proxy_image_url(author.get("round_head_img", ""), base_url),
        })
    return OnlineResponse(success=True, data={"authors": authors, "total": len(authors)})


@router.post("/online/follow-author", response_model=OnlineResponse, summary="关注作者")
async def follow_author(req: FollowAuthorRequest):
    rss_store.add_subscription(
        fakeid=req.fakeid,
        nickname=req.nickname,
        alias=req.alias,
        head_img=req.head_img,
    )
    return OnlineResponse(success=True, data={"message": "已关注作者"})


@router.delete("/online/follow-author/{fakeid}", response_model=OnlineResponse, summary="取消关注作者")
async def unfollow_author(fakeid: str):
    removed = rss_store.remove_subscription(fakeid)
    return OnlineResponse(
        success=removed,
        data={"message": "已取消关注" if removed else "未找到该作者"},
    )


@router.get("/search/articles", response_model=OnlineResponse, summary="在线检索公众号文章")
async def online_search_articles(
    keyword: str = Query(..., description="文章关键词", min_length=1, max_length=100),
    scope: str = Query("followed", regex="^(followed|author|discover)$", description="检索范围"),
    fakeid: Optional[str] = Query(None, description="scope=author 时指定公众号 fakeid"),
    author_name: str = Query("", description="scope=discover 时先按作者/公众号关键词发现作者"),
    begin: int = Query(0, ge=0, description="单个公众号内偏移"),
    count: int = Query(10, ge=1, le=20, description="每个公众号最多返回数量"),
    max_authors: int = Query(5, ge=1, le=10, description="最多检索多少个公众号"),
    request: Request = None,
):
    authors: List[Dict] = []
    discover_error = None

    if scope == "author":
        if not fakeid:
            return OnlineResponse(success=False, error="请选择一个公众号作者")
        sub = rss_store.get_subscription(fakeid)
        authors = [{
            "fakeid": fakeid,
            "nickname": (sub or {}).get("nickname") or fakeid,
            "alias": (sub or {}).get("alias", ""),
        }]
    elif scope == "discover":
        query_for_author = author_name.strip() or keyword
        ok, discovered, discover_error = await search_wechat_authors(
            query_for_author,
            count=max_authors,
            request=request,
        )
        if not ok:
            return OnlineResponse(success=False, error=discover_error)
        authors = discovered[:max_authors]
    else:
        authors = followed_authors()[:max_authors]

    if not authors:
        return OnlineResponse(
            success=False,
            error="没有可检索的作者。请先搜索并关注公众号，或切换到“自动发现作者”模式。",
        )

    tasks = [
        fetch_online_articles_for_author(
            author,
            keyword=keyword,
            begin=begin,
            count=count,
        )
        for author in authors
    ]
    results = await asyncio.gather(*tasks)

    articles = []
    errors = []
    totals = {}
    for author, (items, total, error) in zip(authors, results):
        totals[author["fakeid"]] = total
        if error:
            errors.append(error)
        articles.extend(items)

    articles = dedupe_articles(articles)
    articles.sort(key=lambda item: item.get("update_time") or item.get("create_time") or 0, reverse=True)

    return OnlineResponse(
        success=True,
        data={
            "keyword": keyword,
            "scope": scope,
            "authors": authors,
            "articles": articles,
            "total": len(articles),
            "author_totals": totals,
            "errors": errors,
            "discover_error": discover_error,
        },
    )


@router.get("/online/yesterday", response_model=OnlineResponse, summary="查看关注作者昨日更新")
async def yesterday_updates(
    count: int = Query(20, ge=1, le=50, description="每个作者拉取最新文章数量"),
):
    authors = followed_authors()
    if not authors:
        return OnlineResponse(success=False, error="还没有关注作者，请先搜索并关注公众号")

    now = datetime.now()
    start = datetime(now.year, now.month, now.day) - timedelta(days=1)
    end = datetime(now.year, now.month, now.day)
    start_ts = int(start.timestamp())
    end_ts = int(end.timestamp())

    tasks = [
        fetch_online_articles_for_author(author, keyword=None, begin=0, count=count)
        for author in authors
    ]
    results = await asyncio.gather(*tasks)

    updates = []
    errors = []
    for author, (items, _total, error) in zip(authors, results):
        if error:
            errors.append(error)
            continue
        yesterday_items = [
            item for item in items
            if start_ts <= int(item.get("update_time") or item.get("create_time") or 0) < end_ts
        ]
        if yesterday_items:
            updates.append({
                "fakeid": author["fakeid"],
                "nickname": author.get("nickname") or author["fakeid"],
                "alias": author.get("alias", ""),
                "count": len(yesterday_items),
                "articles": yesterday_items,
            })

    return OnlineResponse(
        success=True,
        data={
            "date": start.strftime("%Y-%m-%d"),
            "start": start_ts,
            "end": end_ts,
            "updates": updates,
            "total": sum(item["count"] for item in updates),
            "errors": errors,
        },
    )

