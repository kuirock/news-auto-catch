import os
import requests
from bs4 import BeautifulSoup
from supabase import create_client, Client

# --- 1. 設定 ---
# 大学のニュース一覧ページのURL (ここを自分の大学のものに変える！)
TARGET_URL = "https://www.do-johodai.ac.jp/news/" 

# Supabaseの設定 (あとでGitHubに登録するから今は空欄でもOK)
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

def main():
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("Supabaseの鍵がないよ！")
        return

    # Supabaseに接続
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

    # --- 2. 大学サイトにアクセス ---
    print(f"Fetching: {TARGET_URL}")
    response = requests.get(TARGET_URL)
    response.encoding = response.apparent_encoding # 文字化け対策

    if response.status_code != 200:
        print("サイトが開けなかった💦")
        return

    # --- 3. HTMLを解析 (ここが大学によって違う！) ---
    soup = BeautifulSoup(response.text, "html.parser")
    
    # 👇 ここが超重要！Chromeの検証ツールで、ニュースのリストが
    #    どういうタグ(ul, li, divなど)で書かれているか調べて書き換える必要があるよ！
    #    (以下はあくまで「よくある例」)
    news_items = []
    
    # 例: <ul class="news-list"> の中の <li> を探す
    news_list = soup.find("ul", class_="news-list") 
    
    if not news_list:
        print("ニュースのリストが見つからない💦 タグの設定を変えてみて！")
        return

    for item in news_list.find_all("li"):
        try:
            # 日付を取得 (例: <span class="date">2026.01.08</span>)
            date_text = item.find("span", class_="date").text.strip()
            
            # リンクとタイトルを取得 (例: <a href="...">タイトル</a>)
            link_tag = item.find("a")
            title = link_tag.text.strip()
            url = link_tag.get("href")
            
            # URLが相対パス(/news/...)なら絶対パス(https://...)にする
            if url.startswith("/"):
                url = "https://www.do-johodai.ac.jp" + url

            news_items.append({
                "published_at": date_text.replace(".", "-"), # 2026-01-08 の形式にする
                "title": title,
                "url": url,
                "category": "お知らせ", # カテゴリが取れなければ固定でもOK
            })
        except Exception as e:
            print(f"スキップしました: {e}")
            continue

    # --- 4. Supabaseに保存 ---
    print(f"{len(news_items)}件のニュースを見つけたよ！保存するね...")
    
    for news in news_items:
        try:
            # upsert = あれば更新、なければ新規追加
            supabase.table("news").upsert(news, on_conflict="url").execute()
        except Exception as e:
            print(f"保存エラー: {e}")

    print("完了！🎉")

if __name__ == "__main__":
    main()