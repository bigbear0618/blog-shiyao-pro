#!/usr/bin/env python3
"""Generate the stable AI daily rankings page."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from html import escape, unescape
from html.parser import HTMLParser
from pathlib import Path
import re
import sys
import urllib.error
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "ai-daily.html"
UA = "blog-shiyao-ai-daily/1.0 (+https://blog.shiyao.pro)"
CN_TZ = timezone(timedelta(hours=8))


@dataclass
class NewsItem:
    title: str
    link: str
    source: str
    summary: str
    published: str = ""


@dataclass
class RepoItem:
    name: str
    link: str
    lang: str
    stars_today: str
    desc: str


def fetch(url: str, timeout: int = 15) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as res:
        charset = res.headers.get_content_charset() or "utf-8"
        return res.read().decode(charset, errors="replace")


def clean_html(value: str) -> str:
    value = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", value, flags=re.S)
    value = re.sub(r"<[^>]+>", " ", value)
    return " ".join(unescape(value).split())


def extract_tag(block: str, tag: str) -> str:
    m = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", block, re.S | re.I)
    return clean_html(m.group(1)) if m else ""


def parse_rss_items(xml: str, source: str, limit: int = 8) -> list[NewsItem]:
    items: list[NewsItem] = []
    blocks = re.findall(r"<item\b.*?</item>", xml, re.S | re.I)
    for block in blocks:
        title = extract_tag(block, "title")
        link = extract_tag(block, "link")
        summary = extract_tag(block, "description")
        pub = extract_tag(block, "pubDate")
        if title and link:
            items.append(NewsItem(title, link, source, summary, normalize_date(pub)))
    return items[:limit]


def parse_atom_items(xml: str, source: str, limit: int = 8) -> list[NewsItem]:
    items: list[NewsItem] = []
    blocks = re.findall(r"<entry\b.*?</entry>", xml, re.S | re.I)
    for block in blocks:
        title = extract_tag(block, "title")
        m = re.search(r'<link[^>]+href="([^"]+)"', block, re.I)
        link = unescape(m.group(1)) if m else ""
        summary = extract_tag(block, "summary") or extract_tag(block, "content")
        pub = extract_tag(block, "updated") or extract_tag(block, "published")
        if title and link:
            items.append(NewsItem(title, link, source, summary, normalize_date(pub)))
    return items[:limit]


def normalize_date(value: str) -> str:
    if not value:
        return ""
    try:
        return parsedate_to_datetime(value).astimezone(CN_TZ).strftime("%m-%d %H:%M")
    except Exception:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(CN_TZ).strftime("%m-%d %H:%M")
        except Exception:
            return ""


def collect_news() -> list[NewsItem]:
    sources = [
        ("OpenAI", "https://openai.com/news/rss.xml", "rss"),
        ("TechCrunch AI", "https://techcrunch.com/category/artificial-intelligence/feed/", "rss"),
        ("The Verge AI", "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml", "atom"),
    ]
    all_items: list[NewsItem] = []
    for name, url, kind in sources:
        try:
            xml = fetch(url)
        except Exception as exc:
            print(f"warn: failed to fetch {name}: {exc}", file=sys.stderr)
            continue
        if kind == "atom":
            all_items.extend(parse_atom_items(xml, name))
        else:
            all_items.extend(parse_rss_items(xml, name))

    if not all_items:
        all_items = fallback_news()

    seen: set[str] = set()
    ranked: list[NewsItem] = []
    for item in sorted(all_items, key=news_score, reverse=True):
        key = item.title.lower()
        if key in seen:
            continue
        seen.add(key)
        ranked.append(item)
        if len(ranked) == 6:
            break
    return ranked or fallback_news()


def news_score(item: NewsItem) -> tuple[int, str]:
    text = f"{item.title} {item.summary}".lower()
    score = 0
    for word, weight in [
        ("codex", 8),
        ("agent", 7),
        ("openai", 6),
        ("anthropic", 6),
        ("claude", 6),
        ("model", 5),
        ("enterprise", 4),
        ("safety", 4),
        ("governance", 4),
        ("video", 3),
        ("github", 3),
        ("aws", 3),
    ]:
        if word in text:
            score += weight
    return (score, item.published)


def fallback_news() -> list[NewsItem]:
    return [
        NewsItem("OpenAI frontier models and Codex are now available on AWS", "https://openai.com/index/openai-frontier-models-and-codex-are-now-available-on-aws/", "OpenAI", "OpenAI models and Codex enter Amazon Bedrock for enterprise deployment."),
        NewsItem("A blueprint for democratic governance of frontier AI", "https://openai.com/index/frontier-safety-blueprint/", "OpenAI", "OpenAI published a governance blueprint for frontier AI."),
        NewsItem("Claude Opus 4.8", "https://www.anthropic.com/news/claude-opus-4-8", "Anthropic", "Claude Opus 4.8 remains a key model and workflow topic."),
        NewsItem("Artificial Analysis model updates", "https://artificialanalysis.ai/articles", "Artificial Analysis", "Model ecosystem updates across LLM, speech, open weights, and speed."),
    ]


def parse_github_trending() -> list[RepoItem]:
    try:
        html = fetch("https://github.com/trending?spoken_language_code=&since=daily")
    except Exception as exc:
        print(f"warn: failed to fetch GitHub Trending: {exc}", file=sys.stderr)
        return fallback_repos()

    articles = re.findall(r'<article class="Box-row">(.*?)</article>', html, re.S)
    repos: list[RepoItem] = []
    for article in articles:
        m = re.search(r'<h2[^>]*>\s*<a[^>]*href="(/[^"]+)"[^>]*>(.*?)</a>', article, re.S)
        if not m:
            continue
        href, raw_title = m.groups()
        title = clean_html(raw_title).replace(" / ", "/")
        desc = ""
        dm = re.search(r'<p class="col-9[^>]*>(.*?)</p>', article, re.S)
        if dm:
            desc = clean_html(dm.group(1))
        lang = ""
        lm = re.search(r'<span itemprop="programmingLanguage">([^<]+)</span>', article)
        if lm:
            lang = clean_html(lm.group(1))
        stars_today = ""
        sm = re.search(r"([0-9,]+) stars today", article)
        if sm:
            stars_today = sm.group(1)
        item = RepoItem(title, f"https://github.com{href}", lang, stars_today, desc)
        if is_ai_repo(item):
            repos.append(item)
        if len(repos) == 8:
            break
    return repos or fallback_repos()


def is_ai_repo(repo: RepoItem) -> bool:
    text = f"{repo.name} {repo.desc}".lower()
    terms = [
        "ai",
        "agent",
        "llm",
        "rag",
        "mcp",
        "copilot",
        "notebook",
        "ocr",
        "memory",
        "swarm",
        "model",
        "claude",
        "codex",
        "physical ai",
    ]
    return any(term in text for term in terms)


def fallback_repos() -> list[RepoItem]:
    return [
        RepoItem("chopratejas/headroom", "https://github.com/chopratejas/headroom", "Python", "3,142", "Compress tool outputs, logs, files, and RAG chunks before they reach the LLM."),
        RepoItem("NousResearch/hermes-agent", "https://github.com/NousResearch/hermes-agent", "Python", "1,913", "The agent that grows with you."),
        RepoItem("CopilotKit/CopilotKit", "https://github.com/CopilotKit/CopilotKit", "TypeScript", "350", "The Frontend Stack for Agents & Generative UI."),
    ]


def render_rank_items_news(items: list[NewsItem]) -> str:
    rows = []
    for idx, item in enumerate(items, 1):
        rows.append(f"""
        <article class="rank-row">
          <div class="rank-index">{idx:02d}</div>
          <div>
            <h3><a href="{escape(item.link)}">{escape(item.title)}</a></h3>
            <p>{escape(item.summary or "AI 生态今日重点更新。")}</p>
            <span class="mini">{escape(item.source)}{(" · " + escape(item.published)) if item.published else ""}</span>
          </div>
        </article>""")
    return "\n".join(rows)


def render_rank_items_repos(items: list[RepoItem]) -> str:
    rows = []
    for idx, item in enumerate(items, 1):
        meta = " / ".join(x for x in [item.lang, f"+{item.stars_today} stars today" if item.stars_today else "daily trending"] if x)
        rows.append(f"""
        <article class="rank-row">
          <div class="rank-index">{idx:02d}</div>
          <div>
            <h3><a href="{escape(item.link)}">{escape(item.name)}</a></h3>
            <p>{escape(item.desc or "GitHub 今日趋势项目。")}</p>
            <span class="mini">{escape(meta)}</span>
          </div>
        </article>""")
    return "\n".join(rows)


def render_page(news: list[NewsItem], repos: list[RepoItem]) -> str:
    now = datetime.now(CN_TZ)
    today = now.strftime("%Y-%m-%d")
    updated = now.strftime("%Y-%m-%d %H:%M CST")
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>今日 AI 趋势看板 · {today} — blog.shiyao.pro</title>
  <meta name="description" content="{today} 今日 AI 资讯、GitHub AI 趋势榜、工具推荐和本地 Codex 生图工具。">
  <style>
    :root {{
      --bg: #f6f4ef;
      --ink: #191917;
      --muted: #6e6a60;
      --panel: #fffdfa;
      --line: #ded8cb;
      --accent: #206b4f;
      --accent-soft: #e4f2ea;
      --gold: #b8872f;
      color-scheme: light;
    }}

    * {{ box-sizing: border-box; }}

    body {{
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: ui-sans-serif, -apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", "Segoe UI", Arial, sans-serif;
      line-height: 1.65;
    }}

    a {{ color: inherit; text-decoration: none; }}
    a:hover {{ color: var(--accent); }}

    .shell {{ width: min(1180px, calc(100% - 32px)); margin: 0 auto; }}

    .topbar {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 26px 0 18px;
      border-bottom: 1px solid var(--line);
    }}

    .brand {{ font-weight: 800; letter-spacing: 0; }}
    .brand span {{ color: var(--accent); }}
    .back {{ color: var(--muted); font-size: 0.92rem; }}

    .hero {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) 300px;
      gap: 42px;
      padding: 58px 0 42px;
      border-bottom: 1px solid var(--line);
    }}

    .eyebrow {{
      display: inline-flex;
      padding: 0.2rem 0.58rem;
      border: 1px solid var(--line);
      border-radius: 999px;
      background: var(--panel);
      color: var(--accent);
      font-size: 0.78rem;
      font-weight: 800;
      letter-spacing: 0.06em;
      text-transform: uppercase;
    }}

    h1 {{
      max-width: 820px;
      margin: 18px 0 16px;
      font-size: clamp(2.25rem, 6vw, 5.1rem);
      line-height: 0.96;
      letter-spacing: 0;
    }}

    .lead {{
      max-width: 720px;
      margin: 0;
      color: var(--muted);
      font-size: 1.06rem;
    }}

    .stamp {{
      align-self: end;
      padding: 22px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
    }}

    .stamp strong {{ display: block; color: var(--accent); font-size: 2.4rem; line-height: 1; }}
    .stamp span {{ color: var(--muted); font-size: 0.9rem; }}

    .grid {{
      display: grid;
      grid-template-columns: repeat(12, 1fr);
      gap: 18px;
      padding: 26px 0 46px;
    }}

    .module {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      overflow: hidden;
    }}

    .module.news {{ grid-column: span 7; }}
    .module.github {{ grid-column: span 5; }}
    .module.tools {{ grid-column: span 7; }}
    .module.image-tool {{ grid-column: span 5; }}

    .module-head {{
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 16px;
      padding: 18px 20px;
      border-bottom: 1px solid var(--line);
    }}

    h2 {{ margin: 0; font-size: 1.05rem; letter-spacing: 0; }}
    .module-head small {{ color: var(--muted); }}

    .rank-row {{
      display: grid;
      grid-template-columns: 52px 1fr;
      gap: 14px;
      padding: 18px 20px;
      border-bottom: 1px solid color-mix(in srgb, var(--line) 70%, transparent);
    }}

    .rank-row:last-child {{ border-bottom: 0; }}

    .rank-index {{
      width: 38px;
      height: 38px;
      display: grid;
      place-items: center;
      border-radius: 8px;
      background: var(--accent-soft);
      color: var(--accent);
      font-weight: 900;
      font-variant-numeric: tabular-nums;
    }}

    .rank-row h3 {{ margin: 0 0 4px; font-size: 1rem; line-height: 1.34; }}
    .rank-row p {{ margin: 0 0 7px; color: var(--muted); font-size: 0.9rem; }}
    .mini {{ color: var(--gold); font-size: 0.78rem; font-weight: 700; }}

    .tool-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
      padding: 18px 20px 20px;
    }}

    .tool-card {{
      min-height: 132px;
      padding: 16px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fbf8f0;
    }}

    .tool-card h3 {{ margin: 0 0 6px; font-size: 1rem; }}
    .tool-card p {{ margin: 0; color: var(--muted); font-size: 0.88rem; }}

    .image-panel {{ padding: 18px 20px 20px; }}
    label {{ display: block; margin-bottom: 7px; color: var(--muted); font-size: 0.86rem; font-weight: 700; }}

    textarea,
    input {{
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
      color: var(--ink);
      font: inherit;
    }}

    textarea {{
      min-height: 132px;
      resize: vertical;
      padding: 12px;
    }}

    input {{ height: 38px; padding: 0 11px; }}

    .field {{ margin-bottom: 12px; }}

    button {{
      width: 100%;
      min-height: 42px;
      border: 0;
      border-radius: 8px;
      background: var(--accent);
      color: #fff;
      font: inherit;
      font-weight: 800;
      cursor: pointer;
    }}

    button:disabled {{ opacity: 0.55; cursor: wait; }}

    .status {{
      min-height: 24px;
      margin: 12px 0;
      color: var(--muted);
      font-size: 0.86rem;
    }}

    .preview {{
      min-height: 220px;
      display: grid;
      place-items: center;
      border: 1px dashed var(--line);
      border-radius: 8px;
      background: #fbf8f0;
      color: var(--muted);
      overflow: hidden;
    }}

    .preview img {{ width: 100%; height: auto; display: block; }}

    .foot {{
      padding: 28px 0 48px;
      border-top: 1px solid var(--line);
      color: var(--muted);
      font-size: 0.86rem;
    }}

    @media (max-width: 920px) {{
      .hero {{ grid-template-columns: 1fr; }}
      .stamp {{ align-self: start; }}
      .module.news,
      .module.github,
      .module.tools,
      .module.image-tool {{ grid-column: 1 / -1; }}
      .tool-grid {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <main class="shell">
    <nav class="topbar" aria-label="站点导航">
      <a class="brand" href="/">blog<span>.shiyao</span>.pro</a>
      <a class="back" href="/">返回文章列表</a>
    </nav>

    <section class="hero">
      <div>
        <span class="eyebrow">AI Daily · 10:00 CST</span>
        <h1>今日 AI 趋势看板</h1>
        <p class="lead">简洁版每日更新：AI 资讯、GitHub 趋势、工具推荐和本地 Codex 生图入口。页面由脚本自动生成，计划每天北京时间 10:00 更新。</p>
      </div>
      <aside class="stamp">
        <strong>{today}</strong>
        <span>最后生成：{updated}</span>
      </aside>
    </section>

    <section class="grid">
      <section class="module news">
        <div class="module-head">
          <h2>今日 AI 资讯</h2>
          <small>RSS + 官方来源</small>
        </div>
{render_rank_items_news(news)}
      </section>

      <section class="module github">
        <div class="module-head">
          <h2>今日 GitHub 趋势榜单</h2>
          <small>daily trending / AI filter</small>
        </div>
{render_rank_items_repos(repos)}
      </section>

      <section class="module tools">
        <div class="module-head">
          <h2>工具推荐</h2>
          <small>今天适合研究的 workflow</small>
        </div>
        <div class="tool-grid">
          <a class="tool-card" href="https://github.com/nexu-io/html-video">
            <h3>html-video</h3>
            <p>把文章、链接、Repo 交给 Agent，生成多帧 HTML 视频，再导出 MP4。</p>
          </a>
          <a class="tool-card" href="https://github.com/heygen-com/hyperframes">
            <h3>HyperFrames</h3>
            <p>HTML / CSS / GSAP 动效视频引擎，适合产品介绍和动态海报。</p>
          </a>
          <a class="tool-card" href="https://github.com/remotion-dev/skills">
            <h3>Remotion Skills</h3>
            <p>用 React 批量制作固定栏目、排行榜、字幕和数据视频。</p>
          </a>
          <a class="tool-card" href="https://github.com/dexhunter/seedance2-skill">
            <h3>Seedance Prompt</h3>
            <p>生成即梦 Seedance 2.0 分镜、运镜、对白和素材引用提示词。</p>
          </a>
        </div>
      </section>

      <section class="module image-tool">
        <div class="module-head">
          <h2>本地 Codex 生图工具</h2>
          <small>需要启动 helper</small>
        </div>
        <div class="image-panel">
          <div class="field">
            <label for="imagePrompt">生图 Prompt</label>
            <textarea id="imagePrompt" placeholder="例如：极简科技资讯封面，米白背景，绿色细线图形，中心是一枚发光的 AI 芯片， editorial poster style"></textarea>
          </div>
          <div class="field">
            <label for="helperUrl">本地 helper 地址</label>
            <input id="helperUrl" value="/ai-image/generate-image">
          </div>
          <div class="field">
            <label for="imageToken">访问 Token</label>
            <input id="imageToken" type="password" placeholder="服务器部署时需要填写">
          </div>
          <button id="generateBtn" type="button">生成图片</button>
          <div class="status" id="imageStatus">服务器已部署时使用同域地址；本机调试可改成 <code>http://127.0.0.1:8787/generate-image</code></div>
          <div class="preview" id="imagePreview">生成后图片会显示在这里</div>
        </div>
      </section>
    </section>

    <footer class="foot">
      数据源：OpenAI RSS、TechCrunch AI RSS、The Verge AI RSS、GitHub Trending daily。X/Twitter 话题暂不做自动抓取，后续可加入公开 topic 采集。页面生成脚本：<code>scripts/generate-ai-daily.py</code>。
    </footer>
  </main>

  <script>
    const btn = document.getElementById("generateBtn");
    const statusEl = document.getElementById("imageStatus");
    const preview = document.getElementById("imagePreview");
    const promptEl = document.getElementById("imagePrompt");
    const helperEl = document.getElementById("helperUrl");
    const tokenEl = document.getElementById("imageToken");

    btn.addEventListener("click", async () => {{
      const prompt = promptEl.value.trim();
      if (!prompt) {{
        statusEl.textContent = "请先输入生图 prompt。";
        return;
      }}

      btn.disabled = true;
      statusEl.textContent = "正在调用本地 Codex helper，可能需要几十秒到几分钟。";
      preview.textContent = "生成中...";

      try {{
        const token = tokenEl.value.trim();
        const payload = {{ prompt }};
        if (token) payload.token = token;
        const response = await fetch(helperEl.value.trim(), {{
          method: "POST",
          headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify(payload)
        }});
        const data = await response.json();
        if (!response.ok || !data.ok) {{
          throw new Error(data.error || "生成失败");
        }}
        const img = new Image();
        img.alt = prompt;
        img.src = data.image_url + "?t=" + Date.now();
        preview.replaceChildren(img);
        statusEl.textContent = "生成完成：" + (data.filename || "image");
      }} catch (err) {{
        statusEl.textContent = "生成失败：" + err.message + "。确认本地 helper 已启动，并且 Codex 有可用的生图能力。";
        preview.textContent = "暂无图片";
      }} finally {{
        btn.disabled = false;
      }}
    }});
  </script>
</body>
</html>
"""


def main() -> int:
    news = collect_news()
    repos = parse_github_trending()
    OUT.write_text(render_page(news, repos), encoding="utf-8")
    print(f"generated {OUT.relative_to(ROOT)} with {len(news)} news and {len(repos)} repos")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
