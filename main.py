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
    options.add_argument('--disable-blink-features=AutomationControlled') 
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

# ★ 新機能: DBから最新Cookieを取得
def get_cookie_from_db(supabase):
    try:
        res = supabase.table('system_cookies').select('value').eq('key', 'portal_session').execute()
        if res.data and len(res.data) > 0:
            print("📦 DBから最新の自動更新Cookieが見つかりました！これを使います。")
            return res.data[0]['value']
    except Exception as e:
        print(f"⚠️ DBからのCookie取得失敗: {e}")
    return None

# ★ 新機能: 最新CookieをDBに保存（わらしべ長者）
def save_cookie_to_db(driver, supabase):
    try:
        # SeleniumからCookieリストを取得
        cookies = driver.get_cookies()
        # "key=value; key2=value2" 形式の文字列に変換
        cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
        
        if not cookie_str:
            print("⚠️ 保存するCookieがありませんでした。")
            return

        # DBに保存
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
    # ... (前と同じログイン処理) ...
    # ログイン成功後にもCookieを保存するチャンスがあるので、戻り値で判定
    print("🔒 Google SSOログイン...")
    # (中略: エラー回避のため省略しますが、前のコードの perform_google_login と同じ内容でOK)
    # ...
    # 最後に
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

        # --- 1. Cookie戦略 ---
        # 優先順位: ①DBの自動更新Cookie -> ②GitHub Secretsの手動Cookie
        target_cookie = get_cookie_from_db(supabase)
        if not target_cookie:
            print("ℹ️ DBにCookieがないため、手動Cookie(Secrets)を使用します。")
            target_cookie = PORTAL_COOKIE

        # Cookie注入
        cookie_injected = inject_cookies(driver, target_cookie)
        
        # サイトへアクセス
        print(f"🔗 ニュース一覧({TARGET_URL})へ移動...")
        driver.get(TARGET_URL)
        time.sleep(3)

        # ログイン失敗判定
        current_url = driver.current_url
        if "login" in current_url or "google" in current_url or "/top/" in current_url:
            print("⚠️ Cookieが無効です。通常ログインを試みます...")
            # ここで perform_google_login を呼ぶ (省略時は前のコード参照)
            # ログイン成功したら...
            pass

        # ★ ここで「わらしべ長者」発動！
        # ログイン（またはCookie通過）に成功してポータル内にいるなら、最新Cookieを保存！
        if "portal.do-johodai.ac.jp" in driver.current_url and "login" not in driver.current_url:
             save_cookie_to_db(driver, supabase)

        # --- 2. ニュース取得ループ (変更なし) ---
        # ... (前回のスクレイピングコードと同じ) ...
        # ...
        # ...
        # (最後のfinallyの前にもう一度保存しておくと安心)
        save_cookie_to_db(driver, supabase)

    except Exception as e:
        print(f"❌ エラー: {e}")
    finally:
        driver.quit()

if __name__ == "__main__":
    login_and_scrape()