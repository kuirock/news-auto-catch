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
from selenium.common.exceptions import TimeoutException

# --- 設定 ---
TARGET_URL = "https://portal.do-johodai.ac.jp/articles"
TOP_URL = "https://portal.do-johodai.ac.jp/top/"

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
PORTAL_ID = os.environ.get("PORTAL_ID")
PORTAL_PASSWORD = os.environ.get("PORTAL_PASSWORD")
PORTAL_COOKIE = os.environ.get("PORTAL_COOKIE") # ★追加: 手動Cookie

def setup_driver():
    print("🤖 ロボットブラウザ起動中...")
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1280,1024')
    options.add_argument('--disable-blink-features=AutomationControlled') 
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

def inject_cookies(driver):
    if not PORTAL_COOKIE:
        print("ℹ️ 手動Cookie (PORTAL_COOKIE) が設定されていません。通常ログインを試みます。")
        return False
    
    print("🍪 手動Cookieの注入を開始します...")
    try:
        # Cookieをセットするには、まずそのドメインを開く必要がある（404でもいいからドメイン配下へ）
        # ここではトップページへ一旦アクセス
        driver.get(TOP_URL)
        
        # Cookie文字列 "key=value; key2=value2" を分解してセット
        cookies = PORTAL_COOKIE.split(';')
        for cookie in cookies:
            if '=' in cookie:
                name, value = cookie.strip().split('=', 1)
                driver.add_cookie({
                    'name': name,
                    'value': value,
                    'domain': 'portal.do-johodai.ac.jp',
                    'path': '/'
                })
        
        print("✅ Cookie注入完了！")
        return True
    except Exception as e:
        print(f"❌ Cookie注入失敗: {e}")
        return False

def perform_google_login(driver, wait):
    # (省略: さっきと同じログイン処理)
    print("🔒 Google SSOログインプロセス開始...")
    try:
        portal_login_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'ログイン')] | //a[contains(text(), 'ログイン')]")))
        portal_login_btn.click()
    except TimeoutException:
        print("ℹ️ ポータルのログインボタンが見つかりません。")

    try:
        email_input = wait.until(EC.visibility_of_element_located((By.XPATH, "//input[@type='email']")))
        email_input.clear()
        email_input.send_keys(PORTAL_ID)
        email_input.submit()
    except TimeoutException:
        pass

    try:
        password_input = wait.until(EC.visibility_of_element_located((By.XPATH, "//input[@type='password']")))
        time.sleep(1)
        password_input.clear()
        password_input.send_keys(PORTAL_PASSWORD)
        password_input.submit()
    except TimeoutException:
        pass

    time.sleep(10)
    return True

def login_and_scrape():
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("❌ Supabase設定不足")
        return

    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    driver = setup_driver()
    
    # 日付記録用 (UTC)
    from datetime import datetime, timezone
    current_run_time = datetime.now(timezone.utc).isoformat()
    
    try:
        wait = WebDriverWait(driver, 30)

        # --- 1. アクセス & ログイン ---
        # ★ Cookieがあれば注入してログインスキップを狙う
        cookie_injected = inject_cookies(driver)
        
        # ニュース一覧へ移動
        print(f"🔗 ニュース一覧({TARGET_URL})へ移動...")
        driver.get(TARGET_URL)
        time.sleep(3)

        # もしログイン画面やトップページに飛ばされたら、Cookieが無効だったということなので、通常ログイン
        current_url = driver.current_url
        is_login_page = "login" in current_url or "google" in current_url
        is_top_page = "/top/" in current_url # ニュースに行こうとしてトップに飛ばされた場合も失敗とみなす

        if is_login_page or is_top_page:
            print("⚠️ Cookieログインに失敗したか、有効期限切れのようです。")
            print(f"   現在のURL: {current_url}")
            
            if not PORTAL_ID or not PORTAL_PASSWORD:
                print("❌ ID/PASSがないためログインできません。終了します。")
                return

            print("🔄 通常のログインフローを実行します...")
            if is_top_page: 
                # トップにいるならログアウトボタンを探すか、一度ログイン画面に行く必要があるが
                # ログインボタンがあれば押す
                pass 
            
            perform_google_login(driver, wait)
            
            # 再度ニュースへ
            print("↩️ 再度ニュース一覧へ移動...")
            driver.get(TARGET_URL)
            time.sleep(5)

        # --- 2. ニュース取得ループ ---
        page = 1
        total_count = 0
        is_success = True

        while True:
            if page > 1 or "articles" not in driver.current_url:
                driver.get(f"{TARGET_URL}?page={page}")
                time.sleep(2)
            
            try:
                wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".card-outline, .card")))
                time.sleep(2)
            except TimeoutException:
                print(f"⚠️ 記事が見つかりません (Page {page})")
                print(f"   URL: {driver.current_url}")
                if page == 1:
                    print("❌ 1ページ目から取得できませんでした。終了。")
                    is_success = False
                break

            soup = BeautifulSoup(driver.page_source, "html.parser")
            valid_cards = [c for c in soup.select(".card-outline, .card") if c.find("h3") or c.find("a")]

            if not valid_cards:
                print("✅ これ以上記事がありません。")
                break

            page_items = []
            for card in valid_cards:
                try:
                    category_tag = card.find("span", class_="badge")
                    category = category_tag.get_text(strip=True) if category_tag else "お知らせ"
                    
                    h3_tag = card.find("h3", class_="card-title") or card.find("a")
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
                    link_tag = footer.find("a") if footer else card.find("a")

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
                except:
                    continue

            if not page_items: break

            for item in page_items:
                supabase.table("news").upsert(item, on_conflict="url").execute()
            
            print(f"💾 Page {page}: {len(page_items)}件 保存")
            total_count += len(page_items)
            page += 1

        # --- 3. お掃除機能 ---
        if is_success and total_count > 0:
            print("🧹 古いニュースのお掃除を開始...")
            result = supabase.table("news").delete().neq("last_seen_at", current_run_time).execute()
            count = len(result.data) if result.data else 0
            print(f"✨ お掃除完了！削除数: {count}")
        else:
            print(f"⚠️ 取得数: {total_count}。削除スキップ。")

    except Exception as e:
        print(f"❌ エラー: {e}")
    finally:
        driver.quit()

if __name__ == "__main__":
    login_and_scrape()