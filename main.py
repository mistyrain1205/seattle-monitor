import datetime
import json
import os
import feedparser
from google import genai
from google.genai import types
import requests
import trafilatura

# ==========================================
# 設定エリア
# ==========================================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
client = genai.Client(api_key=GEMINI_API_KEY)

HISTORY_FILE = "articles.json"
MAX_BATCH_SIZE = 12  # 一括翻訳の安定性と文字数確保のバランス用
MAX_DISPLAY_ARTICLES = 100

# 総合メディアや専門サイトを含むすべてのフィード
FEEDS = {
    "MLB.com (Mariners)": "https://www.mlb.com/mariners/feeds/news/rss.xml",
    "Lookout Landing": "https://www.lookoutlanding.com/rss/index.xml",
    "MLBTR (Mariners)": "https://www.mlbtraderumors.com/seattle-mariners/feed",
    "FanGraphs": "https://blogs.fangraphs.com/feed/",
    "Just Baseball": "https://www.justbaseball.com/feed/",
    "ESPN": "https://www.espn.com/espn/rss/mlb/news",
}

KEYWORDS = ["mariners", "seattle"]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        " (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}


def load_history():
  if os.path.exists(HISTORY_FILE):
    try:
      with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        return json.load(f)
    except Exception as e:
      print(f"履歴読み込みエラー: {e}")
  return []


def save_history(articles):
  with open(HISTORY_FILE, "w", encoding="utf-8") as f:
    json.dump(articles[:MAX_DISPLAY_ARTICLES], f, ensure_ascii=False, indent=2)


def fetch_feed(url):
  try:
    res = requests.get(url, headers=HEADERS, timeout=10)
    res.raise_for_status()
    return feedparser.parse(res.content)
  except Exception as e:
    print(f"RSS取得エラー ({url}): {e}")
    return feedparser.FeedParserDict(entries=[])


def is_target_article(entry):
  title = entry.get("title", "").lower()
  summary = entry.get("summary", "").lower()
  tags = " ".join([t.get("term", "").lower() for t in entry.get("tags", [])])
  combined = f"{title} {summary} {tags}"
  return any(kw in combined for kw in KEYWORDS)


def extract_article_text(url, fallback_summary):
  try:
    downloaded = trafilatura.fetch_url(url)
    if downloaded:
      text = trafilatura.extract(downloaded)
      if text and len(text) > 200:
        # 最大3500文字に拡張 ＆ 文末（ピリオド）で綺麗にカット
        if len(text) > 3500:
          cut_text = text[:3500]
          last_period = cut_text.rfind(".")
          if last_period > 1800:
            return cut_text[: last_period + 1]
          return cut_text
        return text
  except Exception as e:
    print(f"本文抽出スキップ ({url}): {e}")
  return fallback_summary


