import os
import requests
from bs4 import BeautifulSoup
from supabase import create_client, Client
import time # 👈 サーバーに優しくするために追加

# --- 1. 設定 ---
# ニュース記事一覧のベースURL
BASE_URL = "https://portal.do-johodai.ac.jp/articles"

# 環境変数
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
PORTAL_COOKIE = os.environ.get("PORTAL_COOKIE")

def main():
    if not SUPABASE_URL or not SUPABASE_KEY or not PORTAL_COOKIE:
        print("設定が足りないよ！Secretsを確認してね。")
        return

    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

    # Cookieの準備
    cookies = {}
    for item in PORTAL_COOKIE.split(";"):
        if "=" in item:
            key, value = item.strip().split("=", 1)
            cookies[key] = value

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    page = 1 # 👈 1ページ目からスタート！
    total_count = 0

    while True: # 👈 終わるまで無限ループ！
        current_url = f"{BASE_URL}?page={page}"
        print(f"--- 📄 Page {page} を解析中... ---")
        
        try:
            response = requests.get(current_url, headers=headers, cookies=cookies, timeout=20)
            if response.status_code != 200:
                print(f"これ以上ページがないか、エラーだよ。終了します。 (Status: {response.status_code})")
                break
            
            soup = BeautifulSoup(response.text, "html.parser")
            
            # ニュースのテーブルを探す
            news_table = soup.find("table", class_="table")
            if not news_table:
                print("ニュースが見つからなくなったよ。全件取得完了！")
                break

            rows = news_table.find_all("tr")
            page_items = []

            for row in rows:
                cols = row.find_all("td")
                if len(cols) < 3: continue

                date_text = cols[0].text.strip().replace("/", "-")
                category = cols[1].find("span", class_="badge").text.strip() if cols[1].find("span") else "お知らせ"
                link_tag = cols[2].find("a")
                
                if link_tag:
                    title = link_tag.text.strip()
                    url = link_tag.get("href")
                    if url and not url.startswith("http"):
                        url = "https://portal.do-johodai.ac.jp" + url
                    
                    page_items.append({
                        "published_at": date_text,
                        "title": title,
                        "url": url,
                        "category": category
                    })

            if not page_items:
                print("このページにニュースはもうないみたい。終了！")
                break

            # Supabaseに保存（1ページ分まとめて）
            for item in page_items:
                supabase.table("news").upsert(item, on_conflict="url").execute()
            
            print(f"Page {page}: {len(page_items)}件保存したよ！")
            total_count += len(page_items)

            # 🛑 サーバーに負荷をかけないように1秒休む（これ大事！）
            time.sleep(1)
            
            page += 1 # 👈 次のページへ！

        except Exception as e:
            print(f"エラー発生: {e}")
            break

    print(f"✨ 全作業完了！ 合計 {total_count} 件のニュースを同期したよ！")

if __name__ == "__main__":
    main()