import os
import requests
from bs4 import BeautifulSoup
from supabase import create_client, Client
import time
import re

# --- 1. 設定 ---
BASE_URL = "https://portal.do-johodai.ac.jp/articles"

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
PORTAL_COOKIE = os.environ.get("PORTAL_COOKIE")

def main():
    if not SUPABASE_URL or not SUPABASE_KEY or not PORTAL_COOKIE:
        print("設定が足りないよ！Secretsを確認してね。")
        return

    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

    # 文字列のCookieを辞書に変換
    cookies = {}
    for item in PORTAL_COOKIE.split(";"):
        if "=" in item:
            key, value = item.strip().split("=", 1)
            cookies[key] = value

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    page = 1
    total_count = 0

    while True:
        current_url = f"{BASE_URL}?page={page}"
        print(f"--- 📄 Page {page} を解析中... ---")
        
        try:
            response = requests.get(current_url, headers=headers, cookies=cookies, timeout=20)
            response.encoding = response.apparent_encoding 
            
            # ★ ログイン画面に飛ばされてないかチェック！ ★
            soup = BeautifulSoup(response.text, "html.parser")
            page_title = soup.title.string.strip() if soup.title else ""
            
            # Googleログイン画面やポータルのログイン画面に飛ばされていたらアウト
            if "Login" in page_title or "ログイン" in page_title or "Google" in page_title:
                print("🚨 エラー: ログイン画面に転送されました。Cookieの有効期限が切れています！")
                print("👉 GitHub Secrets の PORTAL_COOKIE を新しいものに更新してください。")
                break

            cards = soup.find_all("div", class_="card-outline")
            
            if not cards:
                print("これ以上ニュースがないか、取得できませんでした。")
                break

            page_items = []
            for card in cards:
                try:
                    category_tag = card.find("span", class_="badge")
                    category = category_tag.get_text(strip=True) if category_tag else "お知らせ"

                    h3_tag = card.find("h3", class_="card-title")
                    if not h3_tag: continue
                    full_text = h3_tag.get_text(strip=True)
                    
                    date_match = re.search(r'\[(\d{4}/\d{2}/\d{2})\]', full_text)
                    if date_match:
                        published_at = date_match.group(1).replace("/", "-")
                        title = full_text.replace(category, "").replace(date_match.group(0), "").strip()
                    else:
                        published_at = "2026-01-01"
                        title = full_text.replace(category, "").strip()

                    footer = card.find("div", class_="card-footer")
                    link_tag = footer.find("a") if footer else None
                    if link_tag:
                        url = link_tag.get("href")
                        if url and not url.startswith("http"):
                            url = "https://portal.do-johodai.ac.jp" + url
                        
                        page_items.append({
                            "published_at": published_at,
                            "title": title,
                            "url": url,
                            "category": category
                        })

                except Exception as e:
                    print(f"解析エラー: {e}")
                    continue

            if not page_items: break

            for item in page_items:
                supabase.table("news").upsert(item, on_conflict="url").execute()
            
            print(f"Page {page}: {len(page_items)}件保存完了")
            total_count += len(page_items)
            time.sleep(1)
            page += 1

        except Exception as e:
            print(f"通信エラー: {e}")
            break

    print(f"✨ 合計 {total_count} 件処理しました")

if __name__ == "__main__":
    main()