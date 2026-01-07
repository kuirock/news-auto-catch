import os
import requests
from bs4 import BeautifulSoup
from supabase import create_client, Client
import datetime

# --- 1. 設定 ---
# ポータルのトップページ (ここにニュースがある)
TARGET_URL = "https://portal.do-johodai.ac.jp/"

# 環境変数 (GitHub Secretsから読み込む)
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
PORTAL_COOKIE = os.environ.get("PORTAL_COOKIE")

def main():
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("Supabaseの鍵がないよ！")
        return
    if not PORTAL_COOKIE:
        print("Cookieがないよ！")
        return

    # Supabaseに接続
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

    # --- 2. Cookieを使ってアクセス ---
    cookies = {}
    try:
        for item in PORTAL_COOKIE.split(";"):
            if "=" in item:
                key, value = item.strip().split("=", 1)
                cookies[key] = value
    except Exception as e:
        print(f"Cookie変換エラー: {e}")
        return

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    print(f"Fetching: {TARGET_URL} ...")
    try:
        response = requests.get(TARGET_URL, headers=headers, cookies=cookies, timeout=20)
        response.encoding = response.apparent_encoding
        
        if response.status_code != 200:
            print(f"アクセス失敗💦 Status: {response.status_code}")
            return
    except Exception as e:
        print(f"接続エラー: {e}")
        return

    # --- 3. HTMLを解析 (ポータルサイト仕様) ---
    soup = BeautifulSoup(response.text, "html.parser")
    news_items = []

    # ニュースが表示されているテーブルを探す
    # クラス名 "table" を持つテーブルを探す
    news_table = soup.find("table", class_="table")

    if not news_table:
        print("ニュースのテーブルが見つからない💦 ログインできてるかな？")
        # 念のためタイトルを表示して確認
        print(f"現在のページタイトル: {soup.title.string if soup.title else '不明'}")
        return

    # テーブルの行(tr)を全部取得
    rows = news_table.find_all("tr")
    print(f"{len(rows)} 行のデータを発見！解析するよ...")

    for row in rows:
        try:
            # 各行のセル(td)を取得
            cols = row.find_all("td")
            
            # データが入っていない行（ヘッダーなど）はスキップ
            if len(cols) < 3:
                continue

            # 1列目: 日付 (例: 2026/01/07)
            date_text = cols[0].text.strip()
            # データベース用に / を - に変換 (2026-01-07)
            published_at = date_text.replace("/", "-")

            # 2列目: カテゴリ (例: 情報センター)
            # badgeクラスの中にテキストがある
            category_span = cols[1].find("span", class_="badge")
            category = category_span.text.strip() if category_span else "お知らせ"

            # 3列目: タイトルとリンク
            link_tag = cols[2].find("a")
            if not link_tag:
                continue
                
            title = link_tag.text.strip()
            url = link_tag.get("href")

            # URLが相対パスなら絶対パスに直す
            if url and not url.startswith("http"):
                 # もし /articles/... なら https://portal.do-johodai.ac.jp/articles/... にする
                url = "https://portal.do-johodai.ac.jp" + url

            # 保存データ作成
            news_data = {
                "published_at": published_at,
                "title": title,
                "url": url,
                "category": category,
            }
            
            news_items.append(news_data)
            print(f"取得: {published_at} [{category}] {title[:15]}...")

        except Exception as e:
            print(f"行の解析エラー: {e}")
            continue

    # --- 4. Supabaseに保存 ---
    if not news_items:
        print("保存するニュースがなかったよ💦")
        return

    print(f"{len(news_items)} 件のニュースを保存開始！")
    
    count = 0
    for news in news_items:
        try:
            # URLをキーにして、すでにあったら更新、なければ追加
            supabase.table("news").upsert(news, on_conflict="url").execute()
            count += 1
        except Exception as e:
            print(f"保存エラー: {e}")

    print(f"完了！ {count} 件のデータを更新したよ！🎉")

if __name__ == "__main__":
    main()