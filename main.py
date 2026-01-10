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
    options.add_argument('--window-size=1280,1024')
    # ロボット検知回避
    options.add_argument('--disable-blink-features=AutomationControlled') 
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

def perform_google_login(driver, wait):
    print("🔒 Google SSOログインプロセス開始...")

    # 1. ポータルの「ログイン」ボタンをクリック
    try:
        portal_login_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'ログイン')] | //a[contains(text(), 'ログイン')]")))
        print("👆 ポータルの【ログイン】ボタンをクリック！")
        portal_login_btn.click()
    except TimeoutException:
        print("ℹ️ ポータルのログインボタンが見つかりません。すでにGoogle画面か、ログイン済みかも？")

    # 2. Google メールアドレス
    try:
        print("📧 Google: メールアドレス入力待ち...")
        email_input = wait.until(EC.visibility_of_element_located((By.XPATH, "//input[@type='email']")))
        email_input.clear()
        email_input.send_keys(PORTAL_ID)
        email_input.submit()
        print("✅ メールアドレス送信")
    except TimeoutException:
        print("ℹ️ メールアドレス入力欄が出ませんでした（スキップ）")

    # 3. Google パスワード
    try:
        print("🔑 Google: パスワード入力待ち...")
        password_input = wait.until(EC.visibility_of_element_located((By.XPATH, "//input[@type='password']")))
        time.sleep(1)
        password_input.clear()
        password_input.send_keys(PORTAL_PASSWORD)
        password_input.submit()
        print("✅ パスワード送信")
    except TimeoutException:
        print("ℹ️ パスワード入力欄が出ませんでした（スキップ）")

    # 4. 遷移待ち
    print("⏳ ログイン処理完了待ち...")
    time.sleep(10)
    
    # ログイン成功判定
    if "login" not in driver.current_url:
        print("🎉 ログイン成功！")
        return True
    else:
        print(f"⚠️ ログイン後のURLが怪しいです: {driver.current_url}")
        return False

def login_and_scrape():
    if not SUPABASE_URL or not SUPABASE_KEY or not PORTAL_ID or not PORTAL_PASSWORD:
        print("❌ 設定不足: Secretsを確認してね")
        return

    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    driver = setup_driver()
    
    # 日付記録用 (UTC)
    from datetime import datetime, timezone
    current_run_time = datetime.now(timezone.utc).isoformat()
    
    try:
        wait = WebDriverWait(driver, 30) # 待ち時間を30秒に延長！

        # --- 1. アクセス & ログイン ---
        print(f"🔗 ポータル({TARGET_URL})にアクセス...")
        driver.get(TARGET_URL)
        time.sleep(3)

        # ログインが必要かチェック
        is_portal_top = len(driver.find_elements(By.XPATH, "//button[contains(text(), 'ログイン')]")) > 0
        if "login" in driver.current_url or "google" in driver.current_url or is_portal_top:
            perform_google_login(driver, wait)
        
        # トップページにいたらニュース一覧へ移動
        if "/top/" in driver.current_url:
            print("↩️ トップページにいるため、ニュース一覧へ移動します...")
            driver.get(TARGET_URL)
            time.sleep(5)

        # --- 2. ニュース取得ループ ---
        page = 1
        total_count = 0
        is_success = True

        while True:
            # ページ移動
            if page > 1 or "articles" not in driver.current_url:
                current_page_url = f"{TARGET_URL}?page={page}"
                print(f"📄 Page {page} へ移動中... ({current_page_url})")
                driver.get(current_page_url)
            
            try:
                # ★ 記事カードが出るまで待つ (card-outline または card)
                wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".card-outline, .card")))
                time.sleep(3) # 描画完了待ち
            except TimeoutException:
                print(f"⚠️ 待機しましたが記事が見つかりませんでした (Page {page})")
                print(f"   現在のURL: {driver.current_url}")
                print(f"   ページタイトル: {driver.title}")
                
                # ▼ デバッグ用: HTMLの最初の方を表示して、どんな状態か確認する
                html_snippet = driver.page_source[:500].replace('\n', ' ')
                print(f"   HTML抜粋: {html_snippet}...")

                # ★ リトライ: 1ページ目なら一度だけリロードしてみる
                if page == 1:
                    print("🔄 ページをリロードして再試行します...")
                    driver.refresh()
                    time.sleep(5)
                    try:
                        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".card-outline, .card")))
                    except:
                        print("❌ リロードしてもダメでした。")
                        # ログイン画面に戻されてないかチェック
                        if "login" in driver.current_url:
                            print("🚨 ログアウトされています。")
                            is_success = False
                        break
                else:
                    break

            # HTML解析
            soup = BeautifulSoup(driver.page_source, "html.parser")
            # セレクタを少し広めに設定
            cards = soup.select(".card-outline, .card")
            
            # カードの中身が空っぽじゃないかチェック
            valid_cards = [c for c in cards if c.find("h3") or c.find("a")]

            if not valid_cards:
                print("✅ 記事カードが見つかりません。取得終了！")
                break

            page_items = []
            for card in valid_cards:
                try:
                    category_tag = card.find("span", class_="badge")
                    category = category_tag.get_text(strip=True) if category_tag else "お知らせ"
                    
                    h3_tag = card.find("h3", class_="card-title")
                    if not h3_tag:
                        # h3がない場合、aタグの中身を探すなどフォールバック
                        h3_tag = card.find("a")
                    
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
                    
                    # footerになければカード全体からリンクを探す
                    if not link_tag:
                        link_tag = card.find("a")

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
                    print(f"⚠️ 解析スキップ: {e}")
                    continue

            if not page_items: break

            for item in page_items:
                supabase.table("news").upsert(item, on_conflict="url").execute()
            
            print(f"💾 Page {page}: {len(page_items)}件 保存完了")
            total_count += len(page_items)
            page += 1

        # --- 3. お掃除機能 ---
        if is_success and total_count > 0:
            print("🧹 古いニュースのお掃除を開始...")
            result = supabase.table("news").delete().neq("last_seen_at", current_run_time).execute()
            count = len(result.data) if result.data else 0
            print(f"✨ お掃除完了！削除された件数: {count}")
        else:
            print(f"⚠️ 取得件数: {total_count}。安全のため削除はスキップします。")

    except Exception as e:
        print(f"❌ エラー発生: {e}")
        import traceback
        traceback.print_exc()
    finally:
        driver.quit()
        print("👋 ブラウザ終了")

if __name__ == "__main__":
    login_and_scrape()