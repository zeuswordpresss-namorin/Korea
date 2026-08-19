# -*- coding: utf-8 -*-
"""
GitHub Actions 위에서 실행되는 자동 블로그 파이프라인 스크립트 (통합판)

[전면 개편] "한국어를 배우면 한국인이 보인다" - 외국인 대상 한국어 표현·한국인 사고방식 블로그
- 주인공은 단어가 아니라 한국인의 사고방식과 문화 (번역이 어려운 감정 / 매일 쓰는 말 / 한국 문화 / 리액션)
- 매 글 고정 5단 템플릿 사용: 오늘의 표현 -> 왜 직역이 안 될까 -> 한국인은 언제 쓸까 -> 문화 이야기 -> 참여형 질문
- 에버그린 주제 뱅크(100개 표현/문화 주제, 4개 카테고리 요일별 로테이션) 기반, 하루 6회 발행 상한
- [업그레이드] 방문자 언어 감지 자동 번역 (버튼 숨김) 및 표 1.5배 확대 기능
"""

import base64
import hashlib
import hmac
import io
import json
import logging
import os
import random
import re
import subprocess
import sys
import textwrap
import time
import urllib.parse
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple

import requests
from PIL import Image, ImageDraw, ImageFont

# =====================================================================
# 로깅 설정
# =====================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

# =====================================================================
# 큐 파일 설정
# =====================================================================
QUEUE_FILE = "keywords_queue.json"

# =====================================================================
# 환경변수로 받는 설정값
# =====================================================================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
SITE_TITLE = os.environ.get("SITE_TITLE", "오늘의 한국어")
SITE_TAGLINE = os.environ.get("SITE_TAGLINE", "한국어를 배우면 한국인이 보인다 - 외국인을 위한 한국어 표현과 사고방식")
SITE_URL = os.environ.get("SITE_URL", "").rstrip("/")
GA_MEASUREMENT_ID = os.environ.get("GA_MEASUREMENT_ID", "")
GOOGLE_SITE_VERIFICATION = os.environ.get("GOOGLE_SITE_VERIFICATION", "")
ADSENSE_CLIENT_ID = os.environ.get("ADSENSE_CLIENT_ID", "")
ADSENSE_SLOT_ID = os.environ.get("ADSENSE_SLOT_ID", "")

COUPANG_PARTNER_TAG = os.environ.get("COUPANG_PARTNER_TAG", "")
COUPANG_ACCESS_KEY = os.environ.get("COUPANG_ACCESS_KEY", "")
COUPANG_SECRET_KEY = os.environ.get("COUPANG_SECRET_KEY", "")

BLOGGER_BLOG_ID = os.environ.get("BLOGGER_BLOG_ID", "")
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REFRESH_TOKEN = os.environ.get("GOOGLE_REFRESH_TOKEN", "")

# --- [NEW] Canva 무료 플랜 연동 방식 ---
# Canva의 Autofill API(템플릿 자동 채우기)는 Canva Teams(유료) 전용 기능이라 무료 플랜에서는
# 쓸 수 없다. 대신 "배경 디자인은 Canva에서 직접 만들어 내보내고, 표현 텍스트만 코드로 자동으로
# 얹는" 방식을 쓴다. API 키/인증이 전혀 필요 없다.
# 준비물: 카테고리별로 Canva에서 1280x720 배경을 디자인한 뒤 PNG로 내보내(다운로드) 아래 폴더에
# 정확히 이 파일명으로 넣어두면 된다. 없으면 기존 방식(랜덤 그라데이션)으로 자동 대체된다.
#   canva_backgrounds/번역감정.png
#   canva_backgrounds/일상표현.png
#   canva_backgrounds/한국문화.png
#   canva_backgrounds/리액션.png
CANVA_BG_DIR = os.environ.get("CANVA_BG_DIR", "canva_backgrounds")

# --- [NEW] 워드프레스 동시 자동 발행 관련 환경변수 ---
# [FIX] *.wordpress.com 호스팅 블로그(예: kresonate.wordpress.com)는 자체 호스팅 워드프레스와
# 완전히 다른 API(public-api.wordpress.com)를 쓰고, Basic Auth(Application Password)가 아니라
# OAuth2만 지원합니다. 그래서 WORDPRESS_CLIENT_ID/SECRET이 설정되면 워드프레스닷컴 OAuth2 방식을,
# 없으면 자체 호스팅용 Basic Auth 방식(wp-json/wp/v2)을 자동으로 사용합니다.
WORDPRESS_URL = os.environ.get("WORDPRESS_URL", "").rstrip("/")          # 예: kresonate.wordpress.com 또는 https://myblog.com
WORDPRESS_USERNAME = os.environ.get("WORDPRESS_USERNAME", "")            # 워드프레스 로그인 아이디
WORDPRESS_APP_PASSWORD = os.environ.get("WORDPRESS_APP_PASSWORD", "")    # Application Password (워드프레스닷컴은 계정보안>2단계인증 페이지에서 발급)
# 워드프레스닷컴 전용: https://developer.wordpress.com/apps/new/ 에서 앱 등록 후 발급되는 값
WORDPRESS_CLIENT_ID = os.environ.get("WORDPRESS_CLIENT_ID", "")
WORDPRESS_CLIENT_SECRET = os.environ.get("WORDPRESS_CLIENT_SECRET", "")

# --- [NEW] 네이버 블로그 자동 발행 관련 환경변수 ---
# 주의: 네이버 '글쓰기 오픈API'(writePost)는 2020-05-06자로 공식 종료되어 더 이상 사용할 수 없습니다.
# 따라서 아래는 Playwright 브라우저 자동화(로그인 → 글쓰기 화면 조작) 방식을 사용합니다.
FONT_CANDIDATES = [
    "font.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothic-Bold.ttf",
    # [FIX] 나눔고딕 설치가 실패할 경우를 대비한 2차 후보 (Noto Sans CJK, 한글 지원)
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
]

DOCS_DIR = "docs"
POSTS_DIR = os.path.join(DOCS_DIR, "posts")
POSTS_JSON = os.path.join(DOCS_DIR, "posts.json")

GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.5-flash:generateContent?key={api_key}"
)

# [전면 개편] "한국어를 배우면 한국인이 보인다" - 고정 5단 템플릿 기반 한국어 표현/문화 콘텐츠
SYSTEM_PROMPT = """당신은 외국인에게 한국어와 한국인의 사고방식을 설명하는 전문 에디터입니다.
이 블로그의 콘셉트는 "한국어를 배우면 한국인이 보인다"입니다. 주인공은 단어가 아니라, 그 단어 뒤에 숨은 한국인의 사고방식과 문화입니다.
독자는 한국어를 배우는 외국인이며, 사전적 정의가 아니라 "왜 이 표현이 그 나라 말로는 설명이 안 되는지", "실제 한국인은 언제 이 말을 쓰는지"를 궁금해합니다.

[필수 포맷 구조 — 반드시 이 5단 구성과 순서를 그대로 지켜서 html_body를 작성한다]
1. 오늘의 표현 — 표현(한국어 원문), 뜻(간결한 설명), 사용 맥락(누구에게/어떤 상황에 쓰는지)을 h2 아래 정리
2. 왜 영어로 직역이 안 될까? — 영어(또는 다른 언어)의 가장 가까운 단어를 대며, 그 단어로는 못 담아내는 한국인만의 뉘앙스를 설명
3. 한국인은 어떤 상황에서 쓸까? — 실제 대화체에 가까운 일상 예시 1~2개 (누가, 어떤 상황에서, 어떤 말투로 썼는지)
4. 문화 이야기 — 이 표현이 한국 사회/관계 맺는 방식과 어떻게 연결되는지, 배경과 맥락을 짧게
5. 여러분의 언어에서는 어떤가요? — 반드시 참여형 질문 1~2개로 마무리해 댓글을 유도한다 (예: "여러분의 언어에도 이런 단어가 있나요?", "비슷한 감정을 뭐라고 표현하시나요?")

아래 규칙을 지켜 작성하세요:
1. 제목은 영어 검색 키워드형으로 작성한다. (예: "Why "정(Jeong)" Has No English Equivalent", "The Real Meaning of "눈치" (Nunchi)", "Why Koreans Say "수고했어요" So Often") 표현의 한국어 원문을 반드시 제목에 쌍따옴표(" ")로 감싸 포함시키고, 25~55자 내외로 작성한다.
1-1. meta_description은 검색결과 스니펫에 노출되는 요약문이다. 표현을 앞부분에 배치하고, "이 표현의 뜻과 왜 번역이 안 되는지를 알 수 있다"는 점이 드러나게 100~140자 내외로 작성한다.
2. 소제목(H2)은 정확히 위 5단 구조(오늘의 표현 / 왜 영어로 직역이 안 될까? / 한국인은 어떤 상황에서 쓸까? / 문화 이야기 / 여러분의 언어에서는 어떤가요?)를 그대로 사용한다. 순서와 문구를 임의로 바꾸지 않는다.
3. [문체/가독성 — 매우 중요] 다음 AI 특유의 어색한 말투를 피한다:
   - 모든 문단을 "~일까요?", "~습니다!" 같은 같은 패턴으로 끝맺지 말고 평서문/의문문/짧은 문장을 자연스럽게 섞는다.
   - 같은 내용을 표현만 바꿔 반복하지 않는다(패딩 금지). 한 문단에서 한 이야기를 하면 다음 문단은 반드시 새로운 정보로 넘어간다.
   - "정말", "충격적인", "놀라운" 같은 과장 수식어는 글 전체에서 1~2회 이하로 아껴 쓴다.
   - 문단은 2~4문장, 대략 60~90자 내외로 짧게 끊어 모바일 가독성을 높인다.
   - 친한 친구에게 설명하듯 구체적 사례·대화 예시 위주로 쓰고, 막연한 감탄으로 문단을 채우지 않는다.
4. [친근한 톤앤매너] 전체적으로 친근하고 공감대를 형성하는 어조를 유지한다. 독자를 "여러분"으로 자연스럽게 지칭하며, 딱딱한 설명체가 아니라 대화하듯 풀어쓴다.
5. 글자 수는 900~1400자 내외 (모바일에서 가볍게 읽히는 짧은 분량을 지향한다).
6. "왜 영어로 직역이 안 될까?" 섹션에는 표현의 한국어 원문을 최소 1회 굵게(strong) 강조한다.
7. "한국인은 어떤 상황에서 쓸까?" 섹션은 <ul> 목록으로 예시 1~2개를 정리한다.
8. schema_type은 항상 "Article"로 고정한다. faq_items와 howto_steps는 항상 빈 배열로 둔다.
9. 제목/키워드를 보고 카테고리 중 가장 알맞은 것 하나를 "category"에 고른다: ["번역감정", "일상표현", "한국문화", "리액션"]
   - 번역감정: 정, 눈치, 아쉽다처럼 영어로 옮기기 어려운 감정·정서 단어
   - 일상표현: 괜찮아요, 수고했어요처럼 한국인이 매일 쓰는 관용적 인사·말
   - 한국문화: 나이 문화, 회식 문화, 존댓말처럼 표현 뒤에 있는 문화적 배경/관습
   - 리액션: 헐, 대박, 아이고처럼 한국인 특유의 감탄사·반응 표현
10. product_keyword와 product_list는 이 블로그와 무관하므로 항상 빈 문자열("")과 빈 배열([])로 둔다.
11. "image_keywords"에는 이 글의 썸네일/본문 이미지로 쓸 무료 스톡사진을 검색하기 위한 영어 키워드 2~4단어를 넣는다.
   [매우 중요] 한국어 표현을 그대로 번역하지 말 것. 스톡사진 사이트에는 한국 특유의 단어를 나타내는 사진이 없으므로,
   그 감정/상황이 드러나는 사람들의 모습을 보편적인 영어로 묘사한다. (예: 표현이 "눈치"라면
   "friends reading social cues" 처럼, 표현이 "정"이라면 "close friends warm moment" 처럼 실제 촬영 가능한 보편적 장면으로 변환한다.)
12. "expression"에는 "오늘의 표현"에서 다루는 한국어 표현의 순수 원문만 담는다. 설명·이모지·괄호 없이 단어/구절 그대로. (예: "민망하다", "정", "수고했어요")
13. 출력은 반드시 아래 JSON 형식만 반환한다. 다른 설명, 코드블록 기호(```) 없이 순수 JSON만 출력한다:
{
  "title": "...",
  "html_body": "...",
  "meta_description": "...",
  "schema_type": "Article",
  "faq_items": [],
  "howto_steps": [],
  "category": "위 4개 중 하나",
  "product_keyword": "",
  "product_list": [],
  "image_keywords": "영어 스톡사진 검색어 2~4단어",
  "expression": "표현의 한국어 원문만"
}
html_body는 5단 구조를 <h2>, <p>, <ul>, <strong> 등을 사용한 HTML 조각으로 작성한다."""

CATEGORY_THEMES = {
    # --- [전면 개편] "한국어를 배우면 한국인이 보인다" 4대 카테고리 ---
    "번역감정": {"gradient": [(233, 92, 132), (247, 158, 173), (255, 205, 210)], "accent": "#e95c84", "badge": "💗 번역이 안 되는 감정", "label": "EMOTION", "font": "Gowun+Dodum", "decor": ["💗", "😌", "🥲", "💭", "😳", "🫠", "😔", "✨"]},
    "일상표현": {"gradient": [(46, 134, 171), (99, 179, 197), (163, 217, 219)], "accent": "#2e86ab", "badge": "💬 매일 쓰는 말", "label": "PHRASE", "font": "Noto+Sans+KR:wght@700", "decor": ["💬", "👋", "🙏", "😊", "🗣️", "📢", "✅", "🤝"]},
    "한국문화": {"gradient": [(150, 40, 27), (196, 84, 39), (231, 156, 92)], "accent": "#96281b", "badge": "🇰🇷 한국 문화", "label": "CULTURE", "font": "Jua", "decor": ["🇰🇷", "🏮", "🥢", "🍶", "🎎", "🏯", "🎏", "🪭"]},
    "리액션": {"gradient": [(255, 154, 60), (255, 194, 92), (255, 226, 130)], "accent": "#ff9a3c", "badge": "😲 한국인의 리액션", "label": "REACTION", "font": "Jua", "decor": ["😲", "🤯", "😂", "😱", "🙌", "👀", "🔥", "💯"]},
}
DEFAULT_THEME = CATEGORY_THEMES["번역감정"]

def get_theme(category: str) -> Dict[str, Any]:
    return CATEGORY_THEMES.get(category, DEFAULT_THEME)

# --- [전면 개편] 무료 AI 생성 2D 시그니처 캐릭터 삽화 (말풍선 대화 만화 스타일) ---
# Pexels 유료 API 키 없이도 항상 그림이 생성되도록, API 키가 필요 없는 무료 AI 이미지 생성
# 서비스(Pollinations.ai)로 "하늘이" 라는 고정 시그니처 캐릭터가 말풍선으로 대화하는
# 2D 플랫 카툰 삽화를 만듭니다. 카테고리별로 장면과 톤만 다르게 구성해 시리즈 일관성을 유지합니다.
SIGNATURE_CHARACTER = (
    "a cute minimalist 2D cartoon mascot character named Haneul-i, round soft face, big round eyes, "
    "simple flat-color vector illustration, warm rounded shapes, soft pastel color palette, "
    "consistent recurring comic-strip mascot"
)
ILLUSTRATION_PROMPTS = {
    "번역감정": (
        f"{SIGNATURE_CHARACTER} acting out a short situational skit — leaning toward a friend character with a "
        "shy warm smile, one hand rubbing the back of the neck, gentle motion lines showing a small shuffle, "
        "a speech bubble containing a small pink heart and sparkle emoji floating above the scene, soft pink and cream tones"
    ),
    "일상표현": (
        f"{SIGNATURE_CHARACTER} acting out a short situational skit — waving energetically at a friend character "
        "passing by on a street, both captured mid-step with dynamic motion lines, a speech bubble containing a "
        "check mark and small wave emoji, cheerful soft blue and teal tones"
    ),
    "한국문화": (
        f"{SIGNATURE_CHARACTER} acting out a short situational skit — bowing slightly at a low traditional Korean "
        "table filled with small side dishes, a friend character passing a bowl, motion lines showing a respectful "
        "nod, a speech bubble containing a lantern and rice bowl emoji, warm terracotta and cream tones"
    ),
    "리액션": (
        f"{SIGNATURE_CHARACTER} acting out a short situational skit — jumping backward with both arms flailing and "
        "mouth wide open in shock, sweat drop and exclamation mark emoji flying out of a big speech bubble, dramatic "
        "radiating motion lines, bright orange and yellow tones"
    ),
}
ILLUSTRATION_SUFFIX = ", flat 2D comic illustration, clean vector art, flat colors, thick clean outlines, no text, no watermark, high quality digital illustration"

