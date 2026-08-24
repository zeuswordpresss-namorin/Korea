#!/usr/bin/env python3
"""
로컬 PC에서 실행하는 스크립트. Blogger 발행 + Google 색인 생성 자동 요청에
필요한 리프레시 토큰(GOOGLE_REFRESH_TOKEN)을 한 번에 발급받습니다.

[중요] 기존에 Blogger 스코프만으로 발급받은 리프레시 토큰이 있더라도, "색인 생성 자동 요청"
기능을 쓰려면 이 스크립트를 다시 실행해서 indexing 스코프가 포함된 새 토큰으로 교체해야 합니다.

사전 준비:
1. Google Cloud Console → API 및 서비스 → 라이브러리에서 아래 2개 모두 사용 설정
   - Blogger API v3
   - Web Search Indexing API
2. 기존에 쓰던 OAuth 클라이언트(데스크톱 앱)의 Client ID / Client Secret 그대로 사용 가능
3. Search Console(https://search.google.com/search-console) → 설정 → 사용자 및 권한 →
   이 스크립트로 로그인할 Google 계정을 해당 속성(예: learnkoreanseekoreans.blogspot.com,
   또는 GitHub Pages 도메인)에 "소유자(Owner)"로 추가

실행 방법:
    pip install google-auth-oauthlib
    export BLOGGER_CLIENT_ID="xxxx.apps.googleusercontent.com"
    export BLOGGER_CLIENT_SECRET="xxxx"
    python scripts/get_refresh_token.py

브라우저가 열리면 로그인 후 권한을 허용하세요.
터미널에 출력되는 GOOGLE_REFRESH_TOKEN 값을 GitHub Secrets에 등록(교체)하면 됩니다.
"""

import os
from google_auth_oauthlib.flow import InstalledAppFlow

# [NEW] 기존 blogger 스코프에 indexing 스코프를 추가
SCOPES = [
    "https://www.googleapis.com/auth/blogger",
    "https://www.googleapis.com/auth/indexing",
]


def build_client_config() -> dict:
    client_id = os.environ.get("BLOGGER_CLIENT_ID")
    client_secret = os.environ.get("BLOGGER_CLIENT_SECRET")

    if not client_id or not client_secret:
        raise SystemExit(
            "BLOGGER_CLIENT_ID / BLOGGER_CLIENT_SECRET 환경변수를 먼저 설정하세요."
        )

    return {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }


def main() -> None:
    client_config = build_client_config()
    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    creds = flow.run_local_server(port=0)

    print("\n===== 아래 값을 GitHub Secrets(GOOGLE_REFRESH_TOKEN)에 등록/교체하세요 =====")
    print(f"GOOGLE_REFRESH_TOKEN={creds.refresh_token}")
    print("================================================================\n")
    print("주의: 기존 GOOGLE_REFRESH_TOKEN을 이 값으로 반드시 교체해야")
    print("색인 생성 자동 요청 기능이 동작합니다 (기존 토큰은 indexing 스코프가 없음).")


if __name__ == "__main__":
    main()