def batch_translate_articles(articles_batch):
  batch_text = ""
  for i, art in enumerate(articles_batch, 1):
    batch_text += f"\n--- 記事ID: {i} ---\n"
    batch_text += f"タイトル: {art['title']}\n"
    batch_text += f"本文: {art['content']}\n"

  prompt = f"""
あなたはMLB専門の翻訳者です。以下の複数（全{len(articles_batch)}件）の英語ニュース記事について、日本のマリナーズファン向けに「タイトル」と「本文」を自然な日本語に翻訳してください。

【出力ルール】
1. 各記事ごとに、必ず以下の形式（ID番号を含む）で出力してください。
[ARTICLE_START: 記事IDの数字]
TITLE: （タイトルの自然な日本語訳）
BODY:
（本文の自然な日本語訳）
[ARTICLE_END]
2. 全記事を省略せず、入力された順番通りに出力してください。

【翻訳する記事データ】
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
  jst = datetime.timezone(datetime.timedelta(hours=9))
  now_str = datetime.datetime.now(jst).strftime("%Y年%m月%d日 %H:%M (JST)")

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
        .meta-row {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }}
        .site-tag {{ display: inline-block; background: #0c2340; color: #fff; font-size: 0.75rem; padding: 3px 8px; border-radius: 4px; }}
        .date-tag {{ font-size: 0.8rem; color: #888; }}
        .article-title {{ font-size: 1.15rem; font-weight: bold; color: #111; margin-bottom: 12px; line-height: 1.4; }}
        .body-box {{ background: #f8f9fa; padding: 15px; border-radius: 6px; font-size: 0.95rem; line-height: 1.75; margin-bottom: 12px; color: #222; white-space: pre-wrap; max-height: 350px; overflow-y: auto; }}
        .link-btn {{ display: inline-block; font-size: 0.85rem; color: #005c5c; text-decoration: none; font-weight: bold; }}
        .link-btn:hover {{ text-decoration: underline; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>マリナーズ最新ニュース</h1>
        <div class="subtitle">最終更新: {now_str} / 掲載件数: {len(articles_data)}件</div>
"""

  for art in articles_data:
    added_date = art.get("added_at", "")
    jp_body = art.get("jp_body", "")
    html_content += f"""
        <div class="card">
            <div class="meta-row">
                <span class="site-tag">{art['site']}</span>
                <span class="date-tag">{added_date}</span>
            </div>
            <div class="article-title">{art['jp_title']}</div>
            <div class="body-box">{jp_body}</div>
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
  history_articles = load_history()
  seen_urls = {art["link"] for art in history_articles}
  print(f"過去の保存済み記事: {len(history_articles)} 件")

  new_candidates = []

  for site, url in FEEDS.items():
    feed = fetch_feed(url)
    limit = 20 if "Mariners" in site or "Lookout" in site else 40
    for entry in feed.entries[:limit]:
      link = entry.get("link", "")
      if link and link not in seen_urls:
        if "Mariners" in site or "Lookout" in site or is_target_article(entry):
          seen_urls.add(link)
          new_candidates.append({
              "site": site,
              "title": entry.get("title", ""),
              "link": link,
              "summary": entry.get("summary", ""),
          })

  target_articles = new_candidates[:MAX_BATCH_SIZE]
  print(
      f"新着の未処理記事: {len(new_candidates)} 件中、今回処理するのは"
      f" {len(target_articles)} 件です。"
  )

  if not target_articles:
    print("新着記事がないため、Gemini APIは呼び出さずに終了します。")
    generate_html(history_articles)
    return

  raw_articles = []
  for item in target_articles:
    print(f"本文抽出: [{item['site']}] {item['title']}")
    body_text = extract_article_text(item["link"], item["summary"])
    raw_articles.append({
        "site": item["site"],
        "title": item["title"],
        "link": item["link"],
        "content": body_text,
    })

  print(
      f"Geminiに {len(raw_articles)} 件を一括送信します（API消費: 1回のみ）..."
  )
  response_text = batch_translate_articles(raw_articles)

  jst = datetime.timezone(datetime.timedelta(hours=9))
  added_time_str = datetime.datetime.now(jst).strftime("%m/%d %H:%M取得")

  newly_parsed = []
  blocks = response_text.split("[ARTICLE_START:")
  for block in blocks[1:]:
    if "[ARTICLE_END]" not in block:
      continue
    try:
      header_and_body = block.split("[ARTICLE_END]")[0]
      first_line, rest = header_and_body.split("\n", 1)
      art_idx = int(first_line.replace("]", "").strip()) - 1
      if art_idx < 0 or art_idx >= len(raw_articles):
        continue

      orig = raw_articles[art_idx]

      if "TITLE:" in rest and "BODY:" in rest:
        title_part, body_part = rest.split("BODY:", 1)
        jp_title = title_part.replace("TITLE:", "").strip()
        jp_body = body_part.strip()

        if jp_title and jp_body:
          newly_parsed.append({
              "site": orig["site"],
              "jp_title": jp_title,
              "jp_body": jp_body,
              "link": orig["link"],
              "added_at": added_time_str,
          })
    except Exception as ex:
      print(f"パース処理スキップ: {ex}")
      continue

  print(f"新たに {len(newly_parsed)} 件の記事の翻訳が完了しました！")

  updated_articles = (newly_parsed + history_articles)[:MAX_DISPLAY_ARTICLES]
  save_history(updated_articles)
  generate_html(updated_articles)


if __name__ == "__main__":
  main()
