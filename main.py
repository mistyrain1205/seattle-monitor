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
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "あなたのAPIキーをここに貼る")
client = genai.Client(api_key=GEMINI_API_KEY)

HISTORY_FILE = "articles.json"  # 過去の記事データを保存するファイル
MAX_BATCH_SIZE = 30  # 1回のAPIリクエストでまとめて処理する最大記事数
MAX_DISPLAY_ARTICLES = 100  # HTMLに表示・保持する最大記事数

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
  """保存済みの過去記事データを読み込む"""
  if os.path.exists(HISTORY_FILE):
    try:
      with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        return json.load(f)
    except Exception as e:
      print(f"履歴読み込みエラー: {e}")
  return []


def save_history(articles):
  """記事データをJSONファイルに保存する"""
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


def extract_article_text(url, fallback_summary):
  try:
    downloaded = trafilatura.fetch_url(url)
    if downloaded:
      text = trafilatura.extract(downloaded)
      if text and len(text) > 200:
        return text[:1200]  # 30件まとめて送るため、1記事あたり1200文字に調整
  except Exception as e:
    print(f"本文抽出スキップ ({url}): {e}")
  return fallback_summary


def batch_translate_and_summarize(articles_batch):
  """最大30件の記事を1回のAPI呼び出しで一括翻訳・要約する"""
  batch_text = ""
  for i, art in enumerate(articles_batch, 1):
    batch_text += f"\n--- 記事ID: {i} ---\n"
    batch_text += f"掲載サイト: {art['site']}\n"
    batch_text += f"タイトル: {art['title']}\n"
    batch_text += f"本文: {art['content']}\n"

  prompt = f"""
あなたはMLB専門のスポーツライターです。以下の複数（最大{len(articles_batch)}件）の英語記事を、日本のマリナーズファン向けにそれぞれ翻訳・要約してください。

【出力ルール】
1. 各記事ごとに、必ず以下の形式（ID番号を含む）で出力してください。
[ARTICLE_START: 記事IDの数字]
■ （タイトルの自然な日本語訳）
・要点1
・要点2
・要点3
[ARTICLE_END]
2. 全記事を省略せず、入力された順番通りに出力してください。
3. セイバーメトリクス指標（wRC+, FIP, WARなど）や選手名はそのまま残してください。

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
  """蓄積されたデータからHTMLファイルを生成する"""
  # GitHub ActionsのサーバーはUTCなので、日本時間(+9時間)に変換して表示
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
        <div class="subtitle">最終更新: {now_str} / 掲載件数: {len(articles_data)}件</div>
"""

  for art in articles_data:
    added_date = art.get("added_at", "")
    html_content += f"""
        <div class="card">
            <div class="meta-row">
                <span class="site-tag">{art['site']}</span>
                <span class="date-tag">{added_date}</span>
            </div>
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
  # 1. 過去の履歴を読み込み、すでに処理済みのURLセットを作る
  history_articles = load_history()
  seen_urls = {art["link"] for art in history_articles}
  print(f"過去の保存済み記事: {len(history_articles)} 件")

  new_candidates = []

  # 2. 専用フィードから新着チェック（各サイト最大15件までスキャン）
  for site, url in MARINERS_ONLY_FEEDS.items():
    feed = fetch_feed(url)
    for entry in feed.entries[:15]:
      link = entry.get("link", "")
      if link and link not in seen_urls:
        seen_urls.add(link)  # 今回の実行内での重複も防止
        new_candidates.append({
            "site": site,
            "title": entry.get("title", ""),
            "link": link,
            "summary": entry.get("summary", ""),
        })

  # 3. 全体フィードから新着チェック（各サイト最大30件までスキャン）
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
            "summary": entry.get("summary", ""),
        })

  # 最大30件までに制限（1回のAPIリクエストで完結させるため）
  target_articles = new_candidates[:MAX_BATCH_SIZE]
  print(
      f"新着の未処理記事: {len(new_candidates)} 件中、今回処理するのは"
      f" {len(target_articles)} 件です。"
  )

  # 新着が0件ならAPIを叩かずにHTMLだけ更新して終了
  if not target_articles:
    print("新着記事がないため、Gemini APIは呼び出さずに終了します。")
    generate_html(history_articles)
    return

  # 4. 新着記事の本文を抽出
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

  # 5. まとめて1回のAPIリクエストで翻訳・要約
  print(
      f"Geminiに {len(raw_articles)} 件を一括送信します（API消費: 1回のみ）..."
  )
  response_text = batch_translate_and_summarize(raw_articles)

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
      # 記事IDから元の記事データを正確に紐付け
      art_idx = int(first_line.replace("]", "").strip()) - 1
      if art_idx < 0 or art_idx >= len(raw_articles):
        continue

      orig = raw_articles[art_idx]
      lines = [line.strip() for line in rest.split("\n") if line.strip()]

      jp_title = ""
      bullets = []
      for line in lines:
        if line.startswith("■"):
          jp_title = line.replace("■", "").strip()
        elif line.startswith("・"):
          bullets.append(f"<li>{line.replace('・','').strip()}</li>")

      if jp_title and bullets:
        newly_parsed.append({
            "site": orig["site"],
            "jp_title": jp_title,
            "link": orig["link"],
            "bullet_points": "".join(bullets),
            "added_at": added_time_str,
        })
    except Exception as ex:
      print(f"パース処理スキップ: {ex}")
      continue

  print(f"新たに {len(newly_parsed)} 件の記事の翻訳・要約が完了しました！")

  # 6. 新着記事を先頭にして過去の履歴と合体させ、保存＆HTML生成
  updated_articles = (newly_parsed + history_articles)[:MAX_DISPLAY_ARTICLES]
  save_history(updated_articles)
  generate_html(updated_articles)


if __name__ == "__main__":
  main()
