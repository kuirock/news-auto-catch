import os
import requests
from bs4 import BeautifulSoup
from supabase import create_client, Client

# ポータルのトップページ（ニュースがある場所）
TARGET_URL = "https://portal.do-johodai.ac.jp/" 

# 環境変数
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
PORTAL_COOKIE = os.environ.get("PORTAL_COOKIE") # 👈 手形を受け取る

def main():
    if not PORTAL_COOKIE:
        print("Cookieがないよ！GitHub Secretsを設定してね！")
        return

    # --- 1. 手形（Cookie）を使ってアクセス ---
    # Cookieは "key=value; key2=value2" という文字列なので、辞書型に変換する
    cookies = {}
    try:
        for item in PORTAL_COOKIE.split(";"):
            if "=" in item:
                key, value = item.strip().split("=", 1)
                cookies[key] = value
    except Exception as e:
        print(f"Cookieの変換に失敗: {e}")
        return

    print(f"Fetching: {TARGET_URL} with Cookies...")
    
    # User-Agent（ブラウザのふりをする）
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    try:
        # cookiesを渡してアクセス！
        response = requests.get(TARGET_URL, headers=headers, cookies=cookies, timeout=20)
        response.encoding = response.apparent_encoding

        if response.status_code != 200:
            print(f"アクセス失敗💦 Status: {response.status_code}")
            # ログイン画面に飛ばされてるかも？
            print(f"URL: {response.url}")
            return

        # --- 2. 成功したらHTMLを確認 ---
        print("アクセス成功！🎉")
        
        # HTMLの一部を表示して、ニュースが含まれてるか確認したい
        # (ここから下は、HTMLが見れてから本気出す！)
        soup = BeautifulSoup(response.text, "html.parser")
        
        # タイトルを表示
        print(f"Page Title: {soup.title.string if soup.title else 'No Title'}")

        # 試しに「お知らせ」っぽい要素を探してみる（仮）
        # AdminLTE（ポータルのデザイン）によくある構造を探す
        news_candidates = soup.find_all(class_="box-title")
        print(f"ボックスのタイトル候補: {[t.text.strip() for t in news_candidates]}")

        # HTMLの中身を少しだけログに出す（デバッグ用）
        print("--- HTML DUMP (Head) ---")
        print(response.text[:1000]) # 最初の1000文字だけ

    except Exception as e:
        print(f"エラー発生: {e}")

if __name__ == "__main__":
    main()