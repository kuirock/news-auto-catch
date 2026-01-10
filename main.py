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
from selenium.webdriver.common.keys import Keys
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
PORTAL_COOKIE = os.environ.get("PORTAL_COOKIE") # 手動フォールバック用

def setup_driver():
    print("🤖 ロボットブラウザ起動中...")
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1280,1024')
    # ロボット検知回避
    options.add_argument('--disable-blink-features=AutomationControlled') 
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

# ★ DBから最新Cookieを取得
def get_cookie_from_db(supabase):
    try:
        # system_cookiesテーブルから 'portal_session' というキーを探す
        res = supabase.table('system_cookies').select('value').eq('key', 'portal_session').execute()
        if res.data and len(res.data) > 0:
            print("📦 DBから最新の自動更新Cookieが見つかりました！これを使います。")
            return res.data[0]['value']
    except Exception as e:
        print(f"⚠️ DBからのCookie取得失敗 (初回はなくてOK): {e}")
    return None

# ★ 最新CookieをDBに保存（わらしべ長者）
def save_cookie_to_db(driver, supabase):
    try:
        # SeleniumからCookieリストを取得
        cookies = driver.get_cookies()
        # 文字列に変換
        cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
        
        if not cookie_str:
            return

        # DBに上書き保存 (Upsert)
        supabase.table('system_cookies').upsert({
            'key': 'portal_session',
            'value': cookie_str,
            'updated_at': 'now()'
        }).execute()
        print("💾 最新のCookieをDBに保存しました！次回のロボットはこれを使います。")
    except Exception as e:
        print(f"❌ Cookieの保存に失敗: {e}")

def inject_cookies(driver, cookie_str):
    if not cookie_str:
        return False
    
    print("🍪 Cookieの注入を開始します...")
    try:
        driver.get(TOP_URL) # ドメインを合わせるためアクセス
        
        cookies = cookie_str.split(';')
        for cookie in cookies:
            if '=' in cookie:
                name, value = cookie.strip().split('=', 1)
                driver.add_cookie({
                    'name': name.strip(),
                    'value': value.strip(),
                    'domain': 'portal.do-johodai.ac.jp',
                    'path': '/'
                })
        print("✅ Cookie注入完了！")
        return True
    except Exception as e:
        print(f"❌ Cookie注入失敗: {e}")
        return False

def perform_google_login(driver, wait):
    print("🔒 Google SSOログインプロセス開始...")

    # 1. ポータルの「ログイン」ボタン
    try:
        portal_login_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'ログイン')] | //a[contains(text(), 'ログイン')]")))
        print("👆 ポータルの【ログイン】ボタンをクリック！")
        portal_login_btn.click()
    except TimeoutException:
        print("ℹ️ ポータルのログインボタンが見つかりません。")

    # 2. メールアドレス入力
    try:
        print("📧 Google: メールアドレス入力待ち...")
        email_input = wait.until(EC.visibility_of_element_located((By.XPATH, "//input[@type='email']")))
        email_input.clear()
        email_input.send_keys(PORTAL_ID)
        time.sleep(0.5)
        email_input.send_keys(Keys.RETURN)
        print("✅ メールアドレス送信")
    except TimeoutException:
        print("ℹ️ メールアドレス入力欄が出ませんでした（スキップ）")

    # 3. パスワード入力
    try:
        print("🔑 Google: パスワード入力待ち...")
        password_input = wait.until(EC.visibility_of_element_located((By.XPATH, "//input[@type='password']")))
        time.sleep(1)
        password_input.clear()
        password_input.send_keys(PORTAL_PASSWORD)
        time.sleep(0.5)
        password_input.send_keys(Keys.RETURN)
        print("✅ パスワード送信")
    except TimeoutException:
        print("ℹ️ パスワード入力欄が出ませんでした（スキップ）")

    print("⏳ ログイン処理完了待ち...")
    time.sleep(10)
    
    if "login" not in driver.current_url:
        print("🎉 ログイン成功！")
        return True
    else:
        print(f"⚠️ ログイン後のURLが怪しいです: {driver.current_url}")
        return False

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

        # --- 1. Cookie戦略 ---
        # 優先順位: ①DBの自動更新Cookie -> ②GitHub Secretsの手動Cookie
        target_cookie = get_cookie_from_db(supabase)
        if not target_cookie:
            print("ℹ️ DBにCookieがないため、手動Cookie(Secrets)を使用します。")
            target_cookie = PORTAL_COOKIE

        # Cookie注入
        inject_cookies(driver, target_cookie)
        
        # サイトへアクセス
        print(f"🔗 ニュース一覧({TARGET_URL})へ移動...")
        driver.get(TARGET_URL)
        time.sleep(3)

        # ログイン失敗判定
        current_url = driver.current_url
        is_login_page = "login" in current_url or "google" in current_url
        is_top_page = "/top/" in current_url 

        if is_login_page or is_top_page:
            print("⚠️ Cookieログインに失敗、または有効期限切れです。")
            
            if not PORTAL_ID or not PORTAL_PASSWORD:
                print("❌ ID/PASSがないため終了します。")
                return

            print("🔄 通常のログインフローを実行します...")
            perform_google_login(driver, wait)
            
            print("↩️ 再度ニュース一覧へ移動...")
            driver.get(TARGET_URL)
            time.sleep(5)

        # ★ ログイン成功したら、早速最新Cookieを保存しておく
        if "portal.do-johodai.ac.jp" in driver.current_url and "login" not in driver.current_url:
             save_cookie_to_db(driver, supabase)

        # --- 2. ニュース取得ループ ---
        page = 1
        total_count = 0
        is_success = True

        while True:
            # ページ移動
            if page > 1 or "articles" not in driver.current_url:
                driver.get(f"{TARGET_URL}?page={page}")
                time.sleep(2)
            
            try:
                # 記事カードが出るまで待つ
                wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".card-outline, .card")))
                time.sleep(2)
            except TimeoutException:
                print(f"⚠️ 記事が見つかりません (Page {page})")
                print(f"   URL: {driver.current_url}")
                # ログイン画面に戻されていたら終了
                if "login" in driver.current_url:
                    print("🚨 ログアウトされました。")
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
            print(f"✨ お掃除完了！削除された件数: {count}")
            
            # 最後にダメ押しで最新Cookie保存
            save_cookie_to_db(driver, supabase)
        else:
            print(f"⚠️ 取得数: {total_count}。削除スキップ。")

    except Exception as e:
        print(f"❌ エラー: {e}")
    finally:
        driver.quit()

if __name__ == "__main__":
    login_and_scrape()