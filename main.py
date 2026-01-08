import os
import requests
from bs4 import BeautifulSoup
from supabase import create_client, Client
import time
import re # 👈 日付を抜き出すために追加

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
            response.encoding = response.apparent_encoding # 文字化け防止
            
            if response.status_code != 200:
                print(f"これ以上ページがないか、エラーだよ。終了します。 (Status: {response.status_code})")
                break
            
            soup = BeautifulSoup(response.text, "html.parser")
            
            # ★ 修正ポイント：カード（div）を全部探す ★
            cards = soup.find_all("div", class_="card-outline")
            
            if not cards:
                print("ニュースが見つからなくなったよ。終了！")
                break

            page_items = []

            for card in cards:
                try:
                    # 1. カテゴリ
                    category_tag = card.find("span", class_="badge")
                    category = category_tag.get_text(strip=True) if category_tag else "お知らせ"

                    # 2. タイトルと日付 (h3タグの中)
                    h3_tag = card.find("h3", class_="card-title")
                    if not h3_tag: continue
                    
                    full_text = h3_tag.get_text(strip=True)
                    # カテゴリ名（学生SCとか）を消して、日付を抜き出す
                    # 例: "学生SC 【重要】日程について [2026/01/08]"
                    
                    # 日付 [YYYY/MM/DD] を探す
                    date_match = re.search(r'\[(\d{4}/\d{2}/\d{2})\]', full_text)
                    if date_match:
                        published_at = date_match.group(1).replace("/", "-")
                        # タイトルからカテゴリ名と日付部分を削る
                        title = full_text.replace(category, "").replace(date_match.group(0), "").strip()
                    else:
                        published_at = "2026-01-01" # 取れなかった時の予備
                        title = full_text.replace(category, "").strip()

                    # 3. URL
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
                        print(f"取得: {published_at} [{category}] {title[:15]}...")

                except Exception as e:
                    print(f"個別カードの解析エラー: {e}")
                    continue

            if not page_items:
                print("このページに有効なニュースがないよ。")
                break

            # 保存
            for item in page_items:
                supabase.table("news").upsert(item, on_conflict="url").execute()
            
            print(f"Page {page}: {len(page_items)}件保存完了！")
            total_count += len(page_items)

            # サーバーに優しくね！
            time.sleep(1.5)
            page += 1

        except Exception as e:
            print(f"エラー発生: {e}")
            break

    print(f"✨ 全作業完了！ 合計 {total_count} 件のニュースを同期したよ！")

if __name__ == "__main__":
    main()