"""VOA Learning English の記事を取り込む。

VOA は米国政府の著作物でパブリックドメイン。ESL 向けに平易な語彙・ゆっくりした音声で
書かれており、読解・文法問題の素材として素性が確かなものを無償で使える。

市販の TOEIC 問題集をそのまま取ってこないのはこのため。問題文そのものを転記する代わりに、
権利のはっきりした英文を素材として、問題は自分の弱点に合わせて生成する。

    fetch_feed(url)     RSS から記事一覧
    fetch_article(url)  記事本文（段落）と語注
"""

from __future__ import annotations

import html
import re
import urllib.request
import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass

from .base import ExternalMaterial, note_path_for, slugify

FEEDS_PAGE = "https://learningenglish.voanews.com/rssfeeds"
_TIMEOUT_SECONDS = 30
_MIN_PARAGRAPH_CHARS = 40
# 本文末尾に付く定型（執筆クレジット・区切り線）と語注の見出し。
_CREDIT = re.compile(r"(wrote this story for VOA Learning English|adapted it|_{10,})")
_GLOSSARY_ENTRY = re.compile(r"^(?P<word>[^–—-]{1,40})\s*[–—-]\s*(?P<gloss>[a-z]{1,6}\.\s.+)$")


class ArticleFetchError(Exception):
    pass


@dataclass(frozen=True)
class Article:
    title: str
    url: str
    paragraphs: list[str]
    glossary: dict[str, str]

    @property
    def body(self) -> str:
        return "\n\n".join(self.paragraphs)


def _get(url: str, timeout: int = _TIMEOUT_SECONDS) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "acenglish/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            return response.read().decode("utf-8", errors="replace")
    except Exception as error:  # noqa: BLE001 - URL不正・通信断をまとめて呼び出し側へ
        raise ArticleFetchError(f"{url} を取得できませんでした: {error}") from error


def list_feeds(timeout: int = _TIMEOUT_SECONDS) -> list[str]:
    """RSS 一覧ページから配信 URL を拾う（VOA の feed URL は不透明な文字列のため）。"""
    page = _get(FEEDS_PAGE, timeout)
    paths = sorted(set(re.findall(r'href="(/api/[a-z0-9_\-]+)"', page)))
    return [f"https://learningenglish.voanews.com{path}" for path in paths]


def fetch_feed(url: str, limit: int = 10, timeout: int = _TIMEOUT_SECONDS) -> list[dict]:
    """RSS から記事の見出しとリンクを取る。本文は記事ページ側にしか無い。"""
    try:
        root = ElementTree.fromstring(_get(url, timeout))
    except ElementTree.ParseError as error:
        raise ArticleFetchError(f"{url} は RSS として解釈できません: {error}") from error

    channel = root.find("channel")
    if channel is None:
        raise ArticleFetchError(f"{url} に channel がありません。")
    return [
        {
            "title": (item.findtext("title") or "").strip(),
            "link": (item.findtext("link") or "").strip(),
            "published": (item.findtext("pubDate") or "").strip(),
        }
        for item in channel.findall("item")[:limit]
    ]


def parse_article(page_html: str, title: str, url: str) -> Article:
    """記事ページから本文段落と語注を抜く。

    `<div class="wsw">` の中だけを見るのではなく段落を拾うのは、VOA の記事が本文の前に
    音声プレイヤーの入れ子 div を大量に挟むため。閉じタグの対応を正規表現で追うより、
    段落を集めてから定型の末尾を落とす方が壊れにくい。
    """
    paragraphs: list[str] = []
    glossary: dict[str, str] = {}

    for raw in re.findall(r"<p[^>]*>(.*?)</p>", page_html, re.S):
        text = html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", raw))).strip()
        if len(text) < _MIN_PARAGRAPH_CHARS:
            continue
        match = _GLOSSARY_ENTRY.match(text)
        if match:
            glossary[match.group("word").strip()] = match.group("gloss").strip()
            continue
        if _CREDIT.search(text):
            continue
        paragraphs.append(text)

    if not paragraphs:
        raise ArticleFetchError(f"{url} から本文を抽出できませんでした。")
    return Article(title=title, url=url, paragraphs=paragraphs, glossary=glossary)


def fetch_article(url: str, title: str = "", timeout: int = _TIMEOUT_SECONDS) -> Article:
    page = _get(url, timeout)
    if not title:
        match = re.search(r"<title[^>]*>(.*?)</title>", page, re.S)
        title = html.unescape(match.group(1)).split("|")[0].strip() if match else url
    return parse_article(page, title, url)


def to_material(article: Article) -> ExternalMaterial:
    slug = slugify(article.url.rstrip("/").split("/")[-1].removesuffix(".html") or article.title)
    body = article.body
    if article.glossary:
        entries = "\n".join(f"- {word}: {gloss}" for word, gloss in article.glossary.items())
        body = f"{body}\n\n## 記事に付属する語注\n{entries}"
    return ExternalMaterial(
        review_id=f"voa.{slug}",
        source="voa",
        title=article.title,
        body=body,
        origin=article.url,
        source_file=note_path_for("reading", "voa"),
        source_commit=slug,
        chapter_title="VOA Learning English",
    )