# --- Pexels 무료 스톡 이미지 (2차 폴백 전용) ---
# 1차: 무료 AI 시그니처 캐릭터 생성(API 키 불필요) → 실패 시 2차: Pexels 스톡사진(API 키 설정된 경우만)
# → 최종 폴백: 그라데이션 배경. 준비물(선택): https://www.pexels.com/api/ 에서 무료 키 발급.
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", "")
STOCK_SEARCH_TERMS = {
    "번역감정": "korean friends emotional moment",
    "일상표현": "korean people talking conversation",
    "한국문화": "korean traditional culture family",
    "리액션": "korean people surprised reaction",
}


# =====================================================================
# [전면 개편] 에버그린 주제 뱅크 (100개) + 큐 관리
# - "한국어를 배우면 한국인이 보인다" 콘셉트에 맞춰 4대 카테고리(번역감정/일상표현/한국문화/리액션)
#   각 25개씩 총 100개 주제로 구성. 각 항목은 EVERGREEN_TOPIC_BANK의 "주제(한국어 표현/문화 키워드)"이며,
#   실제 제목·본문은 SYSTEM_PROMPT의 5단 템플릿에 따라 생성됩니다.
# - CATEGORY_WEIGHT: 4개 카테고리를 균등하게 순환시켜 특정 카테고리로 편중되지 않게 합니다.
# =====================================================================
EVERGREEN_TOPIC_BANK: Dict[str, List[str]] = {
    "번역감정": [
        "정(情)", "눈치", "아쉽다", "답답하다", "서운하다", "민망하다", "섭섭하다", "허전하다",
        "애틋하다", "짠하다", "뭉클하다", "억울하다", "속상하다", "찜찜하다", "든든하다", "오지랖",
        "시원섭섭하다", "얄밉다", "한(恨)", "흥", "궁상맞다", "유난스럽다", "정떨어지다", "애매하다",
        "마음이 놓이다",
    ],
    "일상표현": [
        "괜찮아요", "수고했어요", "잘 먹겠습니다", "잘 먹었습니다", "다녀오겠습니다", "고생했어요",
        "밥 한번 먹자", "조심히 들어가세요", "수고하셨습니다", "잘 지내시죠", "식사하셨어요",
        "다음에 봐요", "신경 쓰지 마세요", "별말씀을요", "그러게요", "죄송한데요", "괜찮으시면",
        "바쁘시죠", "힘내세요", "조심하세요", "축하드려요", "화이팅", "신경 좀 써주세요",
        "감사합니다 정말로", "신세 많이 졌습니다",
    ],
    "한국문화": [
        "나이 문화", "존댓말", "회식 문화", "눈치 문화", "정 문화", "빨리빨리 문화",
        "한국식 나이 계산법", "회식 자리 예절", "선후배 문화", "직급 호칭 문화", "한국식 술자리 매너",
        "명절 세배 문화", "밥 사는 문화", "정 나눔 선물 문화", "단체 문화", "눈치껏 행동하기",
        "서열 문화", "동안 문화", "한국식 배려", "회식 2차 3차 문화", "한국식 인사법",
        "존댓말 반말 전환 시점", "한국의 집단주의 정서", "정 많은 민족성", "한국식 나이 서열",
    ],
    "리액션": [
        "헐", "대박", "어머", "아이고", "어쩌지", "진짜?", "세상에", "헉",
        "미쳤다", "짱이다", "완전", "대박사건", "어우", "아 진짜", "그니까", "아니 진짜",
        "실화냐", "소름", "레알", "인정", "극혐", "웃프다", "당황스럽다", "어이없다",
        "기가 막히다",
    ],
}
# 카테고리별 가중치 (4개 카테고리를 균등 순환 — 특정 카테고리 편중 방지)
CATEGORY_WEIGHT: Dict[str, int] = {
    "번역감정": 1, "일상표현": 1, "한국문화": 1, "리액션": 1,
}
# 요일별 우선 테마 (월=0 ~ 금=4). 4개 카테고리를 월~목 순서대로, 금요일엔 번역감정으로 다시 순환.
# 검색엔진에 체계적인 카테고리 구조를 인식시키고, 한 카테고리 연속 발행으로 인한 전문성 분산을 방지.
WEEKDAY_THEME_CATEGORY: Dict[int, str] = {
    0: "번역감정",   # 월요일
    1: "일상표현",   # 화요일
    2: "한국문화",   # 수요일
    3: "리액션",     # 목요일
    4: "번역감정",   # 금요일 (플래그십 카테고리 재순환)
}

def _topic_category(topic: str) -> Optional[str]:
    for category, topics in EVERGREEN_TOPIC_BANK.items():
        if topic in topics:
            return category
    return None

def pick_next_topic(queue: Dict[str, Any]) -> Optional[str]:
    """[NEW] 오늘이 월~금이면 해당 요일의 우선 테마 카테고리에 속한 대기 주제를 최우선으로 뽑고,
    없으면 기존 순서(FIFO)대로 뽑습니다."""
    pending: List[str] = queue.get("pending", [])
    if not pending:
        return None

    today_category = WEEKDAY_THEME_CATEGORY.get(datetime.now().weekday())
    if today_category:
        matches = [t for t in pending if _topic_category(t) == today_category]
        if matches:
            chosen = random.choice(matches)
            pending.remove(chosen)
            return chosen

    return pending.pop(0)

def load_queue() -> Dict[str, Any]:
    if not os.path.exists(QUEUE_FILE):
        return {"pending": [], "completed": [], "daily_stats": {"date": "", "count": 0}}
    try:
        with open(QUEUE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            data.setdefault("pending", [])
            data.setdefault("completed", [])
            data.setdefault("daily_stats", {"date": "", "count": 0})
            return data
    except (json.JSONDecodeError, IOError) as e:
        logger.warning(f"큐 파일을 불러오는 데 실패했습니다: {e}")
        return {"pending": [], "completed": [], "daily_stats": {"date": "", "count": 0}}

def save_queue(queue: Dict[str, Any]) -> None:
    with open(QUEUE_FILE, "w", encoding="utf-8") as f:
        json.dump(queue, f, ensure_ascii=False, indent=2)

def refill_evergreen_queue(target_size: int = 20) -> None:
    """[개편] 에버그린 주제 뱅크에서 카테고리 가중치를 반영해 큐를 채웁니다.
    이미 사용(pending/completed)된 주제는 다시 넣지 않습니다."""
    logger.info("=" * 60)
    logger.info("[에버그린 주제뱅크] 큐 보충 시작...")
    queue = load_queue()

    # [FIX] 구글 트렌드 시절 남아있던 잔여 키워드(주제뱅크에 없는 항목)를 자동 정리
    stale = [t for t in queue.get("pending", []) if _topic_category(t) is None]
    if stale:
        queue["pending"] = [t for t in queue.get("pending", []) if _topic_category(t) is not None]
        save_queue(queue)
        logger.info(f"[에버그린 주제뱅크] 예전 트렌드 키워드 잔여분 {len(stale)}개 정리 완료: {stale[:5]}{' ...' if len(stale) > 5 else ''}")

    used = set(queue.get("pending", [])) | set(queue.get("completed", []))

    # 카테고리별 미사용 주제 후보 목록
    pool: List[Tuple[str, int]] = []  # (주제, 가중치)
    for category, topics in EVERGREEN_TOPIC_BANK.items():
        weight = CATEGORY_WEIGHT.get(category, 1)
        for topic in topics:
            if topic not in used:
                pool.append((topic, weight))

    if not pool:
        logger.info("[에버그린 주제뱅크] 모든 주제를 이미 사용했습니다. EVERGREEN_TOPIC_BANK에 새 주제를 추가해주세요.")
        logger.info("=" * 60)
        return

    need = max(0, target_size - len(queue["pending"]))
    if need == 0:
        logger.info(f"[에버그린 주제뱅크] 큐가 이미 충분합니다 (대기 {len(queue['pending'])}개).")
        logger.info("=" * 60)
        return

    weights = [w for _, w in pool]
    topics_only = [t for t, _ in pool]
    picked: List[str] = []
    remaining_idx = list(range(len(topics_only)))
    remaining_weights = list(weights)
    for _ in range(min(need, len(topics_only))):
        chosen = random.choices(remaining_idx, weights=remaining_weights, k=1)[0]
        picked.append(topics_only[chosen])
        pos = remaining_idx.index(chosen)
        remaining_idx.pop(pos)
        remaining_weights.pop(pos)

    queue["pending"].extend(picked)
    save_queue(queue)
    logger.info(f"[에버그린 주제뱅크] 신규 편성: {len(picked)}개 (대기 {len(queue['pending'])}개)")
    logger.info("=" * 60)

DAILY_PUBLISH_LIMIT = 2  # [개편] 하루 자동 발행을 2회로 축소 (사람이 직접 쓴 것처럼 보이도록)
GITHUB_EVENT_NAME = os.environ.get("GITHUB_EVENT_NAME", "")  # "schedule"=자동(cron), "workflow_dispatch"=수동

def check_daily_limit() -> bool:
    queue = load_queue()
    today_str = datetime.now().strftime("%Y-%m-%d")
    daily_stats = queue.get("daily_stats", {"date": "", "count": 0})
    if daily_stats.get("date") != today_str:
        return True
    return daily_stats.get("count", 0) < DAILY_PUBLISH_LIMIT

def _should_publish_now_random() -> bool:
    """[NEW] '하루 랜덤 자동 2번 발행' — 매시 정각마다 cron이 돌지만, 실제 발행 여부는
    저수지 표본추출(reservoir sampling) 방식의 확률로 결정해 하루 중 무작위 시각에
    총 DAILY_PUBLISH_LIMIT회만 발행되도록 한다. (수동 실행은 이 함수를 타지 않음 — 제한 없음)"""
    queue = load_queue()
    today_str = datetime.now().strftime("%Y-%m-%d")
    daily_stats = queue.get("daily_stats", {"date": "", "count": 0})
    published_today = daily_stats.get("count", 0) if daily_stats.get("date") == today_str else 0

    slots_remaining = DAILY_PUBLISH_LIMIT - published_today
    if slots_remaining <= 0:
        return False

    now = datetime.now()
    hours_remaining = 24 - now.hour  # 이번 시각의 실행도 후보에 포함
    probability = min(1.0, slots_remaining / max(1, hours_remaining))
    roll = random.random()
    logger.info(f"[랜덤 발행 판정] 오늘 발행 {published_today}/{DAILY_PUBLISH_LIMIT}회, 남은 시간대 {hours_remaining}개, 발행 확률 {probability:.2f}, 주사위 {roll:.2f}")
    return roll < probability

def increment_daily_count() -> None:
    queue = load_queue()
    today_str = datetime.now().strftime("%Y-%m-%d")
    daily_stats = queue.get("daily_stats", {"date": today_str, "count": 0})
    if daily_stats.get("date") == today_str:
        daily_stats["count"] = daily_stats.get("count", 0) + 1
    else:
        daily_stats = {"date": today_str, "count": 1}
    queue["daily_stats"] = daily_stats
    save_queue(queue)



# =====================================================================
# HTML 및 렌더링 템플릿들
# =====================================================================

def build_decor_html(theme: Dict[str, Any], seed: str) -> str:
    rng = random.Random(seed)
    emojis = theme["decor"]
    count = rng.randint(9, 12)
    items = []
    for _ in range(count):
        emoji = rng.choice(emojis)
        top = rng.randint(0, 96)
        left = rng.randint(0, 92)
        size = rng.randint(26, 58)
        rotate = rng.randint(-30, 30)
        opacity = round(rng.uniform(0.07, 0.16), 2)
        items.append(
            f'<span class="decor-item" style="top:{top}%;left:{left}%;font-size:{size}px;'
            f'opacity:{opacity};transform:rotate({rotate}deg);">{emoji}</span>'
        )
    return '<div class="decor-layer" aria-hidden="true">' + "".join(items) + "</div>"

def _search_console_meta() -> str:
    if not GOOGLE_SITE_VERIFICATION: return ""
    return f'\n<meta name="google-site-verification" content="{GOOGLE_SITE_VERIFICATION}">'

def _ga_snippet() -> str:
    if not GA_MEASUREMENT_ID: return ""
    return f"""
<script async src="https://www.googletagmanager.com/gtag/js?id={GA_MEASUREMENT_ID}"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){{dataLayer.push(arguments);}}
  gtag('js', new Date());
  gtag('config', '{GA_MEASUREMENT_ID}');
</script>"""

ENABLE_AUTO_TRANSLATE = os.environ.get("ENABLE_AUTO_TRANSLATE", "true").strip().lower() != "false"

def _translate_widget() -> str:
    """방문자의 브라우저 언어가 한국어가 아니면 조용히 번역을 수행합니다 (UI 완전 숨김 처리).
    [NEW] 말풍선 아이콘 클릭 시 배우는 한글 표현을 남성/여성 음성으로 또박또박 읽어주는
    TTS(Web Speech API) 스크립트도 함께 포함합니다 (모든 플랫폼 공통 삽입 지점)."""
    parts = []
    if ENABLE_AUTO_TRANSLATE:
        parts.append("""
<div id="google_translate_element" style="position:absolute; top:-9999px; left:-9999px; display:none;"></div>
<script>
function googleTranslateElementInit() {
  new google.translate.TranslateElement({pageLanguage: 'ko', autoDisplay: false}, 'google_translate_element');
}
(function() {
  try {
      var userLang = navigator.language || navigator.userLanguage;
      if (userLang && !userLang.startsWith('ko')) {
        var targetLang = userLang.split('-')[0];
        if(document.cookie.indexOf('googtrans=') === -1) {
          document.cookie = "googtrans=/ko/" + targetLang + "; path=/";
          if (document.domain) {
              document.cookie = "googtrans=/ko/" + targetLang + "; domain=" + document.domain + "; path=/";
          }
          window.location.reload();
        }
      }
  } catch(e) {}
})();
</script>
<script src="//translate.google.com/translate_a/element.js?cb=googleTranslateElementInit"></script>""")

    parts.append("""
<script>
function playKoreanTTS(text) {
  try {
    var audio = new Audio('https://translate.google.com/translate_tts?ie=UTF-8&q=' + encodeURIComponent(text) + '&tl=ko&client=tw-ob');
    var played = audio.play();
    if (played && played.catch) {
      played.catch(function(err) {
        console.warn('[TTS] 구글 번역 음성 재생 실패, 브라우저 음성으로 대체합니다:', err);
        _fallbackKoreanTTS(text);
      });
    }
  } catch(e) {
    console.warn('[TTS] 구글 번역 음성 호출 실패, 브라우저 음성으로 대체합니다:', e);
    _fallbackKoreanTTS(text);
  }
}
function _fallbackKoreanTTS(text) {
  try {
    if (!('speechSynthesis' in window)) { alert('이 브라우저는 음성 재생을 지원하지 않습니다.'); return; }
    window.speechSynthesis.cancel();
    var utter = new SpeechSynthesisUtterance(text);
    utter.lang = 'ko-KR';
    utter.rate = 0.85;
    window.speechSynthesis.speak(utter);
  } catch(e) { console.error('[TTS 폴백 오류]', e); }
}
</script>""")
    return "".join(parts)

def _adsense_snippet() -> str:
    if not ADSENSE_CLIENT_ID: return ""
    return f'\n<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client={ADSENSE_CLIENT_ID}" crossorigin="anonymous"></script>'

def build_faq_section_html(article: Dict[str, Any], accent: str = "#e95c84") -> str:
    if not article.get("faq_items"): return ""
    cards = []
    for i, qa in enumerate(article["faq_items"], 1):
        cards.append(
            f'<details style="margin:14px 0;background:#f7f8fa;border-left:4px solid {accent};'
            'border-radius:8px;padding:2px 18px;" open>'
            '<summary style="cursor:pointer;padding:14px 0;font-family:\'Noto Sans KR\',-apple-system,sans-serif;'
            f'font-weight:800;font-size:1.08em;color:#111;outline:none;user-select:none;">Q{i}. {qa.get("question", "")}</summary>'
            '<p style="margin:0;padding:0 0 16px;font-family:\'Noto Sans KR\',-apple-system,sans-serif;'
            f'font-weight:400;color:#555;line-height:1.75;">A. {qa.get("answer", "")}</p>'
            '</details>'
        )
    return '<h2 style="margin-top:2em;">자주 묻는 질문(FAQ) <span style="font-size:0.6em;color:#999;font-weight:400;">(탭하면 펼쳐져요)</span></h2>' + "".join(cards)

def build_json_ld(article: Dict[str, Any], canonical_url: str, thumb_url: str, date: str, platform: str = "github") -> str:
    schema_type = article.get("schema_type", "Article")
    title = article["title"]
    meta_description = article.get("meta_description", "")
    article_type = "BlogPosting" if platform == "blogger" else "Article"

    if schema_type == "FAQPage" and article.get("faq_items"):
        data = {
            "@context": "https://schema.org", "@type": "FAQPage",
            "mainEntity": [{"@type": "Question", "name": qa.get("question", ""), "acceptedAnswer": {"@type": "Answer", "text": qa.get("answer", "")}} for qa in article["faq_items"]],
        }
    elif schema_type == "HowTo" and article.get("howto_steps"):
        data = {
            "@context": "https://schema.org", "@type": "HowTo", "name": title, "description": meta_description,
            "step": [{"@type": "HowToStep", "name": s.get("name", ""), "text": s.get("text", "")} for s in article["howto_steps"]],
        }
    else:
        schema_type = article_type
        org_id = build_organization_website_json_ld()["org_id"]
        data = {
            "@context": "https://schema.org", "@type": article_type, "headline": title, "description": meta_description,
            "image": thumb_url, "datePublished": date,
            "author": {"@type": "Organization", "name": SITE_TITLE, "@id": org_id},
            "publisher": {"@type": "Organization", "name": SITE_TITLE, "@id": org_id},
        }

    data.pop("@context", None)
    breadcrumb = {
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": SITE_TITLE, "item": (SITE_URL + "/") if SITE_URL else "../index.html"},
            {"@type": "ListItem", "position": 2, "name": article.get("category", "번역감정"), "item": (SITE_URL + "/") if SITE_URL else "../index.html"},
            {"@type": "ListItem", "position": 3, "name": title, "item": canonical_url},
        ],
    }
    graph_nodes = [data, breadcrumb]
    if article.get("product_list"):
        graph_nodes.append({
            "@type": "ItemList", "name": f"{title} - 소개된 상품 목록",
            "itemListElement": [{"@type": "ListItem", "position": i, "item": {"@type": "Product", "name": p.get("name", ""), "description": p.get("description", "")}} for i, p in enumerate(article["product_list"][:6], 1)],
        })
    return json.dumps({"@context": "https://schema.org", "@graph": graph_nodes}, ensure_ascii=False, indent=2)

