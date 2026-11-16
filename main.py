import datetime
import os
import time
import feedparser
from google import genai
from google.genai import types
import requests
import trafilatura

# ==========================================
# 設定エリア
# ==========================================
# 取得したAPIキーを設定（環境変数から読み込み）
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "あなたのAPIキーをここに貼る")
client = genai.Client(api_key=GEMINI_API_KEY)

MARINERS_ONLY_FEEDS = {
    "MLB.com (Mariners)": "https://www.mlb.com/mariners/feeds/news/rss.xml",
    "Lookout Landing": "https://www.lookoutlanding.com/rss/index.xml",
    "MLBTR (Mariners)": "https://www.mlbtraderumors.com/seattle-mariners/feed",
}

GENERAL_MLB_FEEDS = {
    "FanGraphs": "https://blogs.fangraphs.com/feed/",
    "Just Baseball": "https://www.justbaseball.com/feed/",
    "ESPN": "https://www.espn.com/espn/rss/mlb/news",
}

KEYWORDS = [
    "mariners",
    "seattle",
    "julio rodriguez",
    "cal raleigh",
    "logan gilbert",
    "george kirby",
    "bryce miller",
    "bryan woo",
    "andres munoz",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        " (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}


def fetch_feed(url):
  try:
    res = requests.get(url, headers=HEADERS, timeout=10)
    res.raise_for_status()
    return feedparser.parse(res.content)
  except Exception as e:
    print(f"RSS取得エラー ({url}): {e}")
    return feedparser.FeedParserDict(entries=[])


def is_mariners_article(entry):
  title = entry.get("title", "").lower()
  summary = entry.get("summary", "").lower()
  tags = " ".join([t.get("term", "").lower() for t in entry.get("tags", [])])
  return any(kw in f"{title} {summary} {tags}" for kw in KEYWORDS)


def extract_article_text(url, fallback_summary):
  try:
    downloaded = trafilatura.fetch_url(url)
    if downloaded:
      text = trafilatura.extract(downloaded)
      if text and len(text) > 200:
        return text[:4000]
  except Exception as e:
    print(f"本文抽出スキップ ({url}): {e}")
  return fallback_summary


def translate_and_summarize(site, title, content):
  prompt = f"""
あなたはMLB専門のスポーツライターです。以下の英語記事（{site}掲載）を日本のマリナーズファン向けに翻訳・要約してください。

【出力ルール】
1. 1行目に「■ タイトルの自然な日本語訳」を書く（「■」を含めないで、純粋なタイトルテキストのみにしてください）
2. 2行目以降に、記事の要点を箇条書き（・）で3つにまとめる
3. セイバーメトリクス指標や選手名はそのまま残す
4. 余計な前置きは一切書かない

【元記事タイトル】
{title}

【元記事本文】
{content}
"""
  try:
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.3),
    )
    return response.text
  except Exception as e:
    return f"■ 翻訳エラー\n・エラーが発生しました: {e}"


def generate_html(articles_data):
  """取得したデータをきれいなHTMLファイルに出力する"""
  now_str = datetime.datetime.now().strftime("%Y年%m月%d日 %H:%M")

  html_content = f"""<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SEA Mariners Daily Digest</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background-color: #f4f6f9; color: #333; margin: 0; padding: 20px; }}
        .container {{ max-width: 800px; margin: 0 auto; }}
        h1 {{ color: #0c2340; text-align: center; margin-bottom: 5px; }}
        .subtitle {{ text-align: center; color: #666; font-size: 0.9rem; margin-bottom: 30px; }}
        .card {{ background: #fff; border-radius: 8px; padding: 20px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); border-left: 5px solid #005c5c; }}
        .site-tag {{ display: inline-block; background: #0c2340; color: #fff; font-size: 0.75rem; padding: 3px 8px; border-radius: 4px; margin-bottom: 8px; }}
        .article-title {{ font-size: 1.1rem; font-weight: bold; color: #111; margin-bottom: 10px; }}
        .summary-box {{ background: #f8f9fa; padding: 12px 15px; border-radius: 6px; font-size: 0.95rem; line-height: 1.6; margin-bottom: 12px; }}
        .summary-box ul {{ margin: 0; padding-left: 20px; }}
        .summary-box li {{ margin-bottom: 4px; }}
        .link-btn {{ display: inline-block; font-size: 0.85rem; color: #005c5c; text-decoration: none; font-weight: bold; }}
        .link-btn:hover {{ text-decoration: underline; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>マリナーズ最新情報まとめ</h1>
        <div class="subtitle">最終更新: {now_str}</div>
"""

  for art in articles_data:
    lines = art["result"].strip().split("\n")
    jp_title = lines[0].replace("■", "").strip()
    bullet_points = "".join([
        f"<li>{l.replace('・','').strip()}</li>"
        for l in lines[1:]
        if l.strip()
    ])

    html_content += f"""
        <div class="card">
            <span class="site-tag">{art['site']}</span>
            def title_block(): pass
            <div class="article-title">{jp_title}</div>
            <div class="summary-box">
                <ul>{bullet_points}</ul>
            </div>
            <a class="link-btn" href="{art['link']}" target="_blank">元記事を読む (英語) &rarr;</a>
        </div>
    """

  html_content += """
    </div>
</body>
</html>
"""

  with open("index.html", "w", encoding="utf-8") as f:
    f.write(html_content)
  print("index.html を生成しました！")


def main():
  articles_data = []
  collected = []

  # ① 専用フィード（取得数を 5件 -> 30件 に増加）
  for site, url in MARINERS_ONLY_FEEDS.items():
    feed = fetch_feed(url)
    for entry in feed.entries[:30]:
      collected.append(
          (site, entry.get("title"), entry.get("link"), entry.get("summary", ""))
      )

  # ② 全体フィード（検索対象を 15件 -> 30件 に増加）
  for site, url in GENERAL_MLB_FEEDS.items():
    feed = fetch_feed(url)
    for entry in feed.entries[:30]:
      if is_mariners_article(entry):
        collected.append(
            (site, entry.get("title"), entry.get("link"), entry.get("summary", ""))
        )

  print(f"合計 {len(collected)} 件の記事を処理します...\n" + "=" * 50)

  for site, title, link, summary in collected:
    print(f"処理中: [{site}] {title}")
    body_text = extract_article_text(link, summary)
    jp_result = translate_and_summarize(site, title, body_text)

    articles_data.append(
        {"site": site, "title": title, "link": link, "result": jp_result}
    )
    # 記事数が増えるため、API制限に引っかからないよう4秒待機を維持
    time.sleep(4)

  # HTML生成
  generate_html(articles_data)


if __name__ == "__main__":
  main()
