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
        return text[:1500]  # まとめて送るため、1記事あたりの文字数を少しコンパクトに調整
  except Exception as e:
    print(f"本文抽出スキップ ({url}): {e}")
  return fallback_summary


def batch_translate_and_summarize(articles_batch):
  """複数の記事をまとめて1回で翻訳・要約する"""
  # 送信するデータをテキストとして組み立てる
  batch_text = ""
  for i, art in enumerate(articles_batch, 1):
    batch_text += f"\n--- 記事 {i} ---\n"
    batch_text += f"掲載サイト: {art['site']}\n"
    batch_text += f"タイトル: {art['title']}\n"
    batch_text += f"本文: {art['content']}\n"

  prompt = f"""
あなたはMLB専門のスポーツライターです。以下の複数（最大10件）の記事を、日本のマリナーズファン向けにそれぞれ翻訳・要約してください。

【出力ルール】
1. 各記事ごとに、必ず以下の形式で出力してください。
[ARTICLE_START]
サイト名: （元のサイト名）
■ （タイトルの自然な日本語訳）
・要点1
・要点2
・要点3
[ARTICLE_END]
2. 記事の順番を崩さず、入力された順番通りに出力してください。
3. セイバーメトリクス指標や選手名はそのまま残してください。

【処理する記事データ】
{batch_text}
"""
  try:
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.3),
    )
    return response.text
  except Exception as e:
    print(f"一括翻訳エラー: {e}")
    return ""


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
    html_content += f"""
        <div class="card">
            <span class="site-tag">{art['site']}</span>
            <div class="article-title">{art['jp_title']}</div>
            <div class="summary-box">
                <ul>{art['bullet_points']}</ul>
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
  collected = []

  # 1. 各専用フィードから記事を集める（例: 各5件、合計15件程度）
  for site, url in MARINERS_ONLY_FEEDS.items():
    feed = fetch_feed(url)
    for entry in feed.entries[:5]:
      collected.append({
          "site": site,
          "title": entry.get("title", ""),
          "link": entry.get("link", ""),
          "summary": entry.get("summary", ""),
      })

  # 2. 全体フィードからも集める
  for site, url in GENERAL_MLB_FEEDS.items():
    feed = fetch_feed(url)
    for entry in feed.entries[:15]:
      if is_mariners_article(entry):
        collected.append({
            "site": site,
            "title": entry.get("title", ""),
            "link": entry.get("link", ""),
            "summary": entry.get("summary", ""),
        })

  print(
      f"合計 {len(collected)} 件の記事の本文を抽出します..."
      + "=" * 50
  )

  # 本文を事前に抽出しておく
  raw_articles = []
  for item in collected:
    print(f"本文抽出: [{item['site']}] {item['title']}")
    body_text = extract_article_text(item["link"], item["summary"])
    raw_articles.append({
        "site": item["site"],
        "title": item["title"],
        "link": item["link"],
        "content": body_text,
    })

  # 3. 10件ずつ（または設定した単位で）まとめてGeminiに一括送信する
  batch_size = 10
  parsed_articles = []

  for i in range(0, len(raw_articles), batch_size):
    batch = raw_articles[i : i + batch_size]
    print(
        f"Geminiに {len(batch)} 件の記事を一括で翻訳・要約させます..."
    )

    response_text = batch_translate_and_summarize(batch)

    # 返ってきた一括テキストを [ARTICLE_END] などの目印で綺麗に切り分ける
    blocks = response_text.split("[ARTICLE_START]")
    for idx, block in enumerate(blocks):
      if "[ARTICLE_END]" not in block:
        continue
      try:
        # ブロックの中身を解析
        lines = [
            line.strip()
            for line in block.split("[ARTICLE_END]")[0].split("\n")
            if line.strip()
        ]

        # 該当する元のリンクを紐付け
        original_index = i + idx - 1 if idx - 1 < len(batch) else len(batch) - 1
        if original_index < 0:
          original_index = 0
        link = batch[original_index]["link"]
        site = batch[original_index]["site"]

        jp_title = ""
        bullets = []
        for line in lines:
          if line.startswith("■"):
            jp_title = line.replace("■", "").strip()
          elif line.startswith("・"):
            bullets.append(f"<li>{line.replace('・','').strip()}</li>")

        if jp_title and bullets:
          parsed_articles.append({
              "site": site,
              "jp_title": jp_title,
              "link": link,
              "bullet_points": "".join(bullets),
          })
      except Exception as ex:
        print(f"パース処理エラー: {ex}")
        continue

    # 1括送るごとに少しだけウェイトを入れる（念のため）
    time.sleep(2)

  print(f"合計 {len(parsed_articles)} 件のカードを生成します。")
  # HTML生成
  generate_html(parsed_articles)


if __name__ == "__main__":
  main()
