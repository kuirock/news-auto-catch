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
    options.add_argument('--window-size=1280,1024') # 画面サイズ指定（要素が見つかりやすくなる）
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

def perform_login(driver, wait):
    print("🔒 ログイン画面を検知！自動ログインします...")
    try:
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
        
        print("👆 ログインボタンを押しました。遷移を待ちます...")
        time.sleep(10) # 遷移待ち
        return True
    except Exception as e:
        print(f"❌ ログイン操作中にエラー: {e}")
        return False

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
        wait = WebDriverWait(driver, 20) # 待ち時間を20秒に延長

        # --- 1. アクセス & ログイン判定 ---
        print(f"🔗 ポータル({TARGET_URL})にアクセス...")
        driver.get(TARGET_URL)
        time.sleep(3) # 初期ロード待ち

        # ログインが必要かチェック (URLまたはページ内の要素で判断)
        # パスワード入力欄があればログイン画面とみなす
        is_login_page = len(driver.find_elements(By.XPATH, "//input[@type='password']")) > 0
        
        if is_login_page or "login" in driver.current_url or "sso" in driver.current_url:
            perform_login(driver, wait)
        
        # --- 2. ニュース取得ループ ---
        page = 1
        total_count = 0
        is_success = True

        while True:
            # ページ移動
            if page > 1:
                current_page_url = f"{TARGET_URL}?page={page}"
                print(f"📄 Page {page} へ移動中... ({current_page_url})")
                driver.get(current_page_url)
            
            # ★ 重要: 記事カードが表示されるまで待つ！
            try:
                # 記事カード(card-outline)が出るまで最大10秒待つ
                wait.until(EC.presence_of_element_located((By.CLASS_NAME, "card-outline")))
                time.sleep(2) # 念のため描画安定待ち
            except TimeoutException:
                # タイムアウト＝記事がない、または読み込み失敗
                print(f"⚠️ 待機しましたが記事が見つかりませんでした (Page {page})")
                # デバッグ用: ページのタイトルを表示
                print(f"   現在のページタイトル: {driver.title}")
                print(f"   現在のURL: {driver.current_url}")
                
                # もしここでまたログイン画面に戻ってたらリトライすべきかも？
                if len(driver.find_elements(By.XPATH, "//input[@type='password']")) > 0:
                    print("🚨 ログアウトされているようです！")
                    is_success = False
                break

            # HTML解析
            soup = BeautifulSoup(driver.page_source, "html.parser")
            cards = soup.find_all("div", class_="card-outline")
            
            if not cards:
                print(f"✅ Page {page}: カード要素なし。取得終了！")
                break

            page_items = []
            for card in cards:
                try:
                    # カテゴリ
                    category_tag = card.find("span", class_="badge")
                    category = category_tag.get_text(strip=True) if category_tag else "お知らせ"
                    
                    # タイトル・日付
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

                    # URL
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
                    print(f"⚠️ 解析スキップ: {e}")
                    continue

            if not page_items:
                break

            # DB保存
            for item in page_items:
                supabase.table("news").upsert(item, on_conflict="url").execute()
            
            print(f"💾 Page {page}: {len(page_items)}件 保存完了")
            total_count += len(page_items)
            page += 1

        # --- 3. お掃除機能 ---
        # 1件以上取得できた場合のみ実行（安全装置）
        if is_success and total_count > 0:
            print("🧹 古いニュースのお掃除を開始...")
            # 今回の実行で「見たよ(last_seen_at更新)」とならなかったデータを削除
            result = supabase.table("news").delete().neq("last_seen_at", current_run_time).execute()
            deleted_count = len(result.data) if result.data else 0
            print(f"✨ お掃除完了！削除された件数: {deleted_count}")
            
            if deleted_count == 0:
                print("   (削除対象はありませんでした)")
        else:
            print(f"⚠️ 取得件数が {total_count}件 のため、安全のため削除処理をスキップしました。")
            if not is_success:
                print("   (途中でエラーが発生した可能性があります)")

    except Exception as e:
        print(f"❌ 全体エラー: {e}")
        import traceback
        traceback.print_exc()
    finally:
        driver.quit()
        print("👋 ブラウザを閉じました")

if __name__ == "__main__":
    login_and_scrape()