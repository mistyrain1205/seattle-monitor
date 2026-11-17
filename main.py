import datetime
import json
import os
import feedparser
from google import genai
from google.genai import types
import requests

# ==========================================
# 設定エリア
# ==========================================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "あなたのAPIキーをここに貼る")
client = genai.Client(api_key=GEMINI_API_KEY)

HISTORY_FILE = "articles.json"
MAX_BATCH_SIZE = 30
MAX_DISPLAY_ARTICLES = 100

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
    "j.p. crawford",
    "randy arozarena",
    "victor robles",
]

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


def is_mariners_article(entry):
  title = entry.get("title", "").lower()
  summary = entry.get("summary", "").lower()
  tags = " ".join([t.get("term", "").lower() for t in entry.get("tags", [])])
  return any(kw in f"{title} {summary} {tags}" for kw in KEYWORDS)


def batch_translate_titles(articles_batch):
  """最大30件の記事タイトルを1回のAPI呼び出しで一括翻訳する"""
  batch_text = ""
  for i, art in enumerate(articles_batch, 1):
    batch_text += f"{i}. {art['title']}\n"

  prompt = f"""
あなたはMLB専門の翻訳者です。以下の英語のニュース記事タイトル（全{len(articles_batch)}件）を、日本のマリナーズファン向けに自然な日本語に翻訳してください。

【出力ルール】
1. 必ず「番号. 日本語訳」の形式で、1行に1記事ずつ出力してください。（例: 1. フリオ・ロドリゲスが決勝ホームランを放つ）
2. 選手名やMLB専門用語は自然なカタカナ・表記にしてください。
3. 余計な挨拶や説明は一切書かず、翻訳リストのみを出力してください。

【翻訳するタイトル一覧】
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
        .subtitle {{ text-align: center; color: #666; font-size: 0.9rem; margin-bottom: 25px; }}
        .card {{ background: #fff; border-radius: 8px; padding: 16px 20px; margin-bottom: 12px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); border-left: 5px solid #005c5c; display: flex; flex-direction: column; gap: 6px; }}
        .meta-row {{ display: flex; justify-content: space-between; align-items: center; }}
        .site-tag {{ display: inline-block; background: #0c2340; color: #fff; font-size: 0.75rem; padding: 2px 8px; border-radius: 4px; }}
        .date-tag {{ font-size: 0.8rem; color: #888; }}
        .article-title {{ font-size: 1.05rem; font-weight: bold; color: #111; text-decoration: none; line-height: 1.4; }}
        .article-title:hover {{ color: #005c5c; text-decoration: underline; }}
        .orig-title {{ font-size: 0.8rem; color: #777; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>マリナーズ最新ニュース一覧</h1>
        <div class="subtitle">最終更新: {now_str} / 掲載件数: {len(articles_data)}件</div>
"""

  for art in articles_data:
    added_date = art.get("added_at", "")
    orig_title = art.get("orig_title", "")
    html_content += f"""
        <div class="card">
            <div class="meta-row">
                <span class="site-tag">{art['site']}</span>
                <span class="date-tag">{added_date}</span>
            </div>
            <a class="article-title" href="{art['link']}" target="_blank">{art['jp_title']} &rarr;</a>
            <div class="orig-title">{orig_title}</div>
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

  for site, url in MARINERS_ONLY_FEEDS.items():
    feed = fetch_feed(url)
    for entry in feed.entries[:15]:
      link = entry.get("link", "")
      if link and link not in seen_urls:
        seen_urls.add(link)
        new_candidates.append({
            "site": site,
            "title": entry.get("title", ""),
            "link": link,
        })

  for site, url in GENERAL_MLB_FEEDS.items():
    feed = fetch_feed(url)
    for entry in feed.entries[:30]:
      link = entry.get("link", "")
      if link and link not in seen_urls and is_mariners_article(entry):
        seen_urls.add(link)
        new_candidates.append({
            "site": site,
            "title": entry.get("title", ""),
            "link": link,
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

  print(
      f"Geminiに {len(target_articles)} 件のタイトルを一括送信します（API消費:"
      " 1回のみ）..."
  )
  response_text = batch_translate_titles(target_articles)

  jst = datetime.timezone(datetime.timedelta(hours=9))
  added_time_str = datetime.datetime.now(jst).strftime("%m/%d %H:%M取得")

  newly_parsed = []
  for line in response_text.strip().split("\n"):
    line = line.strip()
    if not line or "." not in line:
      continue
    try:
      num_str, jp_title = line.split(".", 1)
      idx = int(num_str.strip()) - 1
      if 0 <= idx < len(target_articles):
        orig = target_articles[idx]
        newly_parsed.append({
            "site": orig["site"],
            "jp_title": jp_title.strip(),
            "orig_title": orig["title"],
            "link": orig["link"],
            "added_at": added_time_str,
        })
    except Exception as ex:
      print(f"パース処理スキップ: {ex}")
      continue

  print(f"新たに {len(newly_parsed)} 件のタイトル翻訳が完了しました！")

  updated_articles = (newly_parsed + history_articles)[:MAX_DISPLAY_ARTICLES]
  save_history(updated_articles)
  generate_html(updated_articles)


if __name__ == "__main__":
  main()