def build_organization_website_json_ld() -> Dict[str, Any]:
    """[NEW] 브랜드 엔티티 SEO: 사이트 전체를 대표하는 Organization + WebSite를 선언한다.
    각 글의 Article/BlogPosting의 publisher가 이 @id를 참조해 동일 브랜드로 연결된다."""
    base = (SITE_URL + "/") if SITE_URL else "."
    org_id = f"{base}#organization"
    site_id = f"{base}#website"
    return {
        "org": {
            "@type": "Organization", "@id": org_id, "name": SITE_TITLE, "url": base,
            "description": SITE_TAGLINE,
        },
        "website": {
            "@type": "WebSite", "@id": site_id, "url": base, "name": SITE_TITLE,
            "description": SITE_TAGLINE, "publisher": {"@id": org_id}, "inLanguage": "ko",
        },
        "org_id": org_id,
    }

def build_blog_index_json_ld(posts: List[Dict[str, Any]]) -> str:
    brand = build_organization_website_json_ld()
    blog_node = {
        "@type": "Blog", "name": SITE_TITLE, "url": (SITE_URL + "/") if SITE_URL else ".",
        "publisher": {"@id": brand["org_id"]},
        "blogPost": [{"@type": "BlogPosting", "headline": p["title"], "url": (f"{SITE_URL}/{p['file']}" if SITE_URL else p["file"]), "datePublished": p["date"], "image": (f"{SITE_URL}/{p['thumb']}" if SITE_URL else p["thumb"])} for p in posts[:10]],
    }
    return json.dumps({"@context": "https://schema.org", "@graph": [brand["org"], brand["website"], blog_node]}, ensure_ascii=False, indent=2)

POST_TEMPLATE = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<meta name="description" content="{meta_description}">
<link rel="canonical" href="{canonical_url}">
<link rel="icon" type="image/png" href="../favicon.png">{search_console_meta}
<link rel="manifest" href="../manifest.json">
<meta name="theme-color" content="#facc15">
<link rel="apple-touch-icon" href="../icon-192.png">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="{site_title_short}">
<script>if ('serviceWorker' in navigator) {{ window.addEventListener('load', () => navigator.serviceWorker.register('../sw.js').catch(()=>{{}})); }}</script>
<meta property="og:type" content="article">
<meta property="og:site_name" content="{site_title}">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{meta_description}">
<meta property="og:image" content="{thumb_url}">
<meta property="og:url" content="{canonical_url}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{title}">
<meta name="twitter:description" content="{meta_description}">
<meta name="twitter:image" content="{thumb_url}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family={font}&family=Noto+Sans+KR:wght@400;700&display=swap" rel="stylesheet">
<script type="application/ld+json">
{json_ld}
</script>{ga_snippet}{adsense_snippet}
<style>
  * {{ box-sizing: border-box; }}
  html {{ -webkit-text-size-adjust: 100%; }}
  body {{ position: relative; width: 100%; max-width: 720px; margin: 0 auto; padding: 0 clamp(16px, 4vw, 20px) 60px; font-family: 'Noto Sans KR', -apple-system, sans-serif; line-height: 1.75; color: #1a1a1a; background: #fafafa; overflow-x: hidden; }}
  img {{ max-width: 100%; height: auto; }}
  .decor-layer {{ position: absolute; inset: 0; overflow: hidden; pointer-events: none; z-index: 0; }}
  .decor-item {{ position: absolute; filter: grayscale(0%); user-select: none; }}
  .content {{ position: relative; z-index: 1; }}
  .hero {{ margin: 0 -20px 24px; position: relative; }}
  .hero img {{ width: 100%; aspect-ratio: 16/9; object-fit: cover; display: block; }}
  .badge {{ display: inline-block; background: {accent}; color: #fff; font-size: clamp(0.75em, 2.2vw, 0.85em); font-weight: 700; padding: 5px 14px; border-radius: 999px; margin: 20px 0 10px; }}
  h1 {{ font-family: '{font_family}', 'Noto Sans KR', sans-serif; font-size: clamp(1.4em, 5vw, 1.9em); line-height: 1.35; margin: 0 0 8px; word-break: keep-all; }}
  h2 {{ font-family: '{font_family}', 'Noto Sans KR', sans-serif; font-size: clamp(1.1em, 4vw, 1.35em); margin-top: 2em; padding: 10px 14px; background: linear-gradient(90deg, {accent}22, transparent); border-left: 5px solid {accent}; border-radius: 4px; position: relative; z-index: 1; word-break: keep-all; }}
  p {{ margin: 1em 0; position: relative; z-index: 1; }}
  table {{ width: 100%; min-width: 460px; border-collapse: collapse; font-size: 0.92em; }}
  th, td {{ padding: 11px 14px; border-bottom: 1px solid #eee; text-align: left; line-height: 1.5; }}
  th {{ background: {accent}14; font-weight: 800; color: #111; white-space: nowrap; }}
  tr:last-child td {{ border-bottom: none; }}
  a.back {{ display: inline-block; margin: 20px 0; color: {accent}; text-decoration: none; font-weight: 700; position: relative; z-index: 1; }}
  .meta {{ color: #999; font-size: 0.85em; margin-bottom: 4px; }}
  .related {{ margin-top: 60px; padding-top: 24px; border-top: 2px solid #eee; }}
  .related h3 {{ font-size: 1.1em; margin-bottom: 14px; }}
  .related-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 14px; }}
  .related-card {{ text-decoration: none; color: #1a1a1a; }}
  .related-card img {{ width: 100%; aspect-ratio: 16/9; object-fit: cover; border-radius: 10px; margin-bottom: 6px; }}
  .related-card span {{ font-size: 0.88em; font-weight: 500; }}
  .post-nav {{ display: flex; justify-content: space-between; gap: 10px; margin: 30px 0; flex-wrap: wrap; }}
  .post-nav a {{ display: flex; align-items: center; gap: 8px; text-decoration: none; color: #333; background: #fff; border: 1px solid #eee; border-radius: 999px; padding: 6px 16px 6px 6px; font-size: 0.85em; max-width: 100%; }}
  .post-nav img {{ width: 28px; height: 28px; border-radius: 50%; object-fit: cover; flex-shrink: 0; }}
  .post-nav .nav-icon {{ width: 28px; height: 28px; border-radius: 50%; background: {accent}; color: #fff; display:flex; align-items:center; justify-content:center; font-size: 14px; flex-shrink: 0; }}
  .post-nav span {{ overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}

  details summary {{ list-style: none; display: flex; align-items: center; justify-content: space-between; gap: 10px; }}
  details summary::-webkit-details-marker {{ display: none; }}
  details summary::after {{ content: '▼'; font-size: 0.75em; color: {accent}; flex-shrink: 0; }}
  details[open] summary::after {{ content: '▲'; }}
  @media (max-width: 480px) {{
    .related-grid {{ grid-template-columns: 1fr 1fr; }}
    .post-nav a {{ font-size: 0.78em; flex: 1 1 100%; }}
  }}
  @media (min-width: 900px) {{
    body {{ max-width: 760px; }}
  }}
  .translate-widget {{ position: fixed; top: 10px; right: 10px; z-index: 999; font-size: 0.8em; }}
  body {{ top: 0 !important; }}
  .goog-te-banner-frame {{ display: none !important; }}
</style>
</head>
<body>
{translate_widget}
{decor_html}
<div class="content">
<a class="back" href="../index.html">← 목록으로</a>
<div class="hero"><img src="../thumbs/{thumb_filename}" alt="{title}" loading="eager" fetchpriority="high"></div>
<span class="badge">{badge}</span>
<h1>{title}</h1>
<p class="meta">{date}</p>
{photo_credit_html}
{html_body}
{post_nav}
{related_html}
{bottom_ad}
</div>
</body>
</html>
"""

ALL_THEME_FONTS = sorted({t["font"] for t in CATEGORY_THEMES.values()})
def _google_fonts_url() -> str:
    families = "&family=".join(ALL_THEME_FONTS)
    return f"https://fonts.googleapis.com/css2?family={families}&family=Noto+Sans+KR:wght@400;700;900&display=swap"

INDEX_TEMPLATE = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{site_title}</title>
<meta name="description" content="{site_tagline}">
<link rel="canonical" href="{site_url}/">
<link rel="icon" type="image/png" href="favicon.png">{search_console_meta}
<link rel="manifest" href="manifest.json">
<meta name="theme-color" content="#facc15">
<link rel="apple-touch-icon" href="icon-192.png">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="{site_title_short}">
<script>if ('serviceWorker' in navigator) {{ window.addEventListener('load', () => navigator.serviceWorker.register('sw.js').catch(()=>{{}})); }}</script>
<meta property="og:type" content="website">
<meta property="og:site_name" content="{site_title}">
<meta property="og:title" content="{site_title}">
<meta property="og:description" content="{site_tagline}">
<meta property="og:url" content="{site_url}/">
<meta name="twitter:card" content="summary">
<meta name="twitter:title" content="{site_title}">
<meta name="twitter:description" content="{site_tagline}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="{fonts_url}" rel="stylesheet">
<script type="application/ld+json">
{blog_json_ld}
</script>{ga_snippet}{adsense_snippet}
<style>
  * {{ box-sizing: border-box; }}
  html {{ -webkit-text-size-adjust: 100%; }}
  body {{ max-width: 1000px; margin: 0 auto; padding: 0 0 60px; font-family: 'Noto Sans KR', -apple-system, sans-serif; background:#f5f5f7; color:#1a1a1a; }}
  img {{ max-width: 100%; height: auto; }}
  .masthead {{ position: relative; margin-bottom: 26px; }}
  .masthead img {{ width: 100%; aspect-ratio: 1600/420; object-fit: cover; display:block; }}
  .masthead-inner {{ padding: 0 clamp(14px, 4vw, 20px); }}
  .brand-row {{ display:flex; align-items:center; gap:12px; margin: 18px 0 4px; flex-wrap: wrap; }}
  .brand-row img.logo {{ width:44px; height:44px; border-radius:50%; box-shadow: 0 2px 8px rgba(0,0,0,0.15); }}
  h1.site-title {{ font-family: 'Jua', sans-serif; font-size: clamp(1.2em, 4.5vw, 1.6em); margin:0; word-break: keep-all; }}
  .dash-link {{ margin-left:auto; font-size: clamp(0.7em, 2.5vw, 0.75em); color:#888; text-decoration:none; background:#eee; padding:6px 14px; border-radius:999px; }}
  .intro {{ color:#555; font-size:0.95em; margin: 4px 0 16px; line-height:1.6; word-break: keep-all; }}
  .pill-row {{ display:flex; flex-wrap:wrap; gap:8px; margin-bottom: 10px; }}
  .pill {{ font-size:0.78em; font-weight:700; color:#fff; padding:5px 13px; border-radius:999px; }}
  .content-wrap {{ padding: 0 clamp(14px, 4vw, 20px); }}
  .tier-label {{ font-size: 0.85em; font-weight:900; color:#aaa; letter-spacing:2px; margin: 34px 0 12px; text-transform:uppercase; }}
  .tier-label:first-of-type {{ margin-top: 10px; }}

  .hero {{ display:block; text-decoration:none; color:#1a1a1a; background:#fff; border-radius:20px; overflow:hidden; box-shadow: 0 6px 24px rgba(0,0,0,0.10); }}
  .hero img {{ width:100%; aspect-ratio: 16/9; object-fit:cover; display:block; }}
  .hero-body {{ padding: clamp(16px, 4vw, 22px) clamp(18px, 5vw, 26px) 28px; }}
  .hero-badge {{ display:inline-block; font-size:0.8em; font-weight:700; color:#fff; padding:5px 14px; border-radius:999px; margin-bottom:12px; }}
  .hero-title {{ font-size: clamp(1.25em, 4.5vw, 1.7em); font-weight:800; line-height:1.35; word-break: keep-all; }}

  .mid-grid {{ display:grid; grid-template-columns: 1fr 1fr; gap:18px; }}
  .mid-card {{ text-decoration:none; color:#1a1a1a; background:#fff; border-radius:16px; overflow:hidden; box-shadow: 0 3px 14px rgba(0,0,0,0.08); transition: transform .15s ease; }}
  .mid-card:hover {{ transform: translateY(-3px); }}
  .mid-card img {{ width:100%; aspect-ratio:16/9; object-fit:cover; display:block; }}
  .mid-body {{ padding: 14px 16px 18px; }}
  .mid-title {{ font-weight:700; font-size:clamp(0.92em, 3vw, 1.08em); line-height:1.4; word-break: keep-all; }}

  .bottom-grid {{ display:grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap:14px; }}
  .bottom-card {{ text-decoration:none; color:#1a1a1a; background:#fff; border-radius:10px; overflow:hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }}
  .bottom-card img {{ width:100%; aspect-ratio:16/10; object-fit:cover; display:block; }}
  .bottom-body {{ padding: 8px 10px 12px; }}
  .bottom-title {{ font-weight:600; font-size:0.85em; line-height:1.35; word-break: keep-all; }}

  .badge-sm {{ display:inline-block; font-size:0.65em; font-weight:700; color:#fff; padding:2px 8px; border-radius:999px; margin-bottom:5px; }}
  .date {{ color: #999; font-size: 0.78em; margin-top: 5px; }}
  .site-footer {{ margin-top: 50px; padding: 24px 20px; border-top: 1px solid #e2e2e2; text-align:center; color:#999; font-size:0.82em; }}
  .site-footer a {{ color:#777; text-decoration:none; margin: 0 8px; }}
  .site-footer a:hover {{ color:#b45309; }}

  @media (max-width: 480px) {{
    .masthead img {{ aspect-ratio: 1600/620; }}
    .hero img {{ aspect-ratio: 16/9; }}
    .mid-grid {{ grid-template-columns: 1fr; gap: 14px; }}
    .bottom-grid {{ grid-template-columns: repeat(2, 1fr); }}
  }}
  @media (min-width: 1000px) {{
    .bottom-grid {{ grid-template-columns: repeat(5, 1fr); }}
  }}
  .translate-widget {{ position: fixed; top: 10px; right: 10px; z-index: 999; font-size: 0.8em; }}
  body {{ top: 0 !important; }}
  .goog-te-banner-frame {{ display: none !important; }}
</style>
</head>
<body>
{translate_widget}
<div class="masthead">
  <img src="banner.webp" alt="{site_title}" loading="eager" fetchpriority="high">
</div>
<div class="masthead-inner">
  <div class="brand-row">
    <img class="logo" src="logo.webp" alt="{site_title} 로고">
    <h1 class="site-title">{site_title}</h1>
    <a class="dash-link" href="dashboard.html">📊 성과관리</a>
  </div>
  <p class="intro">{site_tagline}</p>
  <div class="pill-row">{category_pills}</div>
</div>

<div class="content-wrap">
{hero_html}
{mid_html}
{bottom_html}
</div>
{footer_html}
</body>
</html>
"""

DASHBOARD_TEMPLATE = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>성과 관리 - {site_title}</title>
<style>
  body {{ max-width: 760px; margin: 40px auto; padding: 0 20px; font-family: -apple-system, sans-serif; color:#222; }}
  h1 {{ font-size: 1.5em; }}
  h2 {{ font-size: 1.1em; margin-top: 2em; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.9em; }}
  th, td {{ text-align: left; padding: 8px 4px; border-bottom: 1px solid #eee; }}
  a {{ color: #e95c84; }}
  .card {{ background:#f7f7f9; border-radius:8px; padding:16px; margin: 10px 0; }}
  a.back {{ display: inline-block; margin-bottom: 20px; color: #e95c84; text-decoration: none; }}
</style>
</head>
<body>
<a class="back" href="index.html">← 블로그로</a>
<h1>📊 성과 관리 대시보드</h1>
<div class="card">
  <b>실시간 트래픽 확인 (GA4)</b><br>
  플레이스토어 "Google Analytics" 앱 설치 후 이 사이트의 방문자/인기글을 확인하세요.<br>
  <a href="https://analytics.google.com" target="_blank">analytics.google.com 바로가기</a>
</div>
<div class="card">
  <b>수익(쿠팡 마크업 수수료) 확인</b><br>
  쿠팡파트너스 앱 또는 사이트에서 클릭수/수익을 확인하세요.<br>
  <a href="https://partners.coupang.com" target="_blank">partners.coupang.com 바로가기</a>
</div>
<div class="card">
  <b>광고 수익(애드센스) 확인</b><br>
  플레이스토어 "Google AdSense" 앱 설치 후 페이지뷰/광고 수익(전면광고 포함)을 확인하세요.<br>
  <a href="https://www.google.com/adsense" target="_blank">adsense.google.com 바로가기</a>
</div>
<div class="card">
  <b>검색 노출 확인 (Google Search Console)</b><br>
  사이트가 구글 검색에 얼마나 노출/클릭되는지 확인하세요. 최초 1회 소유권 인증이 필요합니다.<br>
  <a href="https://search.google.com/search-console" target="_blank">search.google.com/search-console 바로가기</a>
</div>
<h2>발행된 글 목록 ({post_count}개)</h2>
<table>
<tr><th>날짜</th><th>제목</th><th>바로가기</th></tr>
{rows}
</table>
</body>
</html>
"""

SITEMAP_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url><loc>{site_url}/</loc></url>
{url_entries}
</urlset>
"""
ROBOTS_TXT = "User-agent: *\nAllow: /\n\nSitemap: {site_url}/sitemap.xml\n"
GEMINI_GRADIENT_COLORS = [(66, 133, 244), (156, 39, 176), (234, 67, 121)]
THUMB_SIZE = (1280, 720)

# =====================================================================
# 기타 유틸리티
# =====================================================================

def slugify(text: str) -> str:
    text = re.sub(r"[^\w\s-]", "", text).strip()
    return re.sub(r"[\s]+", "-", text) or "post"

# --- [NEW] AI의 "글자 수 세기" 오류 자동 교정 ---
# LLM은 종종 텍스트의 글자 수를 잘못 셉니다(예: "그래 이혼하자"는 실제 6글자인데 "다섯 글자"라고
# 서술). AI 판단에 맡기지 않고, Python이 키워드의 실제 길이를 정확히 세어 본문에서 언급된
# "OO 글자" 표현을 강제로 바로잡습니다.
KOREAN_COUNT_WORDS = {
    1: "한", 2: "두", 3: "세", 4: "네", 5: "다섯", 6: "여섯", 7: "일곱", 8: "여덟",
    9: "아홉", 10: "열", 11: "열한", 12: "열두", 13: "열세", 14: "열네", 15: "열다섯",
    16: "열여섯", 17: "열일곱", 18: "열여덟", 19: "열아홉", 20: "스무",
}
_COUNT_WORD_PATTERN = re.compile(
    "(" + "|".join(re.escape(w) for w in sorted(KOREAN_COUNT_WORDS.values(), key=len, reverse=True)) + r")\s?(글자|자)\b"
)

def fix_character_count_claims(article: Dict[str, Any]) -> Dict[str, Any]:
    keyword = article.get("keyword", "")
    correct_len = len(re.sub(r"\s+", "", keyword))
    if correct_len not in KOREAN_COUNT_WORDS:
        return article  # 지원 범위(1~20글자) 밖이면 손대지 않음
    correct_word = KOREAN_COUNT_WORDS[correct_len]

    def _replace(m: "re.Match") -> str:
        return f"{correct_word} {m.group(2)}"

    for field in ("title", "html_body", "meta_description"):
        if article.get(field):
            article[field] = _COUNT_WORD_PATTERN.sub(_replace, article[field])
    return article

def generate_article(title: str) -> Dict[str, Any]:
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY 환경변수가 비어있습니다. 저장소 Secrets 설정을 확인하세요.")

    url = GEMINI_URL.format(api_key=GEMINI_API_KEY)
    payload = {
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"role": "user", "parts": [{"text": f"오늘 날짜: {datetime.now().strftime('%Y년 %m월 %d일')}\n\n주제: '{title}'\n\n이 주제에 대해 검색으로 찾아온 독자가 실제로 궁금해할 조건·절차·비교·주의사항을 중심으로, 정확하고 실용적인 가이드형 블로그 글을 작성해주세요. 확실하지 않은 정보는 단정하지 말고, 공식 기관 확인이 필요한 내용은 그렇게 안내해주세요. 시점을 언급할 때는 반드시 위에 적힌 '오늘 날짜'를 기준으로 하고, 이보다 오래된 연도를 임의로 쓰지 마세요."}]}],
        # [FIX] JSON 파싱 실패를 줄이기 위해 순수 JSON 출력을 강제하고 출력 토큰 한도를 명시적으로 늘림
        "generationConfig": {
            "responseMimeType": "application/json",
            "maxOutputTokens": 8192,
        },
    }

    last_error = None
    for attempt in range(1, 4):
        try:
            resp = requests.post(url, json=payload, timeout=60)
            if resp.status_code in (429, 503):
                wait = 15 * attempt
                logger.warning(f"일시적 오류({resp.status_code}), {wait}초 대기 후 재시도 ({attempt}/3)")
                time.sleep(wait)
                last_error = f"{resp.status_code} 오류 반복됨"
                continue
            resp.raise_for_status()
            data = resp.json()

            candidates = data.get("candidates") or []
            if not candidates:
                block_reason = data.get("promptFeedback", {}).get("blockReason", "알 수 없음")
                last_error = f"candidates가 비어있음 (blockReason: {block_reason})"
                logger.warning(f"[Gemini] 응답에 candidates가 없습니다 ({attempt}/3): {last_error}")
                continue

            finish_reason = candidates[0].get("finishReason", "")
            parts = candidates[0].get("content", {}).get("parts", [])
            if not parts:
                last_error = f"content.parts가 비어있음 (finishReason: {finish_reason})"
                logger.warning(f"[Gemini] 빈 응답 ({attempt}/3): {last_error}")
                continue

            text = parts[0].get("text", "")
            cleaned = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()

            try:
                decoder = json.JSONDecoder()
                article, _ = decoder.raw_decode(cleaned)
            except json.JSONDecodeError as e:
                last_error = f"JSON 파싱 실패: {e} (finishReason: {finish_reason}, 응답 길이: {len(text)}자)"
                logger.warning(
                    f"[Gemini] {last_error} ({attempt}/3)\n"
                    f"  응답 앞부분: {text[:200]!r}\n  응답 뒷부분: {text[-200:]!r}"
                )
                continue

            if not article.get("title") or not article.get("html_body"):
                last_error = "응답 JSON에 title 또는 html_body가 없습니다."
                logger.warning(f"[Gemini] {last_error} ({attempt}/3)")
                continue

            article["keyword"] = title
            article["expression"] = (article.get("expression") or "").strip()
            # [NEW] 배우는 한글 표현이 구글 자동번역으로 다른 언어로 바뀌지 않도록,
            # 본문 전체에서 해당 표현이 등장하는 모든 위치를 notranslate 처리
            article["html_body"] = _wrap_notranslate(article["html_body"], article["expression"])

            desc = article.get("meta_description", "").strip()
            if len(desc) > 160:
                desc = desc[:157].rstrip() + "..."
            article["meta_description"] = desc

            return article
        except (KeyError, IndexError) as e:
            last_error = f"Gemini 응답 형식이 예상과 다릅니다: {e}"
            logger.warning(f"[Gemini] {last_error} ({attempt}/3)")
        except requests.exceptions.RequestException as e:
            last_error = str(e)
            time.sleep(10)

    raise RuntimeError(f"3번 시도했지만 계속 실패했습니다: {last_error}")

def _load_font(size: int):
    for path in FONT_CANDIDATES:
        if os.path.exists(path) and os.path.getsize(path) > 0:
            try:
                return ImageFont.truetype(path, size)
            except Exception as e:
                # [FIX] 다운로드가 중간에 끊겨 0바이트/손상된 폰트 파일이 생겨도
                # 여기서 죽지 않고 다음 후보 폰트로 넘어가도록 방어
                logger.warning(f"폰트 파일 '{path}' 로드 실패({e}), 다음 후보로 대체합니다.")
    logger.warning("한글 폰트를 찾지 못해 기본 폰트로 대체합니다 (한글이 깨져 보일 수 있음).")
    return ImageFont.load_default()

def _make_gradient_background(size: Tuple[int, int], colors: List[Tuple[int, int, int]]):
    w, h = size
    base = Image.new("RGB", size, colors[0])
    top = Image.new("RGB", size, colors[-1])
    mask = Image.new("L", size)
    mask.putdata([int(((x / w + y / h) / 2) * 255) for y in range(h) for x in range(w)])
    blended = Image.composite(top, base, mask)
    mid = Image.new("RGB", size, colors[1])
    mid_mask = Image.new("L", size)
    mid_mask.putdata([int(80 * (1 - abs((x / w + y / h) / 2 - 0.5) * 2)) for y in range(h) for x in range(w)])
    return Image.composite(mid, blended, mid_mask)

def _make_random_gradient_background(size: Tuple[int, int], colors: List[Tuple[int, int, int]], seed: int = None):
    """[NEW] 감정컬러 랜덤배경: 매번 그라데이션 방향을 무작위로 바꿔 같은 카테고리라도
    다른 느낌의 배경이 나오게 한다 (좌상↘우하 / 우상↙좌하 / 위↓아래 / 왼쪽→오른쪽 중 랜덤)."""
    rnd = random.Random(seed) if seed is not None else random
    direction = rnd.choice(["tl_br", "tr_bl", "top_bottom", "left_right"])
    w, h = size

    def t_at(x, y):
        if direction == "tl_br": return (x / w + y / h) / 2
        if direction == "tr_bl": return ((w - x) / w + y / h) / 2
        if direction == "top_bottom": return y / h
        return x / w  # left_right

    base = Image.new("RGB", size, colors[0])
    top = Image.new("RGB", size, colors[-1])
    mask = Image.new("L", size)
    mask.putdata([int(t_at(x, y) * 255) for y in range(h) for x in range(w)])
    blended = Image.composite(top, base, mask)
    mid = Image.new("RGB", size, colors[1])
    mid_mask = Image.new("L", size)
    mid_mask.putdata([int(80 * (1 - abs(t_at(x, y) - 0.5) * 2)) for y in range(h) for x in range(w)])
    return Image.composite(mid, blended, mid_mask)

def _wrap_notranslate(html_body: str, expression: str) -> str:
    """배우는 한글 표현은 구글 자동번역(_translate_widget)이 건너뛰도록 notranslate 처리.
    HTML 태그/속성 내부는 건드리지 않고, 텍스트 노드에 등장하는 표현만 안전하게 감싼다."""
    expression = (expression or "").strip()
    if not expression or len(expression) > 20:
        return html_body
    wrapped = f'<span class="notranslate kr-word" translate="no">{expression}</span>'
    parts = re.split(r'(<[^>]+>)', html_body)
    for i, part in enumerate(parts):
        if part and not part.startswith("<") and expression in part:
            parts[i] = part.replace(expression, wrapped)
    return "".join(parts)

def _hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))

def _blend_rgb(c1: Tuple[int, int, int], c2: Tuple[int, int, int], t: float) -> Tuple[int, int, int]:
    """c1과 c2를 t(0~1) 비율로 섞는다 (t=0이면 c1, t=1이면 c2)"""
    return tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))

# =====================================================================
# [전면 개편] 무료 AI 2D 시그니처 캐릭터 이미지 생성 (Pollinations.ai — API 키 불필요)
# 말풍선 대화를 나누는 고정 마스코트 캐릭터를 카테고리별 프롬프트로 생성합니다.
# 실패 시 None을 반환하며, 호출부에서 Pexels(설정된 경우) → 그라데이션 순으로 폴백합니다.
# =====================================================================
def _generate_ai_cartoon_image(prompt: str, size: Tuple[int, int], seed: int) -> Optional[Image.Image]:
    try:
        w, h = size
        encoded_prompt = urllib.parse.quote(prompt)
        url = (
            f"https://image.pollinations.ai/prompt/{encoded_prompt}"
            f"?width={w}&height={h}&seed={seed}&nologo=true&model=flux"
        )
        resp = requests.get(url, timeout=45)
        resp.raise_for_status()
        img = Image.open(io.BytesIO(resp.content)).convert("RGB")
        if img.size != size:
            img = img.resize(size)
        return img
    except Exception as e:
        logger.warning(f"[AI 캐릭터 이미지] Pollinations 생성 실패, 2차 폴백으로 넘어갑니다: {e}")
        return None

_pexels_unconfigured_logged = False

def _fetch_stock_photo(query: str, fallback_query: str, size: Tuple[int, int], seed: int) -> Tuple[Optional[Image.Image], Optional[Dict[str, str]]]:
    """Pexels에서 사진을 검색해 (이미지, 출처정보)를 반환합니다. 1순위 검색어(query, 보통 기사
    주제에 맞는 AI 추출 영어 키워드)로 먼저 찾고, 결과가 없으면 2순위(fallback_query, 카테고리
    일반 키워드)로 재검색합니다. API 키 미설정/요청 전부 실패 시 (None, None)을 반환하며,
    호출부에서 그라데이션으로 대체합니다."""
    global _pexels_unconfigured_logged
    if not PEXELS_API_KEY:
        if not _pexels_unconfigured_logged:
            logger.info("[무료 이미지] PEXELS_API_KEY 미설정으로 건너뜁니다. (그라데이션 배경으로 대체됩니다)")
            _pexels_unconfigured_logged = True
        return None, None

    for attempt_query in [q for q in (query, fallback_query) if q]:
        try:
            resp = requests.get(
                "https://api.pexels.com/v1/search",
                headers={"Authorization": PEXELS_API_KEY},
                params={"query": attempt_query, "orientation": "landscape", "per_page": 15, "size": "large"},
                timeout=15,
            )
            resp.raise_for_status()
            photos = resp.json().get("photos", [])
            if not photos:
                continue  # 이 검색어로는 결과 없음 → 다음 후보 검색어로 재시도
            photo = photos[seed % len(photos)]
            img_url = photo["src"].get("large2x") or photo["src"].get("large") or photo["src"]["original"]
            img_resp = requests.get(img_url, timeout=20)
            img_resp.raise_for_status()
            img = Image.open(io.BytesIO(img_resp.content)).convert("RGB")

            # 비율 유지 크롭 후 리사이즈 (center-crop)
            target_ratio = size[0] / size[1]
            w, h = img.size
            cur_ratio = w / h
            if cur_ratio > target_ratio:
                new_w = int(h * target_ratio)
                left = (w - new_w) // 2
                img = img.crop((left, 0, left + new_w, h))
            else:
                new_h = int(w / target_ratio)
                top = (h - new_h) // 2
                img = img.crop((0, top, w, top + new_h))
            img = img.resize(size)

            credit = {
                "name": photo.get("photographer", "Unknown"),
                "photographer_url": photo.get("photographer_url", "https://www.pexels.com"),
                "photo_url": photo.get("url", "https://www.pexels.com"),
                "source": "Pexels",
            }
            return img, credit
        except Exception as e:
            logger.warning(f"[무료 이미지] Pexels 검색/다운로드 실패('{attempt_query}'): {e}")
            continue

    logger.warning("[무료 이미지] 모든 검색어로 실패해 그라데이션으로 대체합니다.")
    return None, None

def _wrap_by_pixel_width(draw, text: str, font, max_width: int) -> List[str]:
    words = text.split(" ")
    lines: List[str] = []
    current = ""
    def width_of(s: str) -> int: return draw.textbbox((0, 0), s, font=font)[2] - draw.textbbox((0, 0), s, font=font)[0]

    for word in words:
        candidate = f"{current} {word}".strip()
        if width_of(candidate) <= max_width:
            current = candidate
            continue
        if current:
            lines.append(current)
            current = ""
        if width_of(word) <= max_width:
            current = word
            continue
        chunk = ""
        for ch in word:
            if width_of(chunk + ch) <= max_width: chunk += ch
            else:
                if chunk: lines.append(chunk)
                chunk = ch
        current = chunk

    if current: lines.append(current)
    return lines

# =====================================================================
# [NEW] Canva 배경 이미지 로더 (무료 플랜 호환 — API 인증 불필요)
# =====================================================================
def _load_canva_background(category: str) -> Optional[Image.Image]:
    """canva_backgrounds/{category}.png (또는 .jpg/.webp)가 있으면 불러와 THUMB_SIZE로 맞춘다.
    없으면 None을 반환해 기존 랜덤 그라데이션 생성으로 자연스럽게 대체된다."""
    for ext in (".png", ".jpg", ".jpeg", ".webp"):
        path = os.path.join(CANVA_BG_DIR, f"{category}{ext}")
        if os.path.exists(path):
            try:
                img = Image.open(path).convert("RGB")
                if img.size != THUMB_SIZE:
                    img = img.resize(THUMB_SIZE)
                logger.info(f"[Canva 배경] {path} 사용")
                return img
            except Exception as e:
                logger.warning(f"[Canva 배경] {path} 로드 실패: {e}")
    return None

def generate_thumbnail(title: str, output_path: str, theme: Dict[str, Any], category: str = "번역감정", image_keywords: str = "", expression: str = "") -> Optional[Dict[str, str]]:
    expression_clean = (expression or "").strip()
    _generate_thumbnail_local(title, output_path, theme, expression_clean, category)
    return None

def _generate_thumbnail_local(title: str, output_path: str, theme: Dict[str, Any], expression: str, category: str = "번역감정") -> None:
    # [개편] Canva로 직접 디자인해 내보낸 배경(canva_backgrounds/{category}.png)이 있으면 그걸 쓰고,
    # 없으면 기존 랜덤 그라데이션 배경으로 자동 대체한다. 표현 텍스트/배지/포인트 바는 항상 코드로 얹는다.
    canva_bg = _load_canva_background(category)
    used_canva = canva_bg is not None
    if used_canva:
        img = canva_bg.convert("RGBA")
    else:
        seed = int(hashlib.md5(title.encode("utf-8")).hexdigest(), 16) % 100000
        img = _make_random_gradient_background(THUMB_SIZE, theme["gradient"], seed=seed).convert("RGBA")

    draw = ImageDraw.Draw(img)
    accent_rgb = _hex_to_rgb(theme["accent"])
    w, h = THUMB_SIZE

    if not used_canva:
        # 시그니처 텍스처: 카테고리 accent 색 사선 줄무늬를 배경 전체에 은은하게 (Canva 배경이 없을 때만)
        texture = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        tex_draw = ImageDraw.Draw(texture)
        stripe_gap = 52
        for x in range(-h, w, stripe_gap):
            tex_draw.line([(x, h), (x + h, 0)], fill=accent_rgb + (22,), width=6)
        img.alpha_composite(texture)
        draw = ImageDraw.Draw(img)

    if expression and len(expression) <= 20:
        expr_font_size = 128 if len(expression) <= 6 else (96 if len(expression) <= 10 else 68)
        expr_font = _load_font(expr_font_size)
        max_text_w = w - 100
        lines = _wrap_by_pixel_width(draw, expression, expr_font, max_text_w)[:2]
        line_h = expr_font_size + 16
        total_h = line_h * len(lines)
        ty = h // 2 - total_h // 2

        # [NEW] 퍼스널컬러: 표현 텍스트를 흰색 고정이 아니라, 카테고리(감정)의 accent 색을 바탕으로
        # 채움은 accent+화이트를 섞은 밝은 톤, 외곽선은 accent+블랙을 섞은 짙은 톤으로 배색해
        # 감정마다 다른 톤앤매너의 시그니처 텍스처가 되도록 한다.
        text_fill = _blend_rgb((255, 255, 255), accent_rgb, 0.22) + (255,)
        text_stroke = _blend_rgb(accent_rgb, (0, 0, 0), 0.55) + (240,)
        for line in lines:
            lb = draw.textbbox((0, 0), line, font=expr_font)
            tw = lb[2] - lb[0]
            tx = (w - tw) / 2 - lb[0]
            draw.text((tx, ty - lb[1]), line, font=expr_font, fill=text_fill,
                       stroke_width=5, stroke_fill=text_stroke)
            ty += line_h

    # 카테고리 배지 (브랜드 일관성 유지용 작은 라벨)
    label_font = _load_font(30)
    label_text = theme["label"]
    lb = draw.textbbox((0, 0), label_text, font=label_font)
    pad_x, pad_y = 18, 8
    badge_w = (lb[2] - lb[0]) + pad_x * 2
    badge_h = (lb[3] - lb[1]) + pad_y * 2
    badge_x, badge_y = 24, 24
    draw.rounded_rectangle([badge_x, badge_y, badge_x + badge_w, badge_y + badge_h], radius=badge_h // 2, fill=accent_rgb + (230,))
    draw.text((badge_x + pad_x, badge_y + pad_y - lb[1]), label_text, font=label_font, fill=(255, 255, 255, 255))

    bar_h = 18
    draw.rectangle([(0, THUMB_SIZE[1] - bar_h), (THUMB_SIZE[0], THUMB_SIZE[1])], fill=accent_rgb + (255,))

    img.convert("RGB").save(output_path, format="WEBP", quality=85, method=6)

BRAND_GRADIENT = [(15, 23, 42), (30, 41, 59), (51, 65, 85)]
BRAND_ACCENT = (250, 204, 21)
LOGO_SIZE = (512, 512)
BANNER_SIZE = (1600, 420)

def generate_site_logo(output_path: str) -> None:
    img = _make_gradient_background(LOGO_SIZE, BRAND_GRADIENT).convert("RGBA")
    draw = ImageDraw.Draw(img)
    w, h = LOGO_SIZE
    margin = 36
    draw.ellipse([margin, margin, w - margin, h - margin], outline=BRAND_ACCENT + (255,), width=10)
    initial = (SITE_TITLE.strip()[:1] or "B")
    font = _load_font(220)
    bbox = draw.textbbox((0, 0), initial, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((w - tw) / 2 - bbox[0], (h - th) / 2 - bbox[1]), initial, font=font, fill=(255, 255, 255, 255))
    img.convert("RGB").save(output_path, format="WEBP", quality=90)

def generate_site_banner(output_path: str) -> None:
    img = _make_gradient_background(BANNER_SIZE, BRAND_GRADIENT).convert("RGBA")
    draw = ImageDraw.Draw(img)
    w, h = BANNER_SIZE
    draw.rectangle([(0, 0), (w, 8)], fill=BRAND_ACCENT + (255,))
    title_font = _load_font(88)
    tagline_font = _load_font(32)
    tb = draw.textbbox((0, 0), SITE_TITLE, font=title_font)
    tw = tb[2] - tb[0]
    ty = h / 2 - 60
    draw.text(((w - tw) / 2, ty), SITE_TITLE, font=title_font, fill=(255, 255, 255, 255))
    lb = draw.textbbox((0, 0), SITE_TAGLINE, font=tagline_font)
    lw = lb[2] - lb[0]
    draw.text(((w - lw) / 2, ty + 110), SITE_TAGLINE, font=tagline_font, fill=BRAND_ACCENT + (255,))
    img.convert("RGB").save(output_path, format="WEBP", quality=88)

def ensure_brand_assets() -> None:
    os.makedirs(DOCS_DIR, exist_ok=True)
    logo_path = os.path.join(DOCS_DIR, "logo.webp")
    generate_site_logo(logo_path)
    generate_site_banner(os.path.join(DOCS_DIR, "banner.webp"))
    favicon_path = os.path.join(DOCS_DIR, "favicon.png")
    with Image.open(logo_path) as im:
        im.convert("RGB").resize((64, 64)).save(favicon_path, format="PNG")

# =====================================================================
# [NEW] PWA(프로그레시브 웹앱) 지원
# - 홈 화면에 앱 아이콘처럼 설치할 수 있도록 manifest.json, 아이콘(PNG), 서비스워커를 생성합니다.
# - 앱스토어/플레이스토어 등록이나 결제 기능은 포함하지 않으며, 순수 "설치형 웹앱" 수준입니다.
# =====================================================================
def generate_pwa_icons() -> None:
    logo_path = os.path.join(DOCS_DIR, "logo.webp")
    if not os.path.exists(logo_path):
        return
    with Image.open(logo_path) as im:
        im = im.convert("RGB")
        for size in (192, 512):
            im.resize((size, size)).save(os.path.join(DOCS_DIR, f"icon-{size}.png"), format="PNG")
        # 마스커블 아이콘(안드로이드가 원형/둥근모서리로 잘라도 안전하도록 여백을 둔 버전)
        maskable = Image.new("RGB", (512, 512), BRAND_GRADIENT[0])
        inner = im.resize((360, 360))
        maskable.paste(inner, (76, 76))
        maskable.save(os.path.join(DOCS_DIR, "icon-maskable-512.png"), format="PNG")

def generate_pwa_manifest() -> None:
    accent_hex = "#{:02x}{:02x}{:02x}".format(*BRAND_ACCENT)
    bg_hex = "#{:02x}{:02x}{:02x}".format(*BRAND_GRADIENT[0])
    # [FIX] "/"(도메인 루트) 절대경로는 GitHub Pages 프로젝트 사이트(예: 아이디.github.io/저장소명/)처럼
    # 하위 경로에 배포되면 실제로 존재하지 않는 루트를 가리켜 404가 나고 PWA 설치 배너가 뜨지 않는
    # 원인이 됨. manifest의 start_url/scope/icons는 manifest.json 자신의 위치 기준 상대경로로 지정해
    # 루트 배포든 하위경로 배포든(SITE_URL 설정과 무관하게) 항상 올바르게 동작하도록 함.
    manifest = {
        "id": ".",
        "name": SITE_TITLE,
        "short_name": SITE_TITLE[:12],
        "description": SITE_TAGLINE,
        "start_url": ".",
        "scope": ".",
        "display": "standalone",
        "background_color": bg_hex,
        "theme_color": accent_hex,
        "icons": [
            {"src": "icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
            {"src": "icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"},
            {"src": "icon-maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
        ],
    }
    with open(os.path.join(DOCS_DIR, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

def generate_service_worker() -> None:
    # 네트워크 우선(신선한 글을 놓치지 않도록) + 실패 시 캐시 폴백 정도의 최소 구현.
    # 블로그는 콘텐츠가 계속 갱신되므로 공격적인 캐싱은 피합니다.
    sw_js = """const CACHE_NAME = 'blog-pwa-v1';
self.addEventListener('install', (event) => {
  self.skipWaiting();
});
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(
      keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k))
    ))
  );
  self.clients.claim();
});
self.addEventListener('fetch', (event) => {
  if (event.request.method !== 'GET') return;
  event.respondWith(
    fetch(event.request)
      .then((resp) => {
        const copy = resp.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy));
        return resp;
      })
      .catch(() => caches.match(event.request))
  );
});
"""
    with open(os.path.join(DOCS_DIR, "sw.js"), "w", encoding="utf-8") as f:
        f.write(sw_js)

def ensure_pwa_assets() -> None:
    generate_pwa_icons()
    generate_pwa_manifest()
    generate_service_worker()

def _coupang_deeplink(search_url: str) -> Optional[str]:
    if not (COUPANG_ACCESS_KEY and COUPANG_SECRET_KEY): return None
    domain = "https://api-gateway.coupang.com"
    path = "/v2/providers/affiliate_open_api/apis/openapi/v1/deeplink"
    try:
        query = urllib.parse.urlencode({"coupangUrls": search_url})
        path_with_query = f"{path}?{query}"
        datetime_str = time.strftime("%y%m%dT%H%M%SZ", time.gmtime())
        message = datetime_str + "GET" + path_with_query
        signature = hmac.new(COUPANG_SECRET_KEY.encode(), message.encode(), hashlib.sha256).hexdigest()
        auth_header = f"CEA algorithm=HmacSHA256, access-key={COUPANG_ACCESS_KEY}, signed-date={datetime_str}, signature={signature}"
        resp = requests.get(domain + path_with_query, headers={"Authorization": auth_header, "Content-Type": "application/json"}, timeout=8)
        resp.raise_for_status()
        return resp.json()["data"][0]["shortenUrl"]
    except Exception as e:
        logger.warning(f"[쿠팡 딥링크] 발급 실패, 일반 링크로 대체: {e}")
        return None

def add_ymyl_disclaimer(article: Dict[str, Any]) -> Dict[str, Any]:
    theme = get_theme(article.get("category", "번역감정"))
    if not theme.get("ymyl"): return article
    disclaimer = (
        '<div style="background:#fff8e1;border:1px solid #ffe082;border-radius:10px;'
        'padding:14px 18px;margin:24px 0;font-size:0.92em;color:#5d4037;">'
        '⚠️ <b>안내:</b> 이 글은 일반적인 정보 제공 목적으로 작성되었으며, 특정 상품·기관을 보증하지 않습니다. '
        '금리, 자격 요건, 지원금액, 신청 기간 등은 수시로 바뀔 수 있으니 반드시 공식 채널에서 최신 정보를 확인하세요.</div>'
    )
    article["html_body"] += disclaimer
    return article

def _relevance_score(article: Dict[str, Any], candidate: Dict[str, Any]) -> float:
    score = 0.0
    if candidate.get("category") == article.get("category", "번역감정"): score += 3.0
    current_words = set(re.findall(r"[\w가-힣]+", (article.get("title", "") + " " + article.get("keyword", ""))))
    candidate_words = set(re.findall(r"[\w가-힣]+", candidate.get("title", "")))
    score += len(current_words & candidate_words) * 1.5
    return score

def add_internal_link(article: Dict[str, Any]) -> Dict[str, Any]:
    if not os.path.exists(POSTS_JSON): return article
    with open(POSTS_JSON, "r", encoding="utf-8") as f: posts = json.load(f)
    if not posts: return article
    scored = [(p, _relevance_score(article, p)) for p in posts]
    scored.sort(key=lambda x: x[1], reverse=True)
    top_pool = [p for p, s in scored[:5] if s > 0] or [p for p, s in scored[:5]]
    if not top_pool: return article
    weights = [max(s, 0.5) for p, s in scored[:len(top_pool)]]
    pick = random.choices(top_pool, weights=weights, k=1)[0]
    article["html_body"] += f'<p style="margin-top:2em;padding-top:1em;border-top:1px dashed #ddd;">🔗 이 글도 함께 보면 좋아요: <a href="../{pick["file"]}">{pick["title"]}</a></p>'
    return article

def _manual_ad_unit() -> str:
    if not (ADSENSE_CLIENT_ID and ADSENSE_SLOT_ID): return ""
    return (
        '<div style="margin:28px 0;text-align:center;">'
        f'<ins class="adsbygoogle" style="display:block" data-ad-client="{ADSENSE_CLIENT_ID}" '
        f'data-ad-slot="{ADSENSE_SLOT_ID}" data-ad-format="auto" data-full-width-responsive="true"></ins>'
        '<script>(adsbygoogle = window.adsbygoogle || []).push({});</script></div>'
    )

def insert_manual_ads(article: Dict[str, Any]) -> Dict[str, Any]:
    ad_html = _manual_ad_unit()
    if not ad_html: return article
    idx = article["html_body"].find("<h2")
    if idx != -1: article["html_body"] = article["html_body"][:idx] + ad_html + article["html_body"][idx:]
    else: article["html_body"] += ad_html
    return article

def _fetch_content_photo(image_keywords: str, category: str, seed: int, size=(1000, 560)):
    # 1차: 무료 AI 시그니처 캐릭터 만화 생성 (API 키 불필요)
    category_prompt = ILLUSTRATION_PROMPTS.get(category, ILLUSTRATION_PROMPTS["번역감정"])
    ai_img = _generate_ai_cartoon_image(f"{category_prompt}{ILLUSTRATION_SUFFIX}", size, seed)
    if ai_img is not None:
        return ai_img
    # 2차 폴백: Pexels 무료 스톡사진 (API 키가 설정된 경우만)
    fallback_query = STOCK_SEARCH_TERMS.get(category, STOCK_SEARCH_TERMS["번역감정"])
    photo, _credit = _fetch_stock_photo(image_keywords, fallback_query, size, seed)
    return photo

def enhance_tables(html_body: str, accent: str) -> str:
    counter = {"n": 0}
    def _style_cells(raw_table: str, min_width: int, is_modal: bool = False) -> str:
        # 1.5x 모달용 폰트 및 패딩 스케일 업 적용
        font_size = "1.5em" if is_modal else "0.92em"
        pad_th = "18px 21px" if is_modal else "12px 14px"
        pad_td = "18px 21px" if is_modal else "12px 14px"
        
        styled = re.sub(
            r"<table\b[^>]*>",
            f'<table style="width:100%;min-width:{min_width}px;border-collapse:collapse;overflow:hidden;font-size:{font_size};"',
            raw_table, count=1,
        )
        styled = re.sub(
            r"<th\b[^>]*>",
            f'<th style="padding:{pad_th};text-align:left;background:{accent}1f;font-weight:800;'
            f'color:#111;border-bottom:2px solid {accent}80;white-space:nowrap;word-break:keep-all;min-width:56px;">',
            styled,
        )
        styled = re.sub(
            r"<td\b[^>]*>",
            # [FIX] word-break:keep-all 없이는 좁은 열에서 한글 단어가 한 글자씩 쪼개져 세로로
            # 늘어지는 가독성 문제가 있었음. 단어 단위로만 줄바꿈되고, 최소 너비를 둬서 셀이
            # 지나치게 눌리지 않도록 수정.
            f'<td style="padding:{pad_td};text-align:left;border-bottom:1px solid #ececec;line-height:1.65;'
            f'vertical-align:top;word-break:keep-all;min-width:56px;">',
            styled,
        )
        return styled

    def wrap_table(match):
        counter["n"] += 1
        uid = f"tblzoom{counter['n']}_{random.randint(1000, 9999)}"
        table_html = match.group(0)
        styled_table = _style_cells(table_html, 460, False)
        # 모달 내부 표는 1.5배(1.5em 폰트) 커진 상태로 렌더링
        modal_table = _style_cells(table_html, 630, True)

        return (
            f'<div style="overflow-x:auto;overflow-y:hidden;-webkit-overflow-scrolling:touch;margin:1.2em 0 0.4em;'
            f'border-radius:8px;border:1px solid #eee;">{styled_table}</div>'
            f'<div style="text-align:right;margin:0 0 1.2em;">'
            f'<button type="button" onclick="document.getElementById(\'{uid}\').style.display=\'flex\';" '
            f'style="border:none;background:none;color:{accent};font-size:0.85em;font-weight:700;'
            f'cursor:pointer;padding:4px 2px;">🔍 표 크게 보기</button></div>'
            f'<div id="{uid}" '
            f'style="display:none;position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.82);'
            f'z-index:1000;align-items:center;justify-content:center;padding:16px;" '
            f'onclick="if(event.target===this){{this.style.display=\'none\';}}">'
            f'<div style="background:#fff;border-radius:12px;padding:24px;max-width:95vw;max-height:88vh;overflow:auto;">'
            f'<button type="button" onclick="document.getElementById(\'{uid}\').style.display=\'none\';" '
            f'style="display:block;margin:0 0 16px auto;width:36px;height:36px;border-radius:50%;'
            f'border:none;background:#f0f0f0;font-size:1.2em;cursor:pointer;">✕</button>'
            f'{modal_table}'
            f'</div></div>'
        )

    return re.sub(r"<table.*?</table>", wrap_table, html_body, flags=re.DOTALL)

def _tts_buttons_html(expression: str, theme: Dict[str, Any]) -> str:
    """말풍선 아이콘 클릭 시 배우는 한글 표현을 구글 번역 음성(정확한 발음)으로 들려주는 버튼.
    [FIX] 기기/폰트에 따라 💬 이모지가 깨져 보이는 문제가 있어, 어디서나 또렷하게 표시되는
    스피커 아이콘(🔊)으로 교체하고 원형 배지로 더 눈에 띄게 "마킹"했다."""
    expression = (expression or "").strip()
    if not expression or len(expression) > 20:
        return ""
    escaped = expression.replace("\\", "\\\\").replace("'", "\\'")
    accent = theme["accent"]
    return (
        '<div class="notranslate" translate="no" style="margin:4px 0 18px;">'
        f'<button type="button" onclick="playKoreanTTS(\'{escaped}\')" aria-label="발음 듣기 (Google 번역)" '
        f'style="display:inline-flex;align-items:center;gap:8px;background:{accent};border:none;color:#fff;'
        f'border-radius:24px;padding:9px 18px 9px 12px;font-size:0.9em;font-weight:700;cursor:pointer;'
        f'box-shadow:0 2px 8px rgba(0,0,0,0.18);">'
        f'<span style="display:inline-flex;align-items:center;justify-content:center;width:26px;height:26px;'
        f'border-radius:50%;background:rgba(255,255,255,0.25);font-size:1em;">🔊</span>'
        f'발음 듣기 (Google 번역)</button>'
        '</div>'
    )

def insert_content_image(article: Dict[str, Any], slug: str) -> Dict[str, Any]:
    category = article.get("category", "번역감정")
    theme = get_theme(category)

    # [FIX] 본문 중간에 별도로 넣던 삽화(figure)를 제거했습니다. 히어로 썸네일에 이미
    # 한글 표현이 큼직하게 들어가 있어 같은 캐릭터 그림이 본문에 또 나오면 중복이었습니다.
    # 발음 듣기 버튼만 "오늘의 표현" 바로 아래 남깁니다.
    extra_html = _tts_buttons_html(article.get("expression", ""), theme)
    if not extra_html:
        return article

    idx = article["html_body"].find("</h2>")
    if idx != -1: article["html_body"] = article["html_body"][:idx + 5] + extra_html + article["html_body"][idx + 5:]
    else: article["html_body"] = extra_html + article["html_body"]
    return article

def _fetch_product_icon(product_name: str, seed: int, size=(160, 160)):
    prompt = f"minimalist pencil sketch icon of {product_name}, single centered object, clean line art, simple outline, white background, no text, no watermark"
    url = f"https://image.pollinations.ai/prompt/{urllib.parse.quote(prompt)}?width={size[0]}&height={size[1]}&seed={seed}&nologo=true"
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        img = Image.open(io.BytesIO(resp.content)).convert("RGB")
        if img.size != size: img = img.resize(size)
        return img
    except Exception as e:
        logger.warning(f"[상품 아이콘] 생성 실패, 아이콘 없이 표시: {e}")
        return None

def build_product_list_html(article: Dict[str, Any], slug: str, accent: str) -> str:
    products = article.get("product_list") or []
    if not products: return ""
    os.makedirs(os.path.join(DOCS_DIR, "thumbs"), exist_ok=True)
    cards = []
    for i, item in enumerate(products[:6], 1):
        name = item.get("name", "")
        desc = item.get("description", "")
        seed = int(hashlib.md5(f"{slug}-product-{i}".encode("utf-8")).hexdigest(), 16) % 100000
        icon = _fetch_product_icon(name, seed)
        if icon is not None:
            icon_filename = f"{slug}-product{i}.webp"
            icon.save(os.path.join(DOCS_DIR, "thumbs", icon_filename), format="WEBP", quality=80)
            icon_html = f'<img src="../thumbs/{icon_filename}" alt="{name}" loading="lazy" style="width:56px;height:56px;border-radius:10px;object-fit:cover;flex-shrink:0;">'
        else:
            icon_html = f'<div style="width:56px;height:56px;border-radius:10px;background:{accent}22;flex-shrink:0;"></div>'

        cards.append(
            '<div style="display:flex;gap:14px;align-items:center;margin:10px 0;padding:12px 14px;'
            f'background:#f7f8fa;border-radius:10px;">{icon_html}'
            f'<div><p style="margin:0 0 3px;font-weight:700;color:#111;">{name}</p>'
            f'<p style="margin:0;color:#555;font-size:0.92em;line-height:1.5;">{desc}</p></div></div>'
        )
    return '<h2 style="margin-top:2em;">한눈에 보는 상품 목록</h2>' + "".join(cards)

def add_coupang_markup(article: Dict[str, Any]) -> Dict[str, Any]:
    product_keyword = (article.get("product_keyword") or "").strip()
    if not product_keyword: return article
    search_url = f"https://www.coupang.com/np/search?q={urllib.parse.quote(product_keyword)}"
    if COUPANG_PARTNER_TAG: search_url += f"&lptag={COUPANG_PARTNER_TAG}"
    link = _coupang_deeplink(search_url) or search_url
    extra_html = (
        f'<h2>관련 추천 상품</h2>'
        f'<p><a href="{link}" target="_blank" rel="nofollow sponsored">{product_keyword} 관련 인기 상품 보러가기</a></p>'
        '<p style="font-size:0.85em;color:#888;">이 포스팅은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다.</p>'
    )
    article["html_body"] += extra_html
    return article

def _font_family_name(font_param: str) -> str:
    return font_param.split(":")[0].replace("+", " ")

def _build_post_nav_html() -> str:
    prev_post = None
    if os.path.exists(POSTS_JSON):
        with open(POSTS_JSON, "r", encoding="utf-8") as f:
            posts = json.load(f)
        if posts: prev_post = posts[0]
    prev_html = (
        f'<a href="../{prev_post["file"]}"><img src="../{prev_post["thumb"]}" alt="이전 게시물">'
        f'<span>← 이전 게시물: {prev_post["title"]}</span></a>'
        if prev_post else '<a href="../index.html"><span class="nav-icon">🏠</span><span>목록으로</span></a>'
    )
    latest_html = '<a href="../index.html"><span class="nav-icon">📰</span><span>최신 게시물 보기</span></a>'
    return f'<div class="post-nav">{prev_html}{latest_html}</div>'

def _build_related_html(exclude_slug: str) -> str:
    if not os.path.exists(POSTS_JSON): return ""
    with open(POSTS_JSON, "r", encoding="utf-8") as f: posts = json.load(f)
    posts = [p for p in posts if p.get("file") != exclude_slug][:3]
    if not posts: return ""
    cards = "\n".join(
        f'<a class="related-card" href="../{p["file"]}"><img src="../{p["thumb"]}" alt="{p["title"]}" loading="lazy">'
        f'<span>{p["title"]}</span></a>' for p in posts
    )
    return f'<div class="related"><h3>📌 함께 보면 좋은 글</h3><div class="related-grid">{cards}</div></div>'

def save_post(article: Dict[str, Any]) -> Tuple[Dict[str, Any], str, str, str, str]:
    os.makedirs(POSTS_DIR, exist_ok=True)
    os.makedirs(os.path.join(DOCS_DIR, "thumbs"), exist_ok=True)
    category = article.get("category", "번역감정")
    theme = get_theme(category)
    slug = slugify(article["keyword"])
    today = datetime.now().strftime("%Y-%m-%d")
    thumb_filename = f"{slug}-{today}.webp"
    post_filename = f"{slug}-{today}.html"
    photo_credit = generate_thumbnail(article["title"], os.path.join(DOCS_DIR, "thumbs", thumb_filename), theme, category, article.get("image_keywords", ""), article.get("expression", ""))
    photo_credit_html = ""
    if photo_credit:
        photo_credit_html = (
            f'<p style="margin:6px 0 0;font-size:0.78em;color:#aaa;">'
            f'사진: <a href="{photo_credit["photo_url"]}" target="_blank" rel="nofollow noopener">'
            f'{photo_credit["name"]}</a> / {photo_credit["source"]} (무료 이미지, 출처 표기)</p>'
        )
    
    cleaned_body = re.sub(
        r"<h[23]>[^<]*자주\s*묻는\s*질문[^<]*</h[23]>.{0,400}?</table>",
        "", article["html_body"], flags=re.DOTALL | re.IGNORECASE
    )
    article["html_body"] = cleaned_body
    article["html_body"] = enhance_tables(article["html_body"], theme["accent"])
    article = insert_content_image(article, slug)
    article["html_body"] += build_faq_section_html(article, theme["accent"])
    article["html_body"] += build_product_list_html(article, slug, theme["accent"])
    
    post_url = f"{SITE_URL}/posts/{post_filename}" if SITE_URL else f"posts/{post_filename}"
    thumb_url = f"{SITE_URL}/thumbs/{thumb_filename}" if SITE_URL else f"../thumbs/{thumb_filename}"
    title = article["title"]
    json_ld = build_json_ld(article, post_url, thumb_url, today)
    
    html = POST_TEMPLATE.format(
        title=title,
        meta_description=article.get("meta_description", ""),
        date=today,
        html_body=article["html_body"],
        thumb_filename=thumb_filename,
        canonical_url=post_url,
        thumb_url=thumb_url,
        json_ld=json_ld,
        ga_snippet=_ga_snippet(),
        adsense_snippet=_adsense_snippet(),
        font=theme["font"],
        font_family=_font_family_name(theme["font"]),
        accent=theme["accent"],
        badge=theme["badge"],
        related_html=_build_related_html(exclude_slug=f"posts/{post_filename}"),
        post_nav=_build_post_nav_html(),
        decor_html=build_decor_html(theme, seed=slug),
        bottom_ad=_manual_ad_unit(),
        search_console_meta=_search_console_meta(),
        translate_widget=_translate_widget(),
        photo_credit_html=photo_credit_html,
        site_title_short=SITE_TITLE[:12],
        site_title=SITE_TITLE,
    )
    with open(os.path.join(POSTS_DIR, post_filename), "w", encoding="utf-8") as f:
        f.write(html)
        
    post_meta = {
        "title": title, "file": f"posts/{post_filename}", "thumb": f"thumbs/{thumb_filename}",
        "date": today, "category": category, "accent": theme["accent"], "badge": theme["badge"],
    }
    return post_meta, json_ld, thumb_url, os.path.join(DOCS_DIR, "thumbs", thumb_filename), post_url

def update_index(new_post: Dict[str, Any]) -> List[Dict[str, Any]]:
    os.makedirs(DOCS_DIR, exist_ok=True)
    posts = []
    if os.path.exists(POSTS_JSON):
        with open(POSTS_JSON, "r", encoding="utf-8") as f: posts = json.load(f)
    posts.insert(0, new_post)
    with open(POSTS_JSON, "w", encoding="utf-8") as f: json.dump(posts, f, ensure_ascii=False, indent=2)

    hero_posts, mid_posts, bottom_posts = posts[:1], posts[1:3], posts[3:]

    hero_html = ""
    if hero_posts:
        p = hero_posts[0]
        hero_html = (
            '<div class="tier-label">🔥 최신 이야기</div>'
            f'<a class="hero" href="{p["file"]}"><img src="{p["thumb"]}" alt="{p["title"]}" loading="eager" fetchpriority="high">'
            f'<div class="hero-body"><span class="hero-badge" style="background:{p.get("accent", "#e95c84")}">{p.get("badge", "💗 번역이 안 되는 감정")}</span>'
            f'<div class="hero-title">{p["title"]}</div><div class="date">{p["date"]}</div></div></a>'
        )
    mid_html = ""
    if mid_posts:
        cards = "\n".join(
            f'<a class="mid-card" href="{p["file"]}"><img src="{p["thumb"]}" alt="{p["title"]}" loading="lazy">'
            f'<div class="mid-body"><span class="badge-sm" style="background:{p.get("accent", "#e95c84")}">{p.get("badge", "💗 번역이 안 되는 감정")}</span>'
            f'<div class="mid-title">{p["title"]}</div><div class="date">{p["date"]}</div></div></a>' for p in mid_posts
        )
        mid_html = f'<div class="tier-label">📖 다음 이야기</div><div class="mid-grid">{cards}</div>'
    bottom_html = ""
    if bottom_posts:
        cards = "\n".join(
            f'<a class="bottom-card" href="{p["file"]}"><img src="{p["thumb"]}" alt="{p["title"]}" loading="lazy">'
            f'<div class="bottom-body"><span class="badge-sm" style="background:{p.get("accent", "#e95c84")}">{p.get("badge", "💗 번역이 안 되는 감정")}</span>'
            f'<div class="bottom-title">{p["title"]}</div></div></a>' for p in bottom_posts
        )
        bottom_html = f'<div class="tier-label">🗂️ 지난 글 모아보기</div><div class="bottom-grid">{cards}</div>'

    with open(os.path.join(DOCS_DIR, "index.html"), "w", encoding="utf-8") as f:
        category_pills = "".join(f'<span class="pill" style="background:{t["accent"]}">{t["badge"]}</span>' for t in CATEGORY_THEMES.values())
        f.write(INDEX_TEMPLATE.format(
            site_title=SITE_TITLE, site_tagline=SITE_TAGLINE, site_url=SITE_URL or ".", ga_snippet=_ga_snippet(),
            adsense_snippet=_adsense_snippet(), fonts_url=_google_fonts_url(),
            hero_html=hero_html, mid_html=mid_html, bottom_html=bottom_html, blog_json_ld=build_blog_index_json_ld(posts),
            category_pills=category_pills, search_console_meta=_search_console_meta(),
            footer_html='<div class="site-footer"><a href="about.html">블로그 소개</a>·<a href="privacy.html">개인정보처리방침</a>·<a href="contact.html">문의하기</a>'
                        f'<div style="margin-top:8px;">© {datetime.now().year} {SITE_TITLE}</div></div>',
            translate_widget=_translate_widget(),
            site_title_short=SITE_TITLE[:12],
        ))
    return posts

def generate_static_pages() -> None:
    os.makedirs(DOCS_DIR, exist_ok=True)
    common_kwargs = dict(site_title=SITE_TITLE, search_console_meta=_search_console_meta(), ga_snippet=_ga_snippet(), adsense_snippet=_adsense_snippet())
    pages = {
        "about.html": ("블로그 소개", f"<p>{SITE_TITLE}에 오신 것을 환영합니다.</p><p>{SITE_TAGLINE}</p><p>이 블로그는 다양한 주제의 정보를 정리해서 소개하며, 콘텐츠 제작 과정 일부에 AI 도구를 활용하고 있습니다. 게시된 정보는 참고용이며, 중요한 결정을 내리실 때는 반드시 공식 출처를 함께 확인해주세요.</p>"),
        "privacy.html": ("개인정보처리방침", "<p>본 블로그는 구글 애널리틱스(GA4) 및 구글 애드센스를 통해 방문자 통계와 광고를 제공할 수 있습니다. 이 과정에서 쿠키(Cookie)가 사용될 수 있으며, 쿠키를 통해 수집되는 정보에는 개인을 직접 식별할 수 있는 정보는 포함되지 않습니다.</p><h2>쿠키 및 광고</h2><p>구글을 포함한 제3자 광고 공급업체는 쿠키를 사용하여 사용자의 이전 방문 기록을 기반으로 광고를 게재합니다. 이용자는 <a href=\"https://adssettings.google.com\" target=\"_blank\">구글 광고 설정</a>에서 맞춤 광고를 비활성화할 수 있습니다.</p><h2>문의</h2><p>개인정보 관련 문의사항은 문의하기 페이지를 통해 연락 주시기 바랍니다.</p>"),
        "contact.html": ("문의하기", "<p>블로그 콘텐츠 관련 문의, 협업 제안, 오류 신고 등은 아래 이메일로 연락 주세요.</p><p><b>이메일:</b> 이 페이지의 문구를 직접 열어 본인의 연락처로 수정해주세요.</p>"),
    }
    for filename, (page_title, page_body) in pages.items():
        path = os.path.join(DOCS_DIR, filename)
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8") as f:
                f.write(STATIC_PAGE_TEMPLATE.format(page_title=page_title, page_body=page_body, **common_kwargs))

def update_dashboard(posts: List[Dict[str, Any]]) -> None:
    rows = "\n".join(f'<tr><td>{p["date"]}</td><td>{p["title"]}</td><td><a href="{p["file"]}">보기</a></td></tr>' for p in posts)
    with open(os.path.join(DOCS_DIR, "dashboard.html"), "w", encoding="utf-8") as f:
        f.write(DASHBOARD_TEMPLATE.format(site_title=SITE_TITLE, post_count=len(posts), rows=rows))

def update_seo_files(posts: List[Dict[str, Any]]) -> None:
    if not SITE_URL: return
    url_entries = "\n".join(f"<url><loc>{SITE_URL}/{p['file']}</loc></url>" for p in posts)
    with open(os.path.join(DOCS_DIR, "sitemap.xml"), "w", encoding="utf-8") as f: f.write(SITEMAP_TEMPLATE.format(site_url=SITE_URL, url_entries=url_entries))
    with open(os.path.join(DOCS_DIR, "robots.txt"), "w", encoding="utf-8") as f: f.write(ROBOTS_TXT.format(site_url=SITE_URL))

def _blogger_configured() -> bool: return bool(BLOGGER_BLOG_ID and GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET and GOOGLE_REFRESH_TOKEN)
def _get_blogger_access_token() -> str:
    resp = requests.post("https://oauth2.googleapis.com/token", data={"client_id": GOOGLE_CLIENT_ID, "client_secret": GOOGLE_CLIENT_SECRET, "refresh_token": GOOGLE_REFRESH_TOKEN, "grant_type": "refresh_token"}, timeout=15)
    if not resp.ok:
        # [FIX] invalid_grant(리프레시 토큰 만료/폐기) 등 원인을 그대로 노출
        raise RuntimeError(f"블로거 토큰 갱신 실패 (HTTP {resp.status_code}): {resp.text[:500]}")
    return resp.json()["access_token"]

def strip_interactive_widgets(html_body: str) -> str:
    """[FIX] 자체 사이트 전용 "표 크게 보기" 버튼/모달에 onclick 같은 인라인 JS가 들어있는데,
    Blogger/워드프레스 모두 보안상 이런 인라인 스크립트를 걸러내면서 태그 구조가 깨져 표가
    텍스트로 그대로 노출되는 원인이 되었습니다. 외부 플랫폼에는 이 인터랙티브 위젯을 제거하고
    정적인(스크롤 가능한) 표만 남깁니다."""
    # "🔍 표 크게 보기" 버튼 div
    html_body = re.sub(r'<div style="text-align:right;margin:0 0 1\.2em;">.*?</div>', '', html_body, flags=re.DOTALL)
    # 확대 모달 (바깥/안쪽 div 두 겹)
    html_body = re.sub(r'<div id="tblzoom[^"]*"[^>]*>.*?</div>\s*</div>', '', html_body, flags=re.DOTALL)
    # 혹시 남아있는 onclick 속성 전체 제거 (안전망)
    html_body = re.sub(r'\s*onclick="[^"]*"', '', html_body)
    return html_body

def convert_tables_to_lists_for_wordpress(html_body: str) -> str:
    """[FIX-5차·최종] style 속성을 다 제거해도 <table> 태그 자체가 여전히 텍스트로 노출되는 것을
    스크린샷으로 재확인 — 즉 워드프레스닷컴은 속성 유무와 무관하게 <table> 태그 자체를 콘텐츠
    저장 과정에서 정상 처리하지 못합니다(자체 kses 화이트리스트에서 table 계열 태그가 제외되어
    있는 것으로 추정). <table>을 아예 쓰지 않고 행 단위 목록(<ul><li>)으로 변환해 문제 자체를
    피해갑니다."""
    def _cell_text(cell_html: str) -> str:
        return re.sub(r'<[^>]+>', '', cell_html).strip()

    def _convert(m: "re.Match") -> str:
        table_html = m.group(0)
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', table_html, re.DOTALL)
        if not rows:
            return ''
        header_cells = [_cell_text(c) for c in re.findall(r'<t[hd][^>]*>(.*?)</t[hd]>', rows[0], re.DOTALL)]
        body_rows = rows[1:] if re.search(r'<th\b', rows[0]) else rows
        items = []
        for row in body_rows:
            cells = [_cell_text(c) for c in re.findall(r'<t[hd][^>]*>(.*?)</t[hd]>', row, re.DOTALL)]
            if not any(cells):
                continue
            # [FIX] 한 줄에 " · "로 몰아넣으면 가독성이 떨어진다는 피드백 반영.
            # 첫 열은 이 항목의 제목처럼 굵게, 나머지는 "라벨: 값" 형태로 줄바꿈해서 나열.
            first_cell, rest_cells = cells[0], cells[1:]
            lines = [f'<b>{first_cell}</b>']
            for i, cell in enumerate(rest_cells, start=1):
                if not cell:
                    continue
                label = header_cells[i] if i < len(header_cells) else ''
                lines.append(f'<b>{label}</b> {cell}' if label else cell)
            items.append('<li style="margin-bottom:10px;">' + '<br>'.join(lines) + '</li>')
        return '<ul>' + ''.join(items) + '</ul>' if items else ''

    return re.sub(r'<table\b.*?</table>', _convert, html_body, flags=re.DOTALL)

def _make_wordpress_images_responsive(html_body: str) -> str:
    """[FIX] style 속성을 제거하면서 고정 픽셀 width="1280" 같은 값만 남아, 좁은 모바일 화면에서도
    그대로 1280px로 렌더링되어 이미지가 화면 밖으로 넘치던 문제를 해결합니다. width는 100%로,
    height는 제거해 종횡비를 유지한 채 컨테이너 폭에 맞게 자동으로 줄어들게 합니다."""
    def _fix(m: "re.Match") -> str:
        tag = m.group(0)
        tag = re.sub(r'\swidth="\d+"', ' width="100%"', tag)
        tag = re.sub(r'\sheight="\d+"', '', tag)
        return tag
    return re.sub(r'<img\b[^>]*>', _fix, html_body)

def build_wordpress_gutenberg_content(html_body: str) -> str:
    """[FIX-5차·최종 원인 확정] <table> 태그 자체가 속성 유무와 무관하게 워드프레스닷컴에서
    텍스트로 노출되는 것으로 최종 확인됨. table을 목록으로 완전히 대체하고, 나머지 style 속성도
    kses 안전성을 위해 제거합니다."""
    html_body = strip_interactive_widgets(html_body)
    html_body = convert_tables_to_lists_for_wordpress(html_body)  # [FIX] <table> 자체를 배제
    html_body = re.sub(r'\s+style="[^"]*"', '', html_body)  # 나머지 style 속성도 안전을 위해 제거
    html_body = _make_wordpress_images_responsive(html_body)  # [FIX] 이미지 크기 오버 방지
    return html_body

def _make_blogger_safe_html(html_body: str) -> str:
    html_body = strip_interactive_widgets(html_body)  # [FIX] 표 확대 모달 등 인라인 JS 제거
    # [FIX] base64는 Blogger의 목록/요약(snippet) 자동 생성 로직에서 글자수 제한에 걸려
    # 이미지가 아예 안 뜨는 부작용이 있었음. 이제 run()에서 외부 발행 전 사전 push를 보장하므로
    # 실제 GitHub Pages 절대경로 URL을 그대로 사용해도 안전함.
    if SITE_URL:
        html_body = html_body.replace('href="../posts/', f'href="{SITE_URL}/posts/').replace('href="../thumbs/', f'href="{SITE_URL}/thumbs/').replace('src="../thumbs/', f'src="{SITE_URL}/thumbs/')
    else:
        html_body = re.sub(r'<img src="\.\./thumbs/[^"]*"[^>]*>', "", html_body)
        html_body = re.sub(r'<a href="\.\./(posts|thumbs)/[^"]*"[^>]*>(.*?)</a>', r"\2", html_body)
    return html_body

def publish_to_blogger(article: Dict[str, Any], canonical_url: str, thumb_url: str, local_thumb_path: str) -> Optional[str]:
    if not _blogger_configured():
        # [FIX] 기존에는 미설정 시 아무 로그 없이 조용히 건너뛰어, 파이프라인이 "성공"으로 표시돼도
        # 실제로는 Blogger에 아무것도 발행되지 않는 원인을 알 수 없었습니다. 어떤 시크릿이
        # 비어있는지 명시적으로 로그에 남깁니다.
        missing = [name for name, val in [
            ("BLOGGER_BLOG_ID", BLOGGER_BLOG_ID),
            ("GOOGLE_CLIENT_ID", GOOGLE_CLIENT_ID),
            ("GOOGLE_CLIENT_SECRET", GOOGLE_CLIENT_SECRET),
            ("GOOGLE_REFRESH_TOKEN", GOOGLE_REFRESH_TOKEN),
        ] if not val]
        logger.warning(f"[블로거] 미설정으로 건너뜁니다. (비어있는 값: {', '.join(missing)}) — GitHub Secrets에 등록되어 있는지 확인하세요.")
        return None
    try:
        access_token = _get_blogger_access_token()
        theme = get_theme(article.get("category", "번역감정"))
        today = datetime.now().strftime("%Y-%m-%d")
        blogger_json_ld = build_json_ld(article, canonical_url, thumb_url, today, platform="blogger")
        # [FIX] base64는 요약 스니펫 글자수 제한 안에서 이미지가 아예 안 뜨는 원인이었음.
        # 사전 push가 보장되므로 실제 GitHub Pages URL(thumb_url)을 그대로 사용.
        content_html = (
            f'{_translate_widget()}'
            f'<img src="{thumb_url}" style="max-width:100%;height:auto;border-radius:8px;display:block;" alt="{article["title"]}">'
            f'<span style="display:inline-block;background:{theme["accent"]};color:#fff;font-size:0.85em;font-weight:bold;padding:4px 12px;border-radius:999px;margin:14px 0 4px;">{theme["badge"]}</span>'
            f'{_make_blogger_safe_html(article["html_body"])}<script type="application/ld+json">{blogger_json_ld}</script>'
        )
        url = f"https://www.googleapis.com/blogger/v3/blogs/{BLOGGER_BLOG_ID}/posts/"
        # [FIX] 짧은 간격으로 연달아 요청하면 토큰/권한이 멀쩡해도 구글 쪽에서 일시적으로
        # 403/429/503을 반환하는 사례가 확인됨 (같은 토큰으로 몇 분 뒤 재시도하면 정상 발행됨).
        # 영구적 권한 문제와 구분하기 위해 지수 백오프로 최대 3회 재시도한다.
        last_error = None
        for attempt in range(1, 4):
            resp = requests.post(url, headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}, json={"title": article["title"], "content": content_html}, timeout=30)
            if resp.ok:
                blogger_url = resp.json().get("url")
                logger.info(f"[블로거] 발행 완료: {blogger_url or '(URL 확인 불가)'}")
                return blogger_url
            if resp.status_code in (403, 429, 503) and attempt < 3:
                wait = 20 * attempt
                logger.warning(f"[블로거] 일시적 오류({resp.status_code}), {wait}초 대기 후 재시도 ({attempt}/3): {resp.text[:200]}")
                time.sleep(wait)
                last_error = f"HTTP {resp.status_code}: {resp.text[:500]}"
                continue
            # [FIX] "403 Client Error: Forbidden"만으로는 원인(토큰 만료/권한 부족/블로그ID 불일치)을
            # 알 수 없었음. 구글이 실제로 보낸 에러 본문을 그대로 노출해 원인 특정이 가능하게 함.
            raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:500]}")
        raise RuntimeError(last_error or "알 수 없는 오류로 3회 재시도 모두 실패")
    except Exception as e:
        logger.error(f"[블로거] 발행 실패: {e}")
        return None

# =====================================================================
# [NEW] 워드프레스 동시 자동 발행 (워드프레스닷컴/Jetpack용 OAuth2 + 자체호스팅용 Basic Auth 자동 분기)
# - [FIX] *.wordpress.com 호스팅 사이트(예: kresonate.wordpress.com)는 자체 호스팅 워드프레스와 전혀
#   다른 API(public-api.wordpress.com)를 쓰고 Basic Auth(Application Password)를 지원하지 않습니다.
#   OAuth2만 가능합니다. 그래서 WORDPRESS_CLIENT_ID/SECRET이 설정되어 있으면 워드프레스닷컴 OAuth2
#   "password grant" 방식을 쓰고, 없으면 기존 자체호스팅용 Basic Auth 방식으로 동작합니다.
# - [워드프레스닷컴 준비물]
#   1) https://developer.wordpress.com/apps/new/ 에서 앱 등록 → Client ID / Client Secret 발급
#      (Redirect URI는 password grant에는 쓰이지 않으므로 아무 값이나 입력 가능, 예: https://localhost)
#   2) 워드프레스닷컴 계정 보안 설정(2단계 인증 활성화 후 my.wordpress.com/me/security)에서
#      Application Password 발급 → WORDPRESS_APP_PASSWORD 로 사용
#   3) WORDPRESS_URL에는 사이트 주소(예: kresonate.wordpress.com)를 입력
# - 미설정 시 조용히 건너뛰며(로그로 사유 표시), 실패해도 다른 발행 채널에는 영향 없습니다.
# =====================================================================
def _wordpress_configured() -> bool:
    return bool(WORDPRESS_URL and WORDPRESS_USERNAME and WORDPRESS_APP_PASSWORD)

def _wordpress_is_com_mode() -> bool:
    # Client ID/Secret이 있으면 워드프레스닷컴(OAuth2) 모드로 판단
    return bool(WORDPRESS_CLIENT_ID and WORDPRESS_CLIENT_SECRET)

def _get_wordpress_com_access_token() -> str:
    resp = requests.post(
        "https://public-api.wordpress.com/oauth2/token",
        data={
            "client_id": WORDPRESS_CLIENT_ID,
            "client_secret": WORDPRESS_CLIENT_SECRET,
            "grant_type": "password",
            "username": WORDPRESS_USERNAME,
            "password": WORDPRESS_APP_PASSWORD,
        },
        timeout=15,
    )
    if not resp.ok:
        # [FIX] resp.raise_for_status()만 쓰면 "400 Client Error"만 남고 정작 왜 실패했는지
        # (invalid_client/invalid_grant/invalid_request 등) 알 수 없었음 → 응답 본문을 그대로 노출
        raise RuntimeError(f"워드프레스닷컴 토큰 발급 실패 (HTTP {resp.status_code}): {resp.text[:500]}")
    data = resp.json()
    if "access_token" not in data:
        raise RuntimeError(f"워드프레스닷컴 토큰 발급 실패: {data}")
    return data["access_token"]

def _upload_media_to_wordpress_com(site: str, access_token: str, local_path: str) -> Optional[str]:
    """워드프레스닷컴 미디어 라이브러리에 로컬 이미지를 업로드하고, 실제 호스팅되는 공개 URL을 반환합니다.
    [FIX] base64 data URI는 워드프레스닷컴 콘텐츠 정제(sanitizer)가 보안상 걸러내어 이미지가
    통째로 깨지는 원인이었습니다. 대신 정식 미디어 업로드 API로 실제 URL을 발급받아 사용합니다."""
    try:
        with open(local_path, "rb") as f:
            files = {"media[]": (os.path.basename(local_path), f, "image/webp")}
            resp = requests.post(
                f"https://public-api.wordpress.com/rest/v1.1/sites/{site}/media/new",
                headers={"Authorization": f"Bearer {access_token}"},
                files=files,
                timeout=30,
            )
        if not resp.ok:
            logger.warning(f"[워드프레스] 미디어 업로드 실패 (HTTP {resp.status_code}): {resp.text[:300]}")
            return None
        media_list = resp.json().get("media", [])
        return media_list[0]["URL"] if media_list else None
    except Exception as e:
        logger.warning(f"[워드프레스] 미디어 업로드 실패 '{local_path}': {e}")
        return None

def _replace_thumbs_with_wordpress_media(html_body: str, site: str, access_token: str) -> str:
    """본문 속 '../thumbs/파일명' 상대경로 이미지를 워드프레스 미디어 라이브러리에 업로드한 뒤
    실제 URL로 치환합니다. 같은 파일이 여러 번 나와도 한 번만 업로드하도록 캐싱합니다."""
    uploaded_cache: Dict[str, Optional[str]] = {}

    def _replace(m: "re.Match") -> str:
        filename = m.group(1)
        if filename not in uploaded_cache:
            local_path = os.path.join(DOCS_DIR, "thumbs", filename)
            uploaded_cache[filename] = _upload_media_to_wordpress_com(site, access_token, local_path)
        hosted_url = uploaded_cache[filename]
        return f'src="{hosted_url}"' if hosted_url else m.group(0)

    return re.sub(r'src="\.\./thumbs/([^"]+)"', _replace, html_body)

def _publish_to_wordpress_com(article: Dict[str, Any], source_url: str, local_thumb_path: str) -> None:
    access_token = _get_wordpress_com_access_token()
    theme = get_theme(article.get("category", "번역감정"))
    site = WORDPRESS_URL.replace("https://", "").replace("http://", "").rstrip("/")

    thumb_hosted_url = _upload_media_to_wordpress_com(site, access_token, local_thumb_path)
    safe_body = _replace_thumbs_with_wordpress_media(article["html_body"], site, access_token)

    hero_html = (
        (f'<img src="{thumb_hosted_url}" alt="{article["title"]}" width="1280" height="720" /><br>' if thumb_hosted_url else "")
        + f'<span style="display:inline-block;background:{theme["accent"]};color:#fff;font-size:0.85em;'
        f'font-weight:bold;padding:4px 12px;border-radius:999px;margin:10px 0 4px;">{theme["badge"]}</span>'
    )
    # [FIX] 표만 워드프레스 네이티브 core/table 블록으로 변환하고 나머지는 HTML 블록으로 감쌈
    # (본문 전체를 하나의 Custom HTML 블록으로 통째로 감싸는 방식이 표 깨짐/앱 미리보기 불가의 원인이었음)
    content_html = build_wordpress_gutenberg_content(hero_html + safe_body)
    payload = {
        "title": article["title"],
        "content": content_html,
        "status": "publish",
        "excerpt": article.get("meta_description", ""),
    }
    resp = requests.post(
        f"https://public-api.wordpress.com/rest/v1.1/sites/{site}/posts/new",
        headers={"Authorization": f"Bearer {access_token}"},
        data=payload,
        timeout=30,
    )
    if not resp.ok:
        raise RuntimeError(f"워드프레스닷컴 글 발행 실패 (HTTP {resp.status_code}, site={site}): {resp.text[:500]}")
    logger.info(f"[워드프레스] 발행 완료(워드프레스닷컴): {resp.json().get('URL', '(URL 확인 불가)')}")

def _upload_media_to_wordpress_self_hosted(auth_header: str, local_path: str) -> Optional[Dict[str, Any]]:
    """자체호스팅 워드프레스 미디어 라이브러리에 업로드하고 {id, url}을 반환합니다."""
    try:
        with open(local_path, "rb") as f:
            img_bytes = f.read()
        resp = requests.post(
            f"{WORDPRESS_URL}/wp-json/wp/v2/media",
            headers={
                "Authorization": auth_header,
                "Content-Disposition": f'attachment; filename="{os.path.basename(local_path)}"',
                "Content-Type": "image/webp",
            },
            data=img_bytes,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        return {"id": data.get("id"), "url": data.get("source_url")}
    except Exception as e:
        logger.warning(f"[워드프레스] 미디어 업로드 실패 '{local_path}': {e}")
        return None

def _replace_thumbs_with_wordpress_self_hosted_media(html_body: str, auth_header: str) -> str:
    uploaded_cache: Dict[str, Optional[str]] = {}

    def _replace(m: "re.Match") -> str:
        filename = m.group(1)
        if filename not in uploaded_cache:
            local_path = os.path.join(DOCS_DIR, "thumbs", filename)
            media = _upload_media_to_wordpress_self_hosted(auth_header, local_path)
            uploaded_cache[filename] = media["url"] if media else None
        hosted_url = uploaded_cache[filename]
        return f'src="{hosted_url}"' if hosted_url else m.group(0)

    return re.sub(r'src="\.\./thumbs/([^"]+)"', _replace, html_body)

def _publish_to_wordpress_self_hosted(article: Dict[str, Any], canonical_url: str, local_thumb_path: str) -> None:
    auth_token = base64.b64encode(f"{WORDPRESS_USERNAME}:{WORDPRESS_APP_PASSWORD}".encode("utf-8")).decode("ascii")
    auth_header = f"Basic {auth_token}"
    theme = get_theme(article.get("category", "번역감정"))

    # 대표이미지(썸네일) 업로드 (실패해도 본문 발행은 계속 진행)
    featured_media_id = None
    thumb_media = _upload_media_to_wordpress_self_hosted(auth_header, local_thumb_path)
    if thumb_media:
        featured_media_id = thumb_media.get("id")

    # [FIX] base64 data URI는 워드프레스 콘텐츠 정제 필터가 걸러낼 수 있어(워드프레스닷컴에서 실제로 발생),
    # 자체호스팅에서도 동일 위험을 피하기 위해 실제 미디어 업로드 방식으로 통일
    safe_body = _replace_thumbs_with_wordpress_self_hosted_media(article["html_body"], auth_header)
    hero_html = (
        f'<span style="display:inline-block;background:{theme["accent"]};color:#fff;font-size:0.85em;'
        f'font-weight:bold;padding:4px 12px;border-radius:999px;margin:0 0 14px;">{theme["badge"]}</span>'
    )
    # [FIX] 표만 네이티브 core/table 블록으로 변환, 나머지는 HTML 블록으로 감쌈
    content_html = build_wordpress_gutenberg_content(hero_html + safe_body)
    payload = {
        "title": article["title"],
        "content": content_html,
        "status": "publish",
        "excerpt": article.get("meta_description", ""),
    }
    if featured_media_id:
        payload["featured_media"] = featured_media_id

    resp = requests.post(
        f"{WORDPRESS_URL}/wp-json/wp/v2/posts",
        headers={"Authorization": auth_header, "Content-Type": "application/json"},
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()
    logger.info(f"[워드프레스] 발행 완료(자체호스팅): {resp.json().get('link', '(URL 확인 불가)')}")

def publish_to_wordpress(article: Dict[str, Any], source_url: str, thumb_url: str, local_thumb_path: str) -> None:
    if not _wordpress_configured():
        missing = [name for name, val in [
            ("WORDPRESS_URL", WORDPRESS_URL),
            ("WORDPRESS_USERNAME", WORDPRESS_USERNAME),
            ("WORDPRESS_APP_PASSWORD", WORDPRESS_APP_PASSWORD),
        ] if not val]
        logger.info(f"[워드프레스] 미설정으로 건너뜁니다. (비어있는 값: {', '.join(missing)})")
        return
    try:
        if _wordpress_is_com_mode():
            _publish_to_wordpress_com(article, source_url, local_thumb_path)
        else:
            logger.warning(
                "[워드프레스] WORDPRESS_CLIENT_ID/SECRET이 없어 자체호스팅용 Basic Auth 방식을 시도합니다. "
                "워드프레스닷컴(*.wordpress.com) 사이트라면 이 방식은 항상 실패합니다 — "
                "https://developer.wordpress.com/apps/new/ 에서 앱을 등록하세요."
            )
            _publish_to_wordpress_self_hosted(article, source_url, local_thumb_path)
    except Exception as e:
        logger.error(f"[워드프레스] 발행 실패: {e}")

def ensure_nojekyll() -> None:
    os.makedirs(DOCS_DIR, exist_ok=True)
    if not os.path.exists(os.path.join(DOCS_DIR, ".nojekyll")):
        open(os.path.join(DOCS_DIR, ".nojekyll"), "w").close()

# =====================================================================
# [NEW] 외부 발행(Blogger/워드프레스) 전에 GitHub Pages로 먼저 push
# - [FIX] 기존에는 git 커밋/푸시가 워크플로의 더 나중 단계(별도 셸 스텝)에서 실행되어,
#   Blogger/워드프레스가 이미지 URL을 참조하는 시점엔 그 파일이 아직 GitHub Pages에
#   존재하지 않는 타이밍 버그가 있었습니다(base64로 임시 땜질했던 이유이기도 함).
# - 이제 파이썬 스크립트 안에서 외부 발행 직전에 먼저 커밋+푸시를 완료시켜, 이후
#   Blogger/워드프레스가 참조하는 GitHub Pages 이미지 URL이 항상 실제로 존재하도록 보장합니다.
# - 실패해도 예외를 던지지 않고 False만 반환합니다 (git push 실패가 전체 파이프라인을
#   중단시키지 않도록 하기 위함; 워크플로의 마지막 커밋 스텝이 안전망으로 남아있음).
# =====================================================================
def commit_and_push_changes() -> bool:
    try:
        subprocess.run(["git", "config", "user.name", "auto-blog-bot"], check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "auto-blog-bot@users.noreply.github.com"], check=True, capture_output=True)
        subprocess.run(["git", "add", "docs", "keywords_queue.json"], check=True, capture_output=True)
        diff_check = subprocess.run(["git", "diff", "--cached", "--quiet"])
        if diff_check.returncode == 0:
            logger.info("[git] 변경사항 없음, 사전 push 생략")
            return True
        commit_msg = f"자동 파이프라인 실행(사전 push): {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        subprocess.run(["git", "commit", "-m", commit_msg], check=True, capture_output=True)
        subprocess.run(["git", "push"], check=True, capture_output=True)
        logger.info("[git] GitHub Pages 사전 push 완료 (외부 발행 시 이미지 URL이 실제로 존재함을 보장)")
        return True
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.decode("utf-8", errors="replace") if e.stderr else str(e)
        logger.warning(f"[git] 사전 push 실패, 외부 발행 시 이미지가 일시적으로 깨질 수 있습니다: {stderr[:300]}")
        return False

def run() -> None:
    is_refresh_only = len(sys.argv) > 1 and sys.argv[1].strip().lower() == "refresh"

    # [개편] 트렌드 감지 대신 에버그린 주제뱅크에서 큐를 보충
    refill_evergreen_queue()
    if is_refresh_only:
        return

    # 수동 제목 입력 여부 확인
    manual_title = ""
    if len(sys.argv) > 1 and sys.argv[1].strip() and sys.argv[1].strip().lower() not in ["publish", "refresh"]:
        manual_title = sys.argv[1].strip()

    # [NEW] 수동 실행(workflow_dispatch)은 제목 입력 여부와 무관하게 발행 한도를 적용하지 않는다.
    # 자동 실행(schedule/cron)에만 "하루 랜덤 2회" 제한을 적용한다.
    is_manual_trigger = GITHUB_EVENT_NAME == "workflow_dispatch"

    title = ""
    if manual_title:
        title = manual_title
    else:
        if is_manual_trigger:
            logger.info("[수동 실행] workflow_dispatch로 직접 실행되어 발행 한도를 적용하지 않습니다.")
        else:
            # [개편] 하루 총 발행 한도(2회) + 무작위 시간대 분산으로 콘텐츠 팜화 방지
            if not check_daily_limit():
                logger.info(f"오늘의 발행 한도({DAILY_PUBLISH_LIMIT}회)를 모두 소진하여 포스팅을 생략합니다.")
                return
            if not _should_publish_now_random():
                logger.info("[랜덤 발행 판정] 이번 시각은 건너뜁니다 (다음 정각에 다시 판정).")
                return

        queue = load_queue()
        if not queue.get("pending"):
            logger.info("대기 중인 에버그린 주제가 없습니다. EVERGREEN_TOPIC_BANK를 확인해주세요.")
            return
            
        title = pick_next_topic(queue)
        if not title:
            logger.info("대기 중인 에버그린 주제가 없습니다. EVERGREEN_TOPIC_BANK를 확인해주세요.")
            return
        queue.setdefault("completed", []).append(title)
        save_queue(queue)

    logger.info(f"[처리 시작] 제목: {title}")

    ensure_nojekyll()
    ensure_brand_assets()
    ensure_pwa_assets()  # [NEW] PWA 매니페스트/아이콘/서비스워커
    generate_static_pages()

    article = generate_article(title)
    article = fix_character_count_claims(article)  # [NEW] AI의 글자 수 오기재를 Python이 강제 교정
    logger.info(f"글 생성 완료: {article['title']}")

    article = add_internal_link(article)
    article = insert_manual_ads(article)
    article = add_coupang_markup(article)
    article = add_ymyl_disclaimer(article)

    post_meta, json_ld, thumb_url, local_thumb_path, post_url = save_post(article)
    posts = update_index(post_meta)

    update_dashboard(posts)
    update_seo_files(posts)

    commit_and_push_changes()  # [NEW] 외부 발행 전 GitHub Pages에 이미지가 실제로 존재하도록 먼저 push

    blogger_url = publish_to_blogger(article, post_url, thumb_url, local_thumb_path)
    # [FIX] 워드프레스/블로거 본문 하단 "원문" 링크는 요청에 따라 완전히 제거함.
    # source_url 인자는 더 이상 본문에 노출되지 않지만, 추후 필요시를 대비해 시그니처는 유지.
    publish_to_wordpress(article, blogger_url or post_url, thumb_url, local_thumb_path)

    if not manual_title and not is_manual_trigger:
        increment_daily_count()

    logger.info(f"저장 완료: docs/{post_meta['file']}, docs/{post_meta['thumb']}")


if __name__ == "__main__":
    try:
        run()
    except Exception as e:
        logger.error(f"스크립트 실행 중 치명적인 오류 발생: {e}")
        sys.exit(1)
