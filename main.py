import os
import time
import re
from bs4 import BeautifulSoup
from supabase import create_client, Client

# --- 🤖 Selenium関係 ---
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# --- 設定 ---
TARGET_URL = "https://portal.do-johodai.ac.jp/articles"
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
PORTAL_ID = os.environ.get("PORTAL_ID")
PORTAL_PASSWORD = os.environ.get("PORTAL_PASSWORD")

def setup_driver():
    print("🤖 ロボットブラウザ起動中...")
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

def login_and_scrape():
    if not SUPABASE_URL or not SUPABASE_KEY or not PORTAL_ID or not PORTAL_PASSWORD:
        print("❌ 設定不足: Secrets (URL, KEY, ID, PASSWORD) を確認してね")
        return

    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    driver = setup_driver()
    
    # 日付記録用 (UTC)
    from datetime import datetime, timezone
    current_run_time = datetime.now(timezone.utc).isoformat()
    
    try:
        # --- 1. ログイン処理 ---
        print(f"🔗 ポータル({TARGET_URL})にアクセス...")
        driver.get(TARGET_URL)
        
        # ログイン画面判定
        if "login" in driver.current_url or "kc.do-johodai" in driver.current_url or "sso" in driver.current_url:
            print("🔒 ログイン画面を検知！自動ログインします...")
            wait = WebDriverWait(driver, 15)
            
            # ID入力
            username_input = wait.until(EC.element_to_be_clickable((By.XPATH, "//input[@placeholder='ユーザー名' or @name='username' or @name='j_username']")))
            username_input.clear()
            username_input.send_keys(PORTAL_ID)
            
            # パスワード入力
            password_input = driver.find_element(By.XPATH, "//input[@placeholder='パスワード' or @name='password' or @name='j_password']")
            password_input.clear()
            password_input.send_keys(PORTAL_PASSWORD)
            
            # ログインボタン
            try:
                login_btn = driver.find_element(By.XPATH, "//button[contains(text(), 'ログイン') or @type='submit']")
                login_btn.click()
            except:
                password_input.submit()
            
            # 遷移待ち
            print("⏳ ログイン処理中...")
            time.sleep(10)
        
        # --- 2. ニュース取得ループ ---
        page = 1
        total_count = 0
        is_success = True

        while True:
            # ページ移動 (1ページ目は既に開いている可能性もあるけど念のため)
            if page > 1 or "page=" not in driver.current_url:
                current_page_url = f"{TARGET_URL}?page={page}"
                print(f"📄 Page {page} へ移動中... ({current_page_url})")
                driver.get(current_page_url)
                time.sleep(3) # 読み込み待ち

            # HTML解析
            soup = BeautifulSoup(driver.page_source, "html.parser")
            
            # カード取得
            cards = soup.find_all("div", class_="card-outline")
            
            if not cards:
                print(f"✅ Page {page}: 記事が見つかりませんでした。取得終了！")
                break

            page_items = []
            for card in cards:
                try:
                    category_tag = card.find("span", class_="badge")
                    category = category_tag.get_text(strip=True) if category_tag else "お知らせ"
                    
                    h3_tag = card.find("h3", class_="card-title")
                    if not h3_tag: continue
                    full_text = h3_tag.get_text(strip=True)
                    
                    # 日付抽出 [2024/01/01] 形式
                    date_match = re.search(r'\[(\d{4}/\d{2}/\d{2})\]', full_text)
                    if date_match:
                        published_at = date_match.group(1).replace("/", "-")
                        title = full_text.replace(category, "").replace(date_match.group(0), "").strip()
                    else:
                        published_at = "2026-01-01" # デフォルト
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
                            "category": category,
                            "last_seen_at": current_run_time
                        })
                except Exception as e:
                    print(f"⚠️ 解析エラー: {e}")
                    continue

            if not page_items:
                print("⚠️ カードはあるけどデータが取れませんでした。終了します。")
                break

            # DB保存
            for item in page_items:
                supabase.table("news").upsert(item, on_conflict="url").execute()
            
            print(f"💾 Page {page}: {len(page_items)}件 保存完了")
            total_count += len(page_items)
            page += 1

        # --- 3. お掃除機能 ---
        if is_success and total_count > 0:
            print("🧹 古いニュースのお掃除を開始...")
            # 今回の実行で更新されなかった(last_seen_atが古い)データを削除
            result = supabase.table("news").delete().neq("last_seen_at", current_run_time).execute()
            print(f"✨ お掃除完了！削除された件数: {len(result.data) if result.data else '不明'}")
        else:
            print("⚠️ ニュースが1件も取得できなかったため、安全のため削除処理をスキップしました。")

    except Exception as e:
        print(f"❌ 全体エラー: {e}")
    finally:
        driver.quit()
        print("👋 ブラウザを閉じました")

if __name__ == "__main__":
    login_and_scrape()