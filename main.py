import os
import time
import requests
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

# --- 1. 設定 ---
# 最初にアクセスするのはポータルのニュース一覧
TARGET_URL = "https://portal.do-johodai.ac.jp/articles"

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
PORTAL_ID = os.environ.get("PORTAL_ID")
PORTAL_PASSWORD = os.environ.get("PORTAL_PASSWORD")

def get_fresh_cookie():
    print("🤖 ロボットブラウザ起動中...")
    
    options = Options()
    options.add_argument('--headless') 
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument(f"user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    
    try:
        # 1. まずポータルのニュースページに行ってみる
        print(f"🔗 ポータル({TARGET_URL})にアクセス...")
        driver.get(TARGET_URL)
        
        # 2. URLをチェック！ログイン画面に飛ばされたか？
        current_url = driver.current_url
        print(f"📍 現在のURL: {current_url}")

        # もしログイン画面（kc.do-johodai... や login...）にいたらログインを試みる
        if "login" in current_url or "kc.do-johodai" in current_url or "sso" in current_url:
            print("🔒 ログイン画面を検知！自動ログインを試みます...")
            
            wait = WebDriverWait(driver, 15)
            
            # --- 入力欄を探す作戦 ---
            # スクショを見た感じ、placeholder="ユーザー名" となっている可能性が高いので
            # XPathを使って「ユーザー名という文字が入ってる入力欄」を探すよ！
            
            # ユーザーID入力
            try:
                username_input = wait.until(EC.element_to_be_clickable((By.XPATH, "//input[@placeholder='ユーザー名' or @name='username' or @name='j_username']")))
                username_input.clear()
                username_input.send_keys(PORTAL_ID)
                print("✅ ID入力完了")
            except:
                print("⚠️ ID入力欄が見つかりません。HTMLが変わった可能性があります。")
                raise

            # パスワード入力
            try:
                password_input = driver.find_element(By.XPATH, "//input[@placeholder='パスワード' or @name='password' or @name='j_password']")
                password_input.clear()
                password_input.send_keys(PORTAL_PASSWORD)
                print("✅ パスワード入力完了")
            except:
                print("⚠️ パスワード入力欄が見つかりません。")
                raise

            # ログインボタンを押す（「ログイン」という文字が含まれるボタンを探す）
            try:
                login_button = driver.find_element(By.XPATH, "//button[contains(text(), 'ログイン') or @type='submit']")
                login_button.click()
                print("👆 ログインボタンをクリック！")
            except:
                # ボタンが見つからない場合、Enterキーで送信してみる
                password_input.submit()
                print("👆 (Enterキーで送信)")

            # 3. ログイン後のリダイレクトを待つ
            # ポータルのURLに戻ってくるまで待機
            print("⏳ ログイン処理中...")
            time.sleep(10) # 遷移待ち（長めに）

            print(f"📍 遷移後のURL: {driver.current_url}")
        
        # 4. Cookieを回収
        selenium_cookies = driver.get_cookies()
        cookie_dict = {}
        for cookie in selenium_cookies:
            cookie_dict[cookie['name']] = cookie['value']
            
        print("🍪 新鮮なCookieをゲットしました！")
        return cookie_dict

    except Exception as e:
        print(f"😱 ログイン失敗: {e}")
        return None
    finally:
        driver.quit()

def main():
    if not SUPABASE_URL or not SUPABASE_KEY or not PORTAL_ID or not PORTAL_PASSWORD:
        print("設定が足りないよ！Secrets (URL, KEY, ID, PASSWORD) を確認してね。")
        return

    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

    # ロボット出動！
    cookies = get_fresh_cookie()
    
    if not cookies:
        print("ログインに失敗したので終了します😭")
        return

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    # 日付記録用
    from datetime import datetime, timezone
    current_run_time = datetime.now(timezone.utc).isoformat()

    page = 1
    total_count = 0
    is_success = True

    while True:
        current_url = f"{TARGET_URL}?page={page}"
        print(f"--- 📄 Page {page} を解析中... ---")
        
        try:
            # さっきゲットしたCookieを使ってアクセス！
            response = requests.get(current_url, headers=headers, cookies=cookies, timeout=20)
            response.encoding = response.apparent_encoding
            
            soup = BeautifulSoup(response.text, "html.parser")
            
            # まだログイン画面にいるかチェック（突破失敗の可能性）
            if soup.title and ("Login" in soup.title.string or "ログイン" in soup.title.string):
                print("🚨 エラー: まだログイン画面にいます。突破に失敗しました💦")
                is_success = False
                break

            cards = soup.find_all("div", class_="card-outline")
            
            if not cards:
                print("ニュース取得完了！")
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
                            "category": category,
                            "last_seen_at": current_run_time
                        })
                except Exception as e:
                    continue

            if not page_items: break

            for item in page_items:
                supabase.table("news").upsert(item, on_conflict="url").execute()
            
            print(f"Page {page}: {len(page_items)}件 保存完了")
            total_count += len(page_items)
            time.sleep(1)
            page += 1

        except Exception as e:
            print(f"エラー: {e}")
            is_success = False
            break
            
    # お掃除機能（さっきのコードと同じ）
    if is_success and total_count > 0:
        try:
            supabase.table("news").delete().neq("last_seen_at", current_run_time).execute()
            print("🧹 古いニュースのお掃除完了！")
        except Exception as e:
            print(f"⚠️ お掃除エラー: {e}")

    print(f"✨ 処理終了！")

if __name__ == "__main__":
    main()