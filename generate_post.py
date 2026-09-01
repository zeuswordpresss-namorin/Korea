# -*- coding: utf-8 -*-
"""
GitHub Actions 위에서 실행되는 자동 블로그 파이프라인 스크립트 (통합판)

[전면 개편] "한국어를 배우면 한국인이 보인다" - 외국인 대상 한국어 표현·한국인 사고방식 블로그
- 주인공은 단어가 아니라 한국인의 사고방식과 문화 (번역이 어려운 감정 / 매일 쓰는 말 / 한국 문화 / 리액션)
- H.O.L.D. 내러티브(Hook → Obstacle → Loop → Deliver)로 읽히게 하되, 소제목·순서·훅 스타일을 매 글마다 무작위로 변주
  (고정 5단 문구/순서 반복을 피해서 AdSense "패턴화된 AI 대량생산" 리스크를 낮춤)
- 문화 섹션은 무출처 단정 표현을 완화 ("~인 경우가 많다", "많은 한국인에게 ~로 느껴진다" 등)
- 에버그린 주제 뱅크(100개 표현/문화 주제, 4개 카테고리 요일별 로테이션) 기반, 하루 발행 상한
- [업그레이드] 방문자 언어 감지 자동 번역 (버튼 숨김) 및 표 1.5배 확대 기능
- [AdSense] 심사 모드(ADSENSE_REVIEW_MODE): 본문 수동광고·제휴 블록 생략, 품질 게이트,
  편집 고지, Blogger About/Privacy/Contact 페이지 동기화, 라벨 구조화
- [SNS] Blogger 발행 성공 후 Threads·Instagram Graph API 자동 공유 (Secrets 설정 시에만)
- [SEO] 제목 Meaning/What Does 패턴, 검색형 H2, Topic Cluster 내부링크 2~3개, 문화 단정 완화
"""

import base64
import hashlib
import hmac
import html
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

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas as pdf_canvas
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    _REPORTLAB_AVAILABLE = True
except ImportError:
    _REPORTLAB_AVAILABLE = False

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
# [NEW] 타깃(외국인 한국어 학습자)이 3초 안에 "누구를 위한 블로그인지" 파악하도록 영문 슬로건을 전면 배치
ENGLISH_SLOGAN = os.environ.get("ENGLISH_SLOGAN", "Learn Korean, Understand Koreans: Language &amp; Cultural Insights")

# --- [NEW] SNS 채널 (설정된 것만 홈페이지 하단에 아이콘으로 노출, 없으면 자동으로 숨김) ---
SNS_PINTEREST_URL = os.environ.get("SNS_PINTEREST_URL", "")
SNS_INSTAGRAM_URL = os.environ.get("SNS_INSTAGRAM_URL", "")
SNS_X_URL = os.environ.get("SNS_X_URL", "")

# --- [NEW] Threads / Instagram 자동 발행 (Blogger 성공 직후)
# Threads: Meta 개발자 앱(Threads use case) + threads_basic, threads_content_publish
# Instagram: Professional(Business/Creator) + Facebook Page 연결 + instagram_content_publish
# 미설정 시 조용히 건너뜀. 실패해도 Blogger 발행 결과는 유지.
THREADS_ENABLED = os.environ.get("THREADS_ENABLED", "true").strip().lower() in ("1", "true", "yes", "y")
THREADS_USER_ID = os.environ.get("THREADS_USER_ID", "").strip()
THREADS_ACCESS_TOKEN = os.environ.get("THREADS_ACCESS_TOKEN", "").strip()
THREADS_API_BASE = os.environ.get("THREADS_API_BASE", "https://graph.threads.net/v1.0").rstrip("/")

INSTAGRAM_ENABLED = os.environ.get("INSTAGRAM_ENABLED", "true").strip().lower() in ("1", "true", "yes", "y")
INSTAGRAM_USER_ID = os.environ.get("INSTAGRAM_USER_ID", "").strip()  # IG Professional user id
INSTAGRAM_ACCESS_TOKEN = os.environ.get("INSTAGRAM_ACCESS_TOKEN", "").strip()
INSTAGRAM_API_BASE = os.environ.get("INSTAGRAM_API_BASE", "https://graph.facebook.com/v21.0").rstrip("/")
SITE_URL = os.environ.get("SITE_URL", "").rstrip("/")
GA_MEASUREMENT_ID = os.environ.get("GA_MEASUREMENT_ID", "")
GOOGLE_SITE_VERIFICATION = os.environ.get("GOOGLE_SITE_VERIFICATION", "")
ADSENSE_CLIENT_ID = os.environ.get("ADSENSE_CLIENT_ID", "")
ADSENSE_SLOT_ID = os.environ.get("ADSENSE_SLOT_ID", "")
# [AdSense] 심사·초기 운영: true면 본문 수동 광고 유닛·제휴 마크업을 넣지 않음.
# Blogger "자동 광고"만 쓰는 편이 심사에 유리. 승인 후 GitHub Secrets에서 false로 전환.
ADSENSE_REVIEW_MODE = os.environ.get("ADSENSE_REVIEW_MODE", "true").strip().lower() in ("1", "true", "yes", "y")
# 본문 텍스트(HTML 태그 제외) 최소 글자 수 — 미달 시 1회 재생성
ADSENSE_MIN_BODY_CHARS = int(os.environ.get("ADSENSE_MIN_BODY_CHARS", "700"))
CONTACT_EMAIL = os.environ.get("CONTACT_EMAIL", "")
# true면 하루에 최대 1회 repair_old_posts()를 발행 파이프라인 시작 시 자동 실행 (고정 템플릿 잔존 정리)
AUTO_REPAIR_ONCE_PER_DAY = os.environ.get("AUTO_REPAIR_ONCE_PER_DAY", "true").strip().lower() in ("1", "true", "yes", "y")
# 실제 Blogger About/Privacy/Contact URL (Posts로 올라간 경우 /p/ 경로가 아님)
# 기본값: learnkoreanseekoreans.blogspot.com 현재 주소. 다른 블로그면 Secrets로 덮어쓰기.
BLOGGER_ABOUT_URL = os.environ.get(
    "BLOGGER_ABOUT_URL",
    "https://learnkoreanseekoreans.blogspot.com/2026/08/about.html",
).rstrip("/")
BLOGGER_PRIVACY_URL = os.environ.get(
    "BLOGGER_PRIVACY_URL",
    "https://learnkoreanseekoreans.blogspot.com/2026/08/privacy-policy.html",
).rstrip("/")
BLOGGER_CONTACT_URL = os.environ.get(
    "BLOGGER_CONTACT_URL",
    "https://learnkoreanseekoreans.blogspot.com/2026/08/contact.html",
).rstrip("/")

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
# [인스타툰 한컷] 표현→실제 사용 순간 시각화 (4:5, Instagram/Threads 단일)
INSTATOON_SIZE = (1080, 1350)  # 4:5 피드
INSTATOON_PUBLIC_DIR = os.path.join(DOCS_DIR, "instatoon")
INSTATOON_DOWNLOAD_DIR = os.environ.get("INSTATOON_DOWNLOAD_DIR", "downloads/instatoon")
INSTATOON_CUTS = 1
# [NEW] 구글 블로그(Blogger)만 메인으로 발행하고, GitHub Pages는 이미지 호스팅(docs/thumbs)과
# posts.json(내부 상태) 용도로만 남긴다. 개별 글 페이지·홈페이지(index.html)·sitemap.xml처럼
# "공개 사이트"로 보일 수 있는 산출물은 더 이상 만들지 않는다 (중복 콘텐츠 방지).
PUBLISH_GITHUB_PAGES_SITE = False
POSTS_JSON = os.path.join(DOCS_DIR, "posts.json")

GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.5-flash:generateContent?key={api_key}"
)

# [전면 개편 + H.O.L.D. 업그레이드] 고정 5단 문구/순서 금지 → 매 글 변주 + 스토리텔링 구조
SYSTEM_PROMPT = """당신은 외국인에게 한국어와 한국인의 사고방식을 설명하는 전문 에디터입니다.
이 블로그의 콘셉트는 "한국어를 배우면 한국인이 보인다"입니다. 주인공은 단어가 아니라, 그 단어 뒤에 숨은 한국인의 사고방식과 문화입니다.
독자는 한국어를 배우는 외국인이며, 사전적 정의가 아니라 "왜 이 표현이 그 나라 말로는 설명이 안 되는지", "실제 한국인은 언제 이 말을 쓰는지"를 궁금해합니다.

[H.O.L.D. 내러티브 — 글 전체 흐름에 반드시 녹여라]
글은 단순한 정보 나열이 아니라 짧은 스토리처럼 읽혀야 한다. 다음 4단계를 본문 흐름에 자연스럽게 반영한다.
- H (HOOK): 첫 1~2문장에서 독자가 "멈출 이유"를 준다. 표현 뜻을 바로 나열하지 말고, 독자가 겪어봤을 법한 구체적 순간·짧은 장면·질문으로 시작한다. (예: 막연한 "작년에 차를 사고 싶었다" 대신 "첫 차를 사려고 2년을 모았다"처럼 그 사람에게 중요한 일로 느끼게 한다.)
- O (OBSTACLE): 중간에 "문제/긴장"을 넣는다. 직역이 안 되는 이유, 오해하기 쉬운 뉘앙스, 외국인이 실제로 겪는 당황·오역 순간 등. 독자가 "그래서 어떻게 되지?"라고 궁금하게 만든다.
- L (LOOP): 바로 답을 주지 말고, 두 가지 결말(이해하느냐 / 계속 오해하느냐, 또는 쓸 수 있느냐 / 어색해지느냐) 사이에 잠시 머무르게 한다. "그는 결국 차를 살까요?"처럼 열린 질문을 한 번 심어두어 다음 단락이 궁금하게 만든다.
- D (DELIVER): 독자가 기다리던 핵심(표현의 진짜 뉘앙스 + 실제 사용법 + 작은 감정적 보상)을 준다. "끝까지 본 게 아깝지 않게" 정리하고, 구체적·답하기 쉬운 참여 질문으로 끝낸다.

[콘텐츠 5개 기둥 — 반드시 모두 다루되, 소제목 문구·순서·개수는 매 글마다 변주한다]
아래 5가지 내용을 글 안에 빠짐없이 담는다. 다만 H2 소제목 문구와 순서는 고정하지 않는다. 매 글마다 아래 후보 중에서 골라 섞거나 직접 비슷한 톤으로 새로 만들어, "패턴화된 동일 템플릿"이 되지 않게 한다.
1) 표현 소개 + 훅: 한국어 원문, 간결한 뜻, 누구에게/어떤 상황에서 쓰는지. 반드시 훅으로 연다.
2) 직역이 안 되는 이유: 영어(또는 다른 언어)의 가장 가까운 단어와 비교하고, 그 단어가 못 담는 한국인만의 뉘앙스를 설명한다. 표현의 한국어 원문을 최소 1회 <strong>으로 강조한다.
3) 실제 사용 장면: 대화체에 가까운 일상 예시 1~2개 (누가, 어떤 상황에서, 어떤 말투로). 가능하면 <ul><li>로 정리한다.
4) 문화/관계 맥락: 이 표현이 관계·일상과 어떻게 맞닿는지. [중요 — 단정 완화]
   금지에 가까운 표현: "한국인은 항상/절대/모두", "obsessed with", "한국 문화는 ~이다"(단정).
   권장: "이 표현은 흔히 ~한 맥락에서 설명됩니다", "한 가지 배경으로 자주 언급되는 것은 ~입니다",
   "나이·지역·관계에 따라 뉘앙스가 달라질 수 있습니다", "learners often notice that…".
   역사·사회 배경을 들 때는 인과를 단정하지 말고 "한 가지 해석으로는", "종종 연결해 설명하곤 합니다" 정도만 쓴다.
5) 참여형 클로징: 막연한 "어떻게 생각하세요?" 대신, 한 가지만 떠올리면 바로 답할 수 있는 구체적 질문 1~2개.

H2 소제목 변주 예시 (그대로 복사하지 말고, 표현명을 넣어 매번 다르게):
- Meaning: What Does "표현" Mean?, The Core Meaning of "표현"
- Usage: When Do Koreans Say "표현"?, Real Situations for "표현"
- Translation gap: Why "표현" Does Not Translate Directly, Closest English Words and Their Limits
- Examples: Example Dialogues with "표현", How It Sounds in Conversation
- Culture (완화): One Cultural Context Behind "표현", What Learners Often Notice About "표현"
- Reader prompt: How Would You Say This in Your Language?, Is There a Similar Phrase Where You Live?

섹션 순서는 고정하지 않는다. 예: 훅→직역 문제→사용 예시→문화→참여 / 훅→사용 예시→직역 문제→문화→참여 / 훅→문화 긴장→직역→사용→참여 등. 다만 글 앞부분에 훅이, 맨 끝에 참여 질문이 오는 흐름은 유지한다. H2는 4~6개 사이로 자연스럽게 나눈다.

아래 규칙을 지켜 작성하세요:
1. [SEO 제목 — 매우 중요] 영어권 검색 의도 "what does X mean" / "X meaning in Korean"에 맞춘다.
   우선 패턴(표현마다 조금씩 다르게 고른다):
   - "표현" Meaning in Korean: What Does It Really Mean?
   - What Does "표현" Mean? Korean Expression Explained
   - "표현" Meaning: What Koreans Actually Mean
   - Why "표현" Has No Direct English Translation
   표현의 한국어 원문을 반드시 제목에 쌍따옴표(" ")로 감싸 넣고, Meaning / What Does 를 제목 앞쪽에 두는 것을 우선한다.
   피해야 할 것: "Are Obsessed With", "Always", "Never", "All Koreans" 같은 강한 일반화·자극 제목.
   길이 약 40~70자(영문 기준).
1-1. meta_description: 표현을 맨 앞에 두고, meaning + when Koreans use it + culture nuance 를 100~140자로.
   예: What does "밥 한번 먹자" mean in Korean? Learn when people say it, why it is not always a firm plan, and the cultural nuance.
2. 소제목(H2)은 검색·스캔에 유리한 영어 중심 문구를 섞는다(매 글 변주). 예:
   - What Does "표현" Mean?
   - When Do Koreans Actually Say "표현"?
   - Why Doesn't "표현" Translate Directly?
   - Examples of "표현" in Real Korean
   - What This Expression Hints About Korean Culture
   - How Would You Say Something Similar in Your Language?
   한국어 고정 5단("오늘의 표현" / "왜 영어로…" / …)을 그대로 반복하지 않는다.
3. [문체/가독성 — 매우 중요] AI 특유의 어색한 말투를 피한다:
   - 모든 문단을 "~일까요?", "~습니다!" 같은 같은 패턴으로 끝맺지 말고 평서문/의문문/짧은 문장을 자연스럽게 섞는다.
   - 같은 내용을 표현만 바꿔 반복하지 않는다(패딩 금지). 한 문단에서 한 이야기를 하면 다음 문단은 반드시 새로운 정보로 넘어간다.
   - "정말", "충격적인", "놀라운" 같은 과장 수식어는 글 전체에서 1~2회 이하로 아껴 쓴다.
   - 문단은 2~4문장, 대략 60~90자 내외로 짧게 끊어 모바일 가독성을 높인다.
   - 친한 친구에게 설명하듯 구체적 사례·대화 예시 위주로 쓰고, 막연한 감탄으로 문단을 채우지 않는다.
4. [친근한 톤앤매너] 친근하고 공감대를 형성하는 어조. 독자를 "여러분"으로 자연스럽게 지칭하며 대화하듯 풀어쓴다.
5. 글자 수는 900~1400자 내외 (모바일에서 가볍게 읽히는 짧은 분량).
6. 직역 불가 설명 구간에 표현의 한국어 원문을 최소 1회 <strong>으로 강조한다.
7. 사용 예시 구간은 가능하면 <ul> 목록으로 1~2개를 정리한다.
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
12. "expression"에는 다루는 한국어 표현의 순수 원문만 담는다. 설명·이모지·괄호 없이 단어/구절 그대로. (예: "민망하다", "정", "수고했어요")
14. [AdSense·품질] 검색 키워드 나열·동의어 반복으로 분량을 채우지 않는다. 각 글은 그 표현만의 구체적 대화 예시·상황 1~2개를 반드시 포함한다. 다른 글과 문장 구조를 복붙한 듯한 도입부("오늘은 ~를 알아보겠습니다" 상투구)를 피한다.
15. [학습 가치] 독자가 읽고 나서 "언제 이 말을 쓰면 되는지"를 실천할 수 있을 정도로 구체적으로 쓴다. 추상적 감탄만으로 끝내지 않는다.
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
html_body는 <h2>, <p>, <ul>, <strong> 등을 사용한 HTML 조각으로 작성한다. H2 문구·순서는 매 글 변주한다."""

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
#   실제 제목·본문은 SYSTEM_PROMPT의 H.O.L.D. + 변주 가능 5개 기둥에 따라 생성됩니다.
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


# =====================================================================
# [SEO] Topic Cluster — 내부링크를 같은 주제 묶음으로 연결 (진단 권고)
# Greetings / Relationship / Emotions·Reactions / Culture
# =====================================================================
TOPIC_CLUSTERS: Dict[str, List[str]] = {
    "greetings": [
        "안녕하세요", "식사하셨어요", "잘 지내시죠", "수고하셨습니다", "별말씀을요",
        "괜찮아요", "수고했어요", "다녀오겠습니다", "조심히 들어가세요", "다음에 봐요",
        "감사합니다 정말로", "화이팅", "힘내세요", "축하드려요",
    ],
    "relationship": [
        "밥 한번 먹자", "우리", "정(情)", "정", "눈치", "밥 사는 문화", "정 나눔 선물 문화",
        "정 문화", "눈치 문화", "신세 많이 졌습니다", "신경 쓰지 마세요", "괜찮으시면",
    ],
    "emotions": [
        "헐", "대박", "어머", "아이고", "헉", "어이없다", "답답하다", "아쉽다", "서운하다",
        "민망하다", "섭섭하다", "허전하다", "짠하다", "뭉클하다", "억울하다", "속상하다",
        "당황스럽다", "기가 막히다", "웃프다", "찜찜하다", "든든하다",
    ],
    "culture": [
        "나이 문화", "한국식 나이 계산법", "한국식 나이 서열", "동안 문화", "동안",
        "존댓말", "존댓말 반말 전환 시점", "회식 문화", "선후배 문화", "서열 문화",
        "빨리빨리 문화", "단체 문화", "한국의 집단주의 정서", "정 많은 민족성",
        "눈치껏 행동하기", "한국식 인사법", "한국식 배려",
    ],
}


def _normalize_topic_key(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"[\(（].*?[\)）]", "", s)
    return s.strip()


def _cluster_for_topic(topic_or_expr: str) -> Optional[str]:
    key = _normalize_topic_key(topic_or_expr)
    if not key:
        return None
    for cname, members in TOPIC_CLUSTERS.items():
        for m in members:
            mk = _normalize_topic_key(m)
            if key == mk or key in m or mk in key:
                return cname
    return None


def _cluster_for_article(article: Dict[str, Any]) -> Optional[str]:
    for field in ("expression", "keyword", "title"):
        c = _cluster_for_topic(str(article.get(field) or ""))
        if c:
            return c
    cat = article.get("category") or ""
    if cat == "일상표현":
        return "greetings"
    if cat in ("번역감정", "리액션"):
        return "emotions"
    if cat == "한국문화":
        return "culture"
    return None


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
  // [FIX] 구글 번역의 비공식 음성 엔드포인트(translate_tts)가 최근 더 자주 요청을 차단(403)해
  // "발음 듣기" 버튼이 조용히 실패하는 문제가 있었습니다. 네트워크 호출 없이 브라우저에 내장된
  // 음성 합성 기능만 사용하도록 단순화해 차단/네트워크 오류 걱정 없이 항상 동작하게 했습니다.
  try {
    if (!('speechSynthesis' in window)) {
      alert('이 브라우저는 음성 재생을 지원하지 않습니다.');
      return;
    }
    window.speechSynthesis.cancel();
    var utter = new SpeechSynthesisUtterance(text);
    utter.lang = 'ko-KR';
    utter.rate = 0.85;
    utter.onerror = function(e) { console.error('[TTS 오류]', e); };
    window.speechSynthesis.speak(utter);
  } catch(e) {
    console.error('[TTS 오류]', e);
    alert('발음 재생 중 문제가 발생했습니다. 잠시 후 다시 시도해주세요.');
  }
}
// [FIX] git push 직후 GitHub Pages(CDN) 배포가 아직 반영되기 전에 Blogger/워드프레스가
// 썸네일을 먼저 요청하면 일시적으로 깨져 보일 수 있음. 실패 시 몇 초 간격으로 자동 재시도.
function _retryHeroImage(img) {
  var tries = parseInt(img.getAttribute('data-retry') || '0', 10);
  if (tries >= 6) return;
  img.setAttribute('data-retry', tries + 1);
  setTimeout(function() {
    img.src = img.src.split('?')[0] + '?retry=' + (tries + 1) + '&t=' + Date.now();
  }, 4000 * (tries + 1));
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
<div class="hero"><img id="heroThumb" src="../thumbs/{thumb_filename}" alt="{title_escaped}" loading="eager" fetchpriority="high" onerror="_retryHeroImage(this)">{hero_tts_html}</div>
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
  /* [NEW] 영문 슬로건 — 3초 안에 "누구를 위한 블로그인지" 파악되도록 상단 전면 배치 */
  .eng-slogan {{ font-size: clamp(0.82em, 3vw, 0.95em); color:#e95c84; font-weight:700; letter-spacing:0.01em; margin: 2px 0 10px; line-height:1.5; }}
  /* [NEW] 콘텐츠 3대 축 소개 카드 */
  .pillars {{ display:grid; grid-template-columns: repeat(3, 1fr); gap:10px; margin: 4px 0 18px; }}
  .pillar {{ background:#fafafa; border:1px solid #ececec; border-radius:14px; padding:12px 10px; text-align:center; }}
  .pillar-emoji {{ font-size:1.5em; display:block; margin-bottom:4px; }}
  .pillar-title {{ font-size:0.78em; font-weight:800; color:#333; word-break:keep-all; line-height:1.3; }}
  .pillar-sub {{ font-size:0.68em; color:#999; margin-top:2px; word-break:keep-all; }}
  @media (max-width:420px) {{ .pillars {{ grid-template-columns: 1fr; }} .pillar {{ display:flex; align-items:center; gap:10px; text-align:left; padding:10px 14px; }} .pillar-emoji {{ margin:0; }} }}
  /* [NEW] 클릭 가능한 카테고리 필터 칩 (전체 포함) */
  .pill-row {{ display:flex; flex-wrap:wrap; gap:8px; margin-bottom: 18px; }}
  .pill {{ font-size:0.78em; font-weight:700; color:#fff; padding:6px 15px; border-radius:999px; border:none; cursor:pointer; opacity:0.55; transition:opacity .15s ease, transform .15s ease; font-family:inherit; }}
  .pill.active {{ opacity:1; transform:scale(1.04); box-shadow:0 2px 8px rgba(0,0,0,0.18); }}
  .pill:hover {{ opacity:0.85; }}
  /* [NEW] 무료 PDF 리드마그넷 배너 */
  .lead-magnet {{ display:flex; align-items:center; gap:14px; background:linear-gradient(135deg,#fff7ed,#fff1f2); border:1px solid #fde8e0; border-radius:16px; padding:16px 18px; margin: 22px 0 6px; text-decoration:none; }}
  .lead-magnet-emoji {{ font-size:2em; flex-shrink:0; }}
  .lead-magnet-title {{ font-weight:800; color:#1a1a1a; font-size:0.95em; word-break:keep-all; }}
  .lead-magnet-sub {{ font-size:0.78em; color:#888; margin-top:2px; word-break:keep-all; }}
  .lead-magnet-cta {{ margin-left:auto; flex-shrink:0; background:#e95c84; color:#fff; font-size:0.78em; font-weight:800; padding:8px 14px; border-radius:999px; white-space:nowrap; }}
  /* [NEW] SNS 팔로우 아이콘 행 (설정된 경우에만 렌더링) */
  .social-row {{ display:flex; gap:10px; margin: 14px 0 2px; }}
  .social-row a {{ width:36px; height:36px; border-radius:50%; background:#f2f2f2; display:flex; align-items:center; justify-content:center; text-decoration:none; font-size:1.1em; }}
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
  <p class="eng-slogan">{eng_slogan}</p>
  <p class="intro">{site_tagline}</p>
  <div class="pillars">
    <div class="pillar"><span class="pillar-emoji">💬</span><span class="pillar-title">Real Korean Phrases</span><span class="pillar-sub">실제 한국인이 쓰는 표현</span></div>
    <div class="pillar"><span class="pillar-emoji">🇰🇷</span><span class="pillar-title">Cultural Nuances</span><span class="pillar-sub">표현 속 한국인의 정서</span></div>
    <div class="pillar"><span class="pillar-emoji">😲</span><span class="pillar-title">Everyday Reactions</span><span class="pillar-sub">리액션으로 배우는 뉘앙스</span></div>
  </div>
  <div class="pill-row" id="categoryFilter">{category_pills}</div>
  {lead_magnet_html}
  {social_row_html}
</div>

<div class="content-wrap">
{hero_html}
{mid_html}
{bottom_html}
</div>
<script>
(function() {{
  var pills = document.querySelectorAll('#categoryFilter .pill');
  var cards = document.querySelectorAll('[data-category]');
  pills.forEach(function(pill) {{
    pill.addEventListener('click', function() {{
      pills.forEach(function(p) {{ p.classList.remove('active'); }});
      pill.classList.add('active');
      var cat = pill.getAttribute('data-filter');
      cards.forEach(function(card) {{
        var show = (cat === 'all' || card.getAttribute('data-category') === cat);
        card.style.display = show ? '' : 'none';
      }});
    }});
  }});
}})();
</script>
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


def _fallback_article_local(title: str) -> Dict[str, Any]:
    """Gemini 429/장애 시 최소 발행 가능한 로컬 폴백 글 (파이프라인 전체 중단 방지)."""
    expr = _extract_expression_from_title(title) or _extract_expression_from_title(title, strict=False) or "한국어"
    category = "일상표현"
    for cat, words in {
        "번역감정": ["마음", "감정", "느낌", "섭섭", "답답", "미안"],
        "한국문화": ["눈치", "정", "체면", "우리"],
        "리액션": ["대박", "헐", "진짜", "미쳤"],
    }.items():
        if any(w in (title + expr) for w in words):
            category = cat
            break
    html = f"""
<div class="reader-value"><strong>Today&apos;s expression</strong><br>「{html.escape(expr)}」</div>
<h2>이 말, 어떤 순간에 나올까?</h2>
<p>한국어 「{html.escape(expr)}」는 사전 뜻만으로는 설명이 부족한 경우가 많습니다. 실제 대화에서는 <em>상황과 관계</em>가 의미를 완성합니다.</p>
<h2>직역하면 놓치는 부분</h2>
<p>영어나 다른 언어로 그대로 옮기면 어색하거나 오해가 생길 수 있어요. 「{html.escape(expr)}」를 배울 때는 예문보다 <strong>언제 쓰는지</strong>를 함께 기억하는 편이 낫습니다.</p>
<h2>이렇게 써 보세요</h2>
<p>친구와의 캐주얼한 대화에서 「{html.escape(expr)}」가 자연스럽게 나오는 장면을 떠올려 보세요. 관계가 가까운 사이에서 더 자주 들릴 수 있습니다.</p>
<h2>한 줄 정리</h2>
<p>「{html.escape(expr)}」 — 뜻이 아니라 <strong>순간</strong>으로 기억해 보세요.</p>
<p class="meta-note">* 일시적 AI 한도로 요약본이 발행되었습니다. 다음 실행에서 본문이 보강될 수 있습니다.</p>
"""
    return {
        "title": title if title else f'"{expr}" Meaning in Korean: What Does It Really Mean?',
        "expression": expr,
        "category": category,
        "html_body": html,
        "meta_description": f'What does "{expr}" mean in Korean? Learn the real situation, not just the dictionary.',
        "image_keywords": f"korean language {expr} conversation",
        "focus_keyword": expr,
    }


def generate_article(title: str) -> Dict[str, Any]:
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY 환경변수가 비어있습니다. 저장소 Secrets 설정을 확인하세요.")

    url = GEMINI_URL.format(api_key=GEMINI_API_KEY)
    payload = {
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"role": "user", "parts": [{"text": f"오늘 날짜: {datetime.now().strftime('%Y년 %m월 %d일')}\n\n주제: '{title}'\n\n이 한국어 표현/문화 주제에 대해, H.O.L.D. 흐름(훅→긴장→열린 궁금증→핵심 전달)을 살려 외국인 학습자가 끝까지 읽고 싶어하는 글을 작성해주세요. 소제목(H2) 문구와 순서는 매 글마다 변주하고, 문화 설명은 무출처 절대 단정을 피하세요. 시점을 언급할 때는 반드시 위에 적힌 '오늘 날짜'를 기준으로 하세요."}]}],
        # [FIX] JSON 파싱 실패를 줄이기 위해 순수 JSON 출력을 강제하고 출력 토큰 한도를 명시적으로 늘림
        "generationConfig": {
            "responseMimeType": "application/json",
            "maxOutputTokens": 8192,
        },
    }

    last_error = None
    for attempt in range(1, 7):  # 429 대비 재시도 확대
        try:
            resp = requests.post(url, json=payload, timeout=60)
            if resp.status_code in (429, 503):
                # Gemini free-tier 429: 지수 백오프 (30s → 최대 3분)
                wait = min(30 * attempt, 180)
                logger.warning(
                    f"일시적 오류({resp.status_code}), {wait}초 대기 후 재시도 ({attempt}/6) "
                    f"— API 할당량/동시요청 한도일 수 있습니다"
                )
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
            if not article["expression"]:
                # [FIX] Gemini가 "expression" 필드를 가끔 빈 값으로 반환하는 경우가 있었음.
                # 이 경우 썸네일 텍스트와 발음 듣기 버튼이 통째로 사라지는 문제로 이어졌으므로,
                # 제목에서 안전하게 폴백 추출한다 (홑/쌍따옴표, 로마자+괄호한글 조합까지 처리).
                fallback_expr = _extract_expression_from_title(title)
                if fallback_expr:
                    article["expression"] = fallback_expr
                    logger.warning(f"[FIX] expression이 비어있어 제목에서 폴백 추출: {fallback_expr}")
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

    raise RuntimeError(f"Gemini 글 생성 실패(재시도 소진): {last_error}")

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
    if not expression_clean:
        # [FIX] 2차 방어선: 상위 단계에서 expression이 비어 넘어와도 썸네일이 빈 배경으로
        # 나가지 않도록, 제목에서 한 번 더 폴백 추출을 시도한다.
        expression_clean = _extract_expression_from_title(title or "")
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
        # 영문 한 줄 서브타이틀(빈 썸네일처럼 보이지 않게)
        sub = 'Korean expression · Learn the nuance'
        sub_font = _load_font(28)
        sub_h = 36
        total_h = line_h * len(lines) + sub_h + 20
        ty = h // 2 - total_h // 2

        text_fill = _blend_rgb((255, 255, 255), accent_rgb, 0.22) + (255,)
        text_stroke = _blend_rgb(accent_rgb, (0, 0, 0), 0.55) + (240,)
        for line in lines:
            lb = draw.textbbox((0, 0), line, font=expr_font)
            tw = lb[2] - lb[0]
            tx = (w - tw) / 2 - lb[0]
            draw.text((tx, ty - lb[1]), line, font=expr_font, fill=text_fill,
                       stroke_width=5, stroke_fill=text_stroke)
            ty += line_h
        sb = draw.textbbox((0, 0), sub, font=sub_font)
        draw.text(((w - (sb[2] - sb[0])) / 2 - sb[0], ty + 12 - sb[1]), sub, font=sub_font,
                  fill=(255, 255, 255, 230))

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

    # [FIX] 항상 JPEG로 저장 (Blogger·사이드바 썸네일 호환). 경장이 .webp면 .jpg로 바꿔 저장.
    rgb = img.convert("RGB")
    out = output_path
    if out.lower().endswith(".webp"):
        out = out[:-5] + ".jpg"
    elif not out.lower().endswith((".jpg", ".jpeg")):
        out = os.path.splitext(out)[0] + ".jpg"
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    rgb.save(out, format="JPEG", quality=90, optimize=True)
    # 호출부가 다른 경로를 기대해도 메인 산출물은 out
    if out != output_path and not os.path.isfile(output_path):
        try:
            rgb.save(output_path, format="JPEG", quality=90, optimize=True)
        except Exception:
            pass








def _instatoon_slug(expression: str, title: str) -> str:
    base = (expression or title or "post").strip()
    base = re.sub(r"[^\w가-힣\-]+", "_", base)[:40].strip("_") or "post"
    return base


def _strip_html_for_instatoon(html_body: str, limit: int = 2800) -> str:
    t = re.sub(r"<script[\s\S]*?</script>", " ", html_body or "", flags=re.I)
    t = re.sub(r"<style[\s\S]*?</style>", " ", t, flags=re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    t = re.sub(r"&nbsp;", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t[:limit]


# ─── MASTER PROMPT: 표현+본문 → 분석 → 콘티 → 이미지 프롬프트 ───
INSTATOON_MASTER_SYSTEM = """당신은 한국어와 한국 문화를 전문적으로 다루는 25년 경력의 인스타툰 작가이자 스토리텔러, 캐릭터 연출가, 이미지 생성 프롬프트 디렉터다.

목표는 한국어 표현을 '설명하는 이미지'가 아니라, 그 표현이 실제 생활에서 튀어나오는 가장 공감되는 순간을 하나의 인스타툰 장면으로 만드는 것이다.

[규칙]
- 본문에 없는 사실을 임의로 추가하지 말 것
- '한국인은 모두…' 식 일반화·과장 금지
- 한 컷 = 하나의 순간 (여러 장면 억지 합치기 금지)
- 외국인 캐릭터는 직역 오해·의미 차이가 콘텐츠 핵심일 때만 (항상 넣지 말 것)
- 대사는 구어체, 1~3개, 표현 철자 유지
- 하단 문화 메시지 1~2줄, 본문에 근거할 것
- 표현마다 장소·행동·구도·포즈를 다르게 (동일 템플릿 반복 금지)
- 첫 시선은 설명문이 아니라 사건·표정

[분석 순서]
1) 본문 분석 (표현/사전뜻/실제뜻/오해/상황/감정/문화/공감장면/핵심메시지)
2) 핵심 메시지 1개만 선정
3) 감정 엔진 (감탄·놀람·기쁨·감동·당황·황당·어이·분노·실망·걱정·체념·민망·부끄러움·설렘·귀여움·공감·복합)
4) 장면 엔진 (음식·카페·쇼핑·여행·직장·학교·친구·가족·연애·SNS·메신저·대중교통·집·거리 등 중 하나)
5) 공감 포인트
6) 시각적 훅 (과장 표정·결정적 순간 등)
7) 캐릭터 최소 인원 (기본 1, 필요시 2, 최대 3)
8) 카메라 (closeup|medium|wide)
9) 대사
10) 하단 메시지
11) 최종 이미지 생성 프롬프트 (영문+한글 표현 병기, 4:5 Instagram webtoon)
12) negative prompt

반드시 아래 JSON만 출력 (마크다운 코드펜스 금지):
{
  "core_message": "한 문장",
  "situation": "장소 + 시간 + 사건",
  "place": "카페|식당|직장|집|거리|지하철|메신저|쇼핑|여행|학교|편의점|기타",
  "empathy": "한국인 공감 한 줄",
  "emotion_primary": "감탄|놀람|기쁨|감동|당황|황당함|어이없음|분노|실망|걱정|체념|민망|부끄러움|설렘|귀여움|공감|복합",
  "emotion_secondary": "",
  "characters": [{"role":"주인공|상대","desc":"외형","action":"행동","face":"표정"}],
  "camera": "closeup|medium|wide",
  "visual_hook": "첫 시선이 갈 사건",
  "bubbles": ["구어 대사1"],
  "highlight_expression": "표현 원문",
  "footer": "하단 1~2줄",
  "color_mood": "bright|warm|cool|dry|soft",
  "use_foreigner": false,
  "foreign_bubble": "",
  "final_image_prompt": "4:5 vertical Instagram webtoon, ... 완성 영문 프롬프트 (한글 표현은 따옴표로 유지)",
  "negative_prompt": "photorealistic, 3D render, ..."
}
"""


def _fallback_master_plan(article: Dict[str, Any]) -> Dict[str, Any]:
    expr = (article.get("expression") or "").strip() or _extract_expression_from_title(article.get("title") or "") or "이 표현"
    meta = (article.get("meta_description") or "").strip()
    body = _strip_html_for_instatoon(article.get("html_body") or "", 600)
    seed = int(hashlib.md5(f"{expr}|{meta}|{body[:60]}".encode()).hexdigest(), 16)
    rules = [
        (r"미쳤|대박|레전드|최고", "감탄", "식당", f"와… {expr}.", "bright",
         "close-up of a young Korean person tasting amazing food, eyes wide with delight"),
        (r"눈치|망설|조심", "당황", "직장", f"…{expr} 보이네.", "cool",
         "office meeting, person hesitating with hand half-raised, awkward smile"),
        (r"괜찮", "체념", "카페", f"{expr}.", "soft",
         "cafe table, person saying they are fine while looking tired"),
        (r"정(이|이 )들|그리", "감동", "거리", f"{expr}…", "warm",
         "person watching a departing bus on a familiar street, soft emotion"),
        (r"답답|억울|화", "황당함", "메신저", f"아, {expr}.", "dry",
         "person staring at phone messages, frustrated expression"),
        (r"애매", "당황", "카페", f"음… {expr}.", "cool",
         "person between two menu choices, unsure expression"),
    ]
    emotion, place, bubble, mood, scene_en = "공감", "카페", expr, "soft", "everyday Korean cafe moment"
    blob = f"{expr} {meta} {body}"
    for pat, em, pl, bu, mo, sc in rules:
        if re.search(pat, blob):
            emotion, place, bubble, mood, scene_en = em, pl, bu, mo, sc
            break
    sit = f"{place} · 그 표현이 나온 순간"
    final_prompt = (
        f"4:5 vertical Instagram Korean webtoon illustration, clean line art, simple background, "
        f"{scene_en}, expressive face matching emotion '{emotion}', "
        f"speech bubble with exact Korean text \"{bubble}\", "
        f"highlight expression \"{expr}\", warm approachable editorial style, high readability, "
        f"no photorealism, minimal text"
    )
    return {
        "core_message": meta[:90] if meta else f"「{expr}」가 나오는 실제 순간",
        "situation": sit,
        "place": place,
        "empathy": "아, 진짜 저 상황에선 저 말이 나오지.",
        "emotion_primary": emotion,
        "emotion_secondary": "",
        "characters": [{"role": "주인공", "desc": "20대 한국인", "action": "반응 중", "face": emotion}],
        "camera": "medium",
        "visual_hook": sit,
        "bubbles": [bubble],
        "highlight_expression": expr,
        "footer": f"한국에서는 이런 순간에 「{expr}」라고 말하기도 해요.",
        "color_mood": mood,
        "use_foreigner": False,
        "foreign_bubble": "",
        "final_image_prompt": final_prompt,
        "negative_prompt": (
            "photorealistic, 3D render, cinematic realism, overly detailed background, "
            "crowded composition, too many characters, bad anatomy, excessive text, "
            "random Korean letters, garbled Korean, watermark, logo, stiff pose"
        ),
    }


def plan_instatoon_from_blog(article: Dict[str, Any]) -> Dict[str, Any]:
    """마스터 프롬프트: 표현+본문 → 분석·상황·콘티·최종 이미지 프롬프트."""
    expr = (article.get("expression") or "").strip() or _extract_expression_from_title(article.get("title") or "")
    body = _strip_html_for_instatoon(article.get("html_body") or "", 2400)
    title = article.get("title") or ""
    meta = article.get("meta_description") or ""
    plan = _fallback_master_plan(article)
    user = (
        f"한국어 표현:\n{expr}\n\n"
        f"블로그 제목:\n{title}\n\n"
        f"메타 요약:\n{meta}\n\n"
        f"블로그 본문:\n{body or '(본문 없음 — 제목·표현만으로 설계)'}\n"
    )
    if not GEMINI_API_KEY:
        logger.info("[인스타툰] GEMINI 없음 — 로컬 마스터 폴백 콘티")
        return plan
    try:
        url = GEMINI_URL.format(api_key=GEMINI_API_KEY)
        resp = requests.post(
            url,
            json={
                "system_instruction": {"parts": [{"text": INSTATOON_MASTER_SYSTEM}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": {
                    "temperature": 0.9,
                    "maxOutputTokens": 2048,
                    "responseMimeType": "application/json",
                },
            },
            timeout=50,
        )
        if resp.status_code in (429, 503):
            logger.warning(f"[인스타툰] Gemini {resp.status_code} — 로컬 콘티 (할당량 보호)")
            return plan
        if not resp.ok:
            logger.warning(f"[인스타툰] Gemini HTTP {resp.status_code}")
            return plan
        text_out = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        m = re.search(r"\{[\s\S]*\}", text_out)
        if not m:
            return plan
        parsed = json.loads(m.group(0))
        for k, v in parsed.items():
            if v is not None and v != "":
                plan[k] = v
        plan["highlight_expression"] = expr  # 철자 고정
        if isinstance(plan.get("bubbles"), str):
            plan["bubbles"] = [plan["bubbles"]]
        if not isinstance(plan.get("bubbles"), list) or not plan["bubbles"]:
            plan["bubbles"] = [expr]
        if not plan.get("final_image_prompt"):
            plan["final_image_prompt"] = _fallback_master_plan(article)["final_image_prompt"]
        logger.info(
            f"[인스타툰] 마스터 콘티 OK — {plan.get('place')} / {plan.get('emotion_primary')} / "
            f"{(plan.get('situation') or '')[:40]}"
        )
        return plan
    except Exception as e:
        logger.warning(f"[인스타툰] 마스터 설계 실패, 폴백: {e}")
        return plan


_MOOD_PALETTE = {
    "bright": [(255, 248, 230), (255, 230, 200), (255, 140, 70)],
    "warm": [(255, 245, 240), (255, 210, 200), (220, 110, 100)],
    "cool": [(245, 248, 255), (210, 220, 240), (100, 130, 190)],
    "dry": [(248, 248, 245), (220, 215, 200), (140, 130, 110)],
    "soft": [(250, 248, 252), (230, 220, 235), (150, 130, 180)],
}


def _try_gemini_image_bytes(prompt: str, negative: str = "") -> Optional[bytes]:
    """가능하면 Gemini/Imagen 계열로 이미지 바이트 생성. 실패 시 None."""
    if not GEMINI_API_KEY:
        return None
    full_prompt = prompt.strip()
    if negative:
        full_prompt += f"\n\nAvoid: {negative[:400]}"
    # 후보 모델 (환경변수로 덮어쓰기 가능)
    models = [
        os.environ.get("GEMINI_IMAGE_MODEL", "").strip(),
        "gemini-2.0-flash-preview-image-generation",
        "gemini-2.0-flash-exp-image-generation",
    ]
    models = [m for m in models if m]
    for model in models:
        try:
            endpoint = (
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
                f"?key={GEMINI_API_KEY}"
            )
            payload = {
                "contents": [{"role": "user", "parts": [{"text": full_prompt}]}],
                "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
            }
            r = requests.post(endpoint, json=payload, timeout=90)
            if r.status_code in (429, 503):
                logger.warning(f"[인스타툰] 이미지 API {r.status_code} ({model})")
                continue
            if not r.ok:
                logger.warning(f"[인스타툰] 이미지 API HTTP {r.status_code} ({model}): {r.text[:180]}")
                continue
            parts = (((r.json().get("candidates") or [{}])[0].get("content") or {}).get("parts") or [])
            for p in parts:
                inline = p.get("inlineData") or p.get("inline_data") or {}
                data_b64 = inline.get("data")
                mime = (inline.get("mimeType") or inline.get("mime_type") or "")
                if data_b64 and "image" in mime:
                    import base64 as b64
                    logger.info(f"[인스타툰] 이미지 모델 생성 성공: {model}")
                    return b64.b64decode(data_b64)
        except Exception as e:
            logger.warning(f"[인스타툰] 이미지 모델 실패({model}): {e}")
    return None


def _render_plan_storyboard(plan: Dict[str, Any], blogger_url: str = "") -> Image.Image:
    """이미지 API 없을 때: 마스터 콘티 기반 4:5 스토리보드(웹툰 톤) 렌더."""
    w, h = INSTATOON_SIZE
    mood = (plan.get("color_mood") or "soft").lower()
    pal = _MOOD_PALETTE.get(mood) or _MOOD_PALETTE["soft"]
    seed = int(hashlib.md5(json.dumps(plan, ensure_ascii=False, sort_keys=True).encode()).hexdigest(), 16)
    img = _make_random_gradient_background((w, h), [pal[0], (255, 255, 255), pal[1]], seed=seed % 99991).convert("RGB")
    draw = ImageDraw.Draw(img)
    ink = (30, 30, 34)
    accent = pal[2]
    expr = plan.get("highlight_expression") or ""

    # 상단: 상황(사건) — 설명문이 아닌 훅
    y = 56
    hook = plan.get("visual_hook") or plan.get("situation") or ""
    for line in _wrap_by_pixel_width(draw, hook, _load_font(32), w - 100)[:2]:
        lb = draw.textbbox((0, 0), line, font=_load_font(32))
        draw.text(((w - (lb[2] - lb[0])) / 2, y), line, font=_load_font(32), fill=(90, 90, 95))
        y += (lb[3] - lb[1]) + 8
    y += 20

    # 말풍선
    for i, b in enumerate((plan.get("bubbles") or [expr])[:3]):
        b = str(b).strip()
        if not b:
            continue
        font = _load_font(44 if expr and expr in b else 34)
        lines = _wrap_by_pixel_width(draw, b, font, 780)[:3]
        pad = 18
        widths = [draw.textbbox((0, 0), ln, font=font)[2] - draw.textbbox((0, 0), ln, font=font)[0] for ln in lines]
        heights = [draw.textbbox((0, 0), ln, font=font)[3] - draw.textbbox((0, 0), ln, font=font)[1] for ln in lines]
        bw = max(widths) + pad * 2
        bh = sum(heights) + 8 * (len(lines) - 1) + pad * 2
        x = 90 if i == 0 else 130
        outline = accent if (expr and expr in b) else ink
        draw.rounded_rectangle([x, y, x + bw, y + bh], radius=22, fill=(255, 255, 255), outline=outline, width=4)
        draw.polygon([(x + 36, y + bh - 1), (x + 22, y + bh + 20), (x + 62, y + bh - 1)], fill=(255, 255, 255), outline=outline)
        cy = y + pad
        for j, ln in enumerate(lines):
            draw.text((x + pad, cy), ln, font=font, fill=ink)
            cy += heights[j] + 8
        y += bh + 28

    if plan.get("use_foreigner") and plan.get("foreign_bubble"):
        fb = str(plan["foreign_bubble"])
        ff = _load_font(30)
        draw.rounded_rectangle([w - 380, y - 20, w - 40, y + 60], radius=18, fill=(255, 255, 255), outline=ink, width=3)
        draw.text((w - 360, y), fb, font=ff, fill=ink)

    # 중앙 감정 라벨 + 장소 (캐릭터 과장 드로잉 대신 콘티 시각화)
    mid_y = int(h * 0.52)
    draw.rounded_rectangle([80, mid_y - 40, w - 80, mid_y + 160], radius=28, fill=(255, 255, 255), outline=ink, width=3)
    em = f"{plan.get('emotion_primary') or ''} {plan.get('emotion_secondary') or ''}".strip()
    draw.text((110, mid_y - 20), f"감정 · {em}", font=_load_font(28), fill=accent)
    draw.text((110, mid_y + 20), f"장소 · {plan.get('place') or ''}", font=_load_font(28), fill=ink)
    cam = plan.get("camera") or "medium"
    draw.text((110, mid_y + 60), f"카메라 · {cam}", font=_load_font(26), fill=(80, 80, 80))
    chars = plan.get("characters") or []
    if chars:
        ch0 = chars[0]
        draw.text(
            (110, mid_y + 100),
            f"{ch0.get('role','')}: {ch0.get('face','')} / {ch0.get('action','')}"[:42],
            font=_load_font(26),
            fill=(60, 60, 60),
        )

    # 하단 문화 메시지 + 블로그 CTA
    foot = (plan.get("footer") or "").strip()
    fy = h - 160
    for line in _wrap_by_pixel_width(draw, foot, _load_font(26), w - 100)[:2]:
        lb = draw.textbbox((0, 0), line, font=_load_font(26))
        draw.text(((w - (lb[2] - lb[0])) / 2, fy), line, font=_load_font(26), fill=(70, 70, 75))
        fy += (lb[3] - lb[1]) + 6
    if blogger_url:
        draw.rectangle([0, h - 72, w, h], fill=accent)
        cta = "탭하면 구글 블로그에서 이어서 읽기"
        b = draw.textbbox((0, 0), cta, font=_load_font(28))
        draw.text(((w - (b[2] - b[0])) / 2, h - 58), cta, font=_load_font(28), fill=(255, 255, 255))
        u = blogger_url.replace("https://", "").replace("http://", "")
        b2 = draw.textbbox((0, 0), u, font=_load_font(20))
        draw.text(((w - (b2[2] - b2[0])) / 2, h - 28), u, font=_load_font(20), fill=(255, 255, 255))

    tag = f"「{expr}」"
    tb = draw.textbbox((0, 0), tag, font=_load_font(22))
    draw.rounded_rectangle(
        [w - 56 - (tb[2] - tb[0]), 28, w - 24, 28 + (tb[3] - tb[1]) + 12],
        radius=10, fill=(255, 255, 255), outline=accent, width=2,
    )
    draw.text((w - 48 - (tb[2] - tb[0]), 32), tag, font=_load_font(22), fill=accent)
    return img


def generate_instatoon_images(article: Dict[str, Any], blogger_url: str = "") -> Dict[str, Any]:
    """마스터 프롬프트 콘티 → (가능하면 AI 이미지) → 4:5 한 컷 + plan.json + 클릭 HTML."""
    expr = (article.get("expression") or "").strip() or _extract_expression_from_title(article.get("title") or "")
    slug = _instatoon_slug(expr, article.get("title") or "")
    public_dir = os.path.join(INSTATOON_PUBLIC_DIR, slug)
    download_dir = os.path.join(INSTATOON_DOWNLOAD_DIR, slug)
    os.makedirs(public_dir, exist_ok=True)
    os.makedirs(download_dir, exist_ok=True)

    plan = plan_instatoon_from_blog(article)
    plan_path = os.path.join(download_dir, "plan.json")
    try:
        with open(plan_path, "w", encoding="utf-8") as f:
            json.dump(plan, f, ensure_ascii=False, indent=2)
        with open(os.path.join(public_dir, "plan.json"), "w", encoding="utf-8") as f:
            json.dump(plan, f, ensure_ascii=False, indent=2)
        # 최종 이미지 프롬프트 단독 파일 (외부 툴 복사용)
        with open(os.path.join(download_dir, "image_prompt.txt"), "w", encoding="utf-8") as f:
            f.write(plan.get("final_image_prompt") or "")
            f.write("\n\n--- NEGATIVE ---\n")
            f.write(plan.get("negative_prompt") or "")
    except Exception as e:
        logger.warning(f"[인스타툰] plan 저장 실패: {e}")

    fname = "01.png"
    pub_path = os.path.join(public_dir, fname)
    dl_path = os.path.join(download_dir, fname)

    raw = _try_gemini_image_bytes(plan.get("final_image_prompt") or "", plan.get("negative_prompt") or "")
    if raw:
        try:
            from io import BytesIO
            ai_img = Image.open(BytesIO(raw)).convert("RGB")
            ai_img = ai_img.resize(INSTATOON_SIZE, Image.Resampling.LANCZOS)
            ai_img.save(pub_path, format="PNG", optimize=True)
            ai_img.save(dl_path, format="PNG", optimize=True)
            logger.info("[인스타툰] AI 이미지 저장 완료")
        except Exception as e:
            logger.warning(f"[인스타툰] AI 이미지 저장 실패, 스토리보드 폴백: {e}")
            raw = None
    if not raw:
        board = _render_plan_storyboard(plan, blogger_url)
        board.save(pub_path, format="PNG", optimize=True)
        board.save(dl_path, format="PNG", optimize=True)
        logger.info("[인스타툰] 마스터 콘티 스토리보드 저장")

    target = (blogger_url or "").strip() or (SITE_URL or "https://learnkoreanseekoreans.blogspot.com").rstrip("/")
    safe_target = html.escape(target, quote=True)
    click_html = (
        "<!DOCTYPE html><html lang=\"ko\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        f"<title>{html.escape(expr or 'Learn Korean')}</title>"
        f"<meta http-equiv=\"refresh\" content=\"0;url={safe_target}\">"
        f"<script>location.replace({json.dumps(target)});</script></head><body>"
        f"<a href=\"{safe_target}\"><img src=\"{html.escape(fname)}\" style=\"width:100%\" alt=\"instatoon\"></a>"
        "</body></html>"
    )
    for folder in (download_dir, public_dir):
        try:
            with open(os.path.join(folder, "index.html"), "w", encoding="utf-8") as hf:
                hf.write(click_html)
        except Exception:
            pass

    public_urls = [f"{SITE_URL.rstrip('/')}/instatoon/{slug}/{fname}"] if SITE_URL else []
    logger.info(f"[인스타툰] {plan.get('situation')} → {dl_path}")
    return {
        "slug": slug,
        "local_paths": [dl_path],
        "public_urls": public_urls,
        "click_url": f"{SITE_URL.rstrip('/')}/instatoon/{slug}/" if SITE_URL else "",
        "blogger_url": target,
        "download_dir": download_dir,
        "public_dir": public_dir,
        "plan": plan,
    }


def generate_card_news_images(article: Dict[str, Any], blogger_url: str = "") -> Dict[str, Any]:
    return generate_instatoon_images(article, blogger_url)


def _card_news_slug(expression: str, title: str) -> str:
    return _instatoon_slug(expression, title)



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
    """같은 Topic Cluster·카테고리에 높은 점수 — SEO 토픽 클러스터 내부링크용."""
    score = 0.0
    if candidate.get("category") == article.get("category", "번역감정"):
        score += 2.0
    ac = _cluster_for_article(article)
    cc = _cluster_for_article(candidate)
    if ac and cc and ac == cc:
        score += 5.0
    current_words = set(re.findall(r"[\w가-힣]+", (article.get("title", "") + " " + article.get("keyword", "") + " " + article.get("expression", ""))))
    candidate_words = set(re.findall(r"[\w가-힣]+", (candidate.get("title", "") + " " + candidate.get("expression", ""))))
    score += len(current_words & candidate_words) * 1.2
    return score

def add_internal_link(article: Dict[str, Any]) -> Dict[str, Any]:
    """관련 글 2~3개를 Topic Cluster 우선으로 연결 (무작위 1개 추천 대신)."""
    if not os.path.exists(POSTS_JSON):
        return article
    with open(POSTS_JSON, "r", encoding="utf-8") as f:
        posts = json.load(f)
    posts = [p for p in posts if p.get("blogger_url")]
    if not posts:
        return article
    scored = [(p, _relevance_score(article, p)) for p in posts]
    scored.sort(key=lambda x: x[1], reverse=True)
    my_title = (article.get("title") or "").strip()
    picks = []
    for p, s in scored:
        if (p.get("title") or "").strip() == my_title:
            continue
        if s <= 0 and picks:
            continue
        picks.append(p)
        if len(picks) >= 3:
            break
    if not picks:
        return article
    cluster = _cluster_for_article(article) or "related"
    cluster_label = {
        "greetings": "More Korean greetings & daily phrases",
        "relationship": "More Korean relationship expressions",
        "emotions": "More Korean emotions & reactions",
        "culture": "More Korean culture & language notes",
        "related": "Related reading",
    }.get(cluster, "Related reading")
    items = "".join(
        f'<li style="margin:0.35em 0;"><a href="{html.escape(p["blogger_url"], quote=True)}">{html.escape(p.get("title") or "")}</a></li>'
        for p in picks
    )
    article["html_body"] += (
        f'<div style="margin-top:2em;padding:14px 16px;border-top:1px dashed #ddd;'
        f'border-radius:0 0 10px 10px;background:#fafafa;">'
        f'<p style="margin:0 0 8px;font-weight:700;color:#333;">📚 {cluster_label}</p>'
        f'<ul style="margin:0;padding-left:1.2em;">{items}</ul></div>'
    )
    return article

def _manual_ad_unit() -> str:
    """수동 광고 유닛. 심사 모드이거나 클라이언트/슬롯 미설정 시 빈 문자열."""
    if ADSENSE_REVIEW_MODE:
        return ""
    if not (ADSENSE_CLIENT_ID and ADSENSE_SLOT_ID):
        return ""
    return (
        '<div style="margin:32px 0;text-align:center;clear:both;" class="ad-unit" data-nosnippet>'
        '<div style="font-size:0.7em;color:#999;margin-bottom:6px;letter-spacing:0.04em;">ADVERTISEMENT</div>'
        f'<ins class="adsbygoogle" style="display:block" data-ad-client="{ADSENSE_CLIENT_ID}" '
        f'data-ad-slot="{ADSENSE_SLOT_ID}" data-ad-format="auto" data-full-width-responsive="true"></ins>'
        '<script>(adsbygoogle = window.adsbygoogle || []).push({});</script></div>'
    )

def insert_manual_ads(article: Dict[str, Any]) -> Dict[str, Any]:
    """본문 중·후반에만 광고 1개 삽입. 첫 화면(첫 H2 앞)에는 넣지 않아 UX·심사에 유리."""
    ad_html = _manual_ad_unit()
    if not ad_html:
        return article
    body = article.get("html_body", "")
    # 두 번째 <h2> 앞에 삽입 (콘텐츠가 충분히 보인 뒤)
    matches = list(re.finditer(r"<h2\b", body, flags=re.IGNORECASE))
    if len(matches) >= 2:
        idx = matches[1].start()
        article["html_body"] = body[:idx] + ad_html + body[idx:]
    elif len(matches) == 1:
        # H2가 하나뿐이면 본문 끝(참여 질문 직전)보다는 그 H2 뒤에 가깝게 — 여기선 끝에 가깝게
        article["html_body"] = body + ad_html
    else:
        article["html_body"] = body + ad_html
    return article


def _strip_html_text(html_body: str) -> str:
    text_only = re.sub(r"<script\b[^>]*>.*?</script>", " ", html_body or "", flags=re.DOTALL | re.IGNORECASE)
    text_only = re.sub(r"<style\b[^>]*>.*?</style>", " ", text_only, flags=re.DOTALL | re.IGNORECASE)
    text_only = re.sub(r"<[^>]+>", " ", text_only)
    text_only = re.sub(r"\s+", " ", text_only)
    return text_only.strip()


def validate_article_quality(article: Dict[str, Any]) -> Tuple[bool, str]:
    """AdSense에 불리한 초단문·표현 누락·고정 템플릿 잔존을 검사한다."""
    body = article.get("html_body", "") or ""
    text_only = _strip_html_text(body)
    if len(text_only) < ADSENSE_MIN_BODY_CHARS:
        return False, f"본문 텍스트 {len(text_only)}자 < 최소 {ADSENSE_MIN_BODY_CHARS}자"
    if not (article.get("expression") or "").strip():
        return False, "expression 필드 비어 있음"
    # 고정 5단 소제목이 한 글에 3개 이상이면 패턴 잔존으로 간주
    fixed_hits = sum(1 for k in ("오늘의 표현", "왜 영어로 직역이 안 될까?", "한국인은 어떤 상황에서 쓸까?", "문화 이야기", "여러분의 언어에서는 어떤가요?") if k in body)
    if fixed_hits >= 3:
        return False, f"고정 5단 H2 잔존 {fixed_hits}개"
    return True, "ok"


def add_editorial_footer(article: Dict[str, Any]) -> Dict[str, Any]:
    """학습 목적·편집 고지. YMYL 금융 고지가 아니라 언어 학습 블로그용 짧은 신뢰 푸터."""
    expr = html.escape((article.get("expression") or "").strip())
    footer = (
        '<div style="margin-top:2.2em;padding:14px 16px;border-radius:10px;'
        'background:#f7f7f8;border:1px solid #e8e8ea;font-size:0.88em;color:#555;line-height:1.55;">'
        '<b style="color:#333;">About this note</b><br>'
        'This article explains a Korean expression for language learners. '
        'Nuance can vary by region, age, and relationship — treat examples as common patterns, not rigid rules.'
    )
    if expr:
        footer += f' Focus expression: <span class="notranslate">{expr}</span>.'
    footer += (
        ' Content is editorially reviewed against a fixed teaching outline; '
        'AI drafting tools may assist production.</div>'
    )
    article["html_body"] = (article.get("html_body") or "") + footer
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
    """[이전됨] "오늘의 표현" 아래가 아니라 썸네일 이미지 위 우하단에 원형 오버레이로 얹는
    발음 듣기 버튼. 브라우저 내장 음성(Web Speech API)으로 재생되어 네트워크 의존이 없다."""
    expression = (expression or "").strip()
    if not expression or len(expression) > 20:
        return ""
    escaped = expression.replace("\\", "\\\\").replace("'", "\\'")
    accent = theme["accent"]
    return (
        f'<button type="button" onclick="event.preventDefault();playKoreanTTS(\'{escaped}\')" '
        f'aria-label="발음 듣기" class="notranslate" translate="no" '
        f'style="position:absolute;right:14px;bottom:14px;width:48px;height:48px;border-radius:50%;'
        f'background:{accent};border:2.5px solid #fff;color:#fff;font-size:1.3em;cursor:pointer;'
        f'box-shadow:0 3px 10px rgba(0,0,0,0.35);display:flex;align-items:center;justify-content:center;'
        f'z-index:2;">🔊</button>'
    )

def insert_content_image(article: Dict[str, Any], slug: str) -> Dict[str, Any]:
    # [FIX] 발음 듣기 버튼을 "오늘의 표현" 아래 → 썸네일 위 오버레이로 이전했습니다.
    # (본문 중간 삽화도 히어로 썸네일과 중복이라 이미 제거된 상태)
    return article

# =====================================================================
# [전면 개편 + H.O.L.D.] 웹툰 패널 — H2 개수/문구가 매 글 변주되어도 동작
# 각 <h2> 섹션을 만화 컷(패널)처럼 감싼다. 인라인 스타일만 사용해 GitHub Pages·Blogger 어디서나 동일하게 보인다.
# 마지막 패널은 참여 클로징으로 보고 accent 배경으로 강조한다.
# =====================================================================
def _wrap_webtoon_panels(html_body: str, theme: Dict[str, Any]) -> str:
    accent_rgb = _hex_to_rgb(theme["accent"])
    sections = re.split(r"(?=<h2>)", html_body)
    sections = [s for s in sections if s.strip()]
    total = len(sections)
    if total == 0:
        return html_body

    panels = []
    for i, section in enumerate(sections, start=1):
        is_last = (i == total)
        # 마지막 패널은 참여 유도 클로징 컷 → accent 배경으로 톤을 바꾼다
        if is_last:
            bg = theme["accent"]
            text_color = "#ffffff"
            border = "none"
        else:
            tint = 0.06 + (i - 1) * 0.02  # 뒤로 갈수록 배경이 아주 조금씩 더 진해짐 (단조로움 방지)
            bg_rgb = _blend_rgb((255, 255, 255), accent_rgb, min(tint, 0.14))
            bg = f"rgb({bg_rgb[0]},{bg_rgb[1]},{bg_rgb[2]})"
            text_color = "#1a1a1a"
            border = f"1px solid rgba({accent_rgb[0]},{accent_rgb[1]},{accent_rgb[2]},0.28)"

        # h2는 패널 자체가 이미 배경/테두리를 갖고 있으므로, 기존 h2의 배경 그라데이션·좌측 보더를
        # 인라인 스타일로 덮어써 이중으로 겹쳐 보이지 않게 한다. (Blogger 등은 외부 CSS가
        # 적용되지 않으므로 인라인 스타일이어야 어느 플랫폼에서나 동일하게 보임)
        section = re.sub(
            r"^<h2>(.*?)</h2>",
            lambda m: (
                f'<h2 style="margin:6px 0 16px;padding:0;background:none;border:none;'
                f'font-size:1.2em;font-weight:800;color:{text_color};">{m.group(1)}</h2>'
            ),
            section, count=1, flags=re.DOTALL,
        )

        # 사용 예시 목록이 있는 섹션이면 말풍선 카드로 스타일링 (소제목 문구와 무관하게 <ul><li> 존재 여부로 판단)
        if re.search(r"<ul[\s>]", section) and re.search(r"<li[\s>]", section):
            section = re.sub(
                r"<li>(.*?)</li>",
                lambda m: (
                    '<li style="list-style:none;background:#fff;border-radius:14px;border:1px solid rgba(0,0,0,0.08);'
                    'padding:14px 16px;margin:0 0 10px;box-shadow:0 2px 6px rgba(0,0,0,0.06);position:relative;">'
                    f'{m.group(1)}</li>'
                ),
                section, flags=re.DOTALL,
            )
            section = section.replace("<ul>", '<ul style="padding-left:0;margin:14px 0 0;">')

        panels.append(
            f'<section style="position:relative;background:{bg};color:{text_color};border:{border};'
            f'border-radius:18px;padding:26px 24px 28px;margin:0 0 26px;box-shadow:0 3px 14px rgba(0,0,0,0.08);">'
            f'<span style="position:absolute;top:-13px;left:22px;background:{theme["accent"]};color:#fff;'
            f'font-weight:800;font-size:0.72em;letter-spacing:0.03em;padding:4px 13px;border-radius:999px;'
            f'box-shadow:0 2px 6px rgba(0,0,0,0.3);">CUT {i}/{total}</span>'
            f'{section}</section>'
        )

    # 패널(컷) 사이에 웹툰 특유의 스크롤 연결선 (짧은 세로선)을 살짝 넣어 컷과 컷이 이어지는 느낌을 준다
    connector = f'<div style="width:2px;height:16px;background:rgba({accent_rgb[0]},{accent_rgb[1]},{accent_rgb[2]},0.35);margin:-14px auto 0;"></div>'
    return connector.join(panels)


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
    if ADSENSE_REVIEW_MODE:
        return article  # 심사 기간에는 제휴 블록을 본문에 넣지 않음
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
        f'<a class="related-card" href="../{p["file"]}"><img src="../{p["thumb"]}" alt="{html.escape(p["title"], quote=True)}" loading="lazy">'
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
    thumb_filename = f"{slug}-{today}.jpg"
    post_filename = f"{slug}-{today}.html"
    thumb_path = os.path.join(DOCS_DIR, "thumbs", thumb_filename)
    photo_credit = generate_thumbnail(article["title"], thumb_path, theme, category, article.get("image_keywords", ""), article.get("expression", ""))
    if not os.path.isfile(thumb_path):
        # WEBP-only 잔존 시 JPG 재생성 보장
        alt = thumb_path.replace(".jpg", ".webp")
        if os.path.isfile(alt):
            try:
                Image.open(alt).convert("RGB").save(thumb_path, format="JPEG", quality=88)
            except Exception as e:
                logger.warning(f"[썸네일] JPG 변환 실패: {e}")
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
    article["html_body"] = _wrap_webtoon_panels(article["html_body"], theme)  # [NEW] 5단 웹툰 패널 스타일 적용
    article["html_body"] += build_faq_section_html(article, theme["accent"])
    article["html_body"] += build_product_list_html(article, slug, theme["accent"])
    
    post_url = f"{SITE_URL}/posts/{post_filename}" if SITE_URL else f"posts/{post_filename}"
    thumb_url = f"{SITE_URL}/thumbs/{thumb_filename}" if SITE_URL else f"../thumbs/{thumb_filename}"
    title = article["title"]
    # [FIX] 제목에 쌍따옴표가 포함되면(예: Why "정" Has No...) alt="{title}" 속성이 그 따옴표에서
    # 조기 종료되어 HTML이 깨지는 버그가 있었다 (실제 발행된 글에서 alt 텍스트 잘림 확인됨).
    # 아래에서 html.escape()로 미리 이스케이프해둔다 — 이 함수 뒤쪽에서 'html' 이름을
    # POST_TEMPLATE 렌더링 결과(지역변수)로 재사용하므로, 표준 라이브러리 html 모듈 호출은 반드시 여기서 끝낸다.
    title_escaped = html.escape(title, quote=True)
    json_ld = build_json_ld(article, post_url, thumb_url, today)

    if PUBLISH_GITHUB_PAGES_SITE:
        page_html = POST_TEMPLATE.format(
            hero_tts_html=_tts_buttons_html(article.get("expression", ""), theme),
            title=title,
            title_escaped=title_escaped,
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
            f.write(page_html)

    post_meta = {
        "title": title, "file": f"posts/{post_filename}", "thumb": f"thumbs/{thumb_filename}",
        "date": today, "category": category, "accent": theme["accent"], "badge": theme["badge"],
        "blogger_url": "",  # [NEW] Blogger 발행 성공 후 run()에서 채워 넣는다 (관련글 링크에 사용)
    }
    local_thumb = os.path.join(DOCS_DIR, "thumbs", thumb_filename)
    if not os.path.isfile(local_thumb):
        # generate_thumbnail이 확장자를 바꿨을 수 있음
        for ext in (".jpg", ".jpeg", ".png", ".webp"):
            alt = os.path.join(DOCS_DIR, "thumbs", f"{slug}-{today}{ext}")
            if os.path.isfile(alt):
                local_thumb = alt
                thumb_filename = os.path.basename(alt)
                thumb_url = f"{SITE_URL}/thumbs/{thumb_filename}" if SITE_URL else f"../thumbs/{thumb_filename}"
                post_meta["thumb"] = f"thumbs/{thumb_filename}"
                break
    return post_meta, json_ld, thumb_url, local_thumb, post_url

def render_index_html(posts: List[Dict[str, Any]]) -> None:
    """[NEW] posts 리스트를 받아 index.html을 다시 그린다. 새 글 추가(update_index)와
    이전 글 삭제 후 재생성(repair_old_posts) 양쪽에서 공통으로 쓰는 렌더링 로직."""
    os.makedirs(DOCS_DIR, exist_ok=True)
    hero_posts, mid_posts, bottom_posts = posts[:1], posts[1:3], posts[3:]

    hero_html = ""
    if hero_posts:
        p = hero_posts[0]
        hero_html = (
            '<div class="tier-label">🔥 최신 이야기</div>'
            f'<a class="hero" data-category="{p.get("category", "")}" href="{p["file"]}"><img src="{p["thumb"]}" alt="{html.escape(p["title"], quote=True)}" loading="eager" fetchpriority="high">'
            f'<div class="hero-body"><span class="hero-badge" style="background:{p.get("accent", "#e95c84")}">{p.get("badge", "💗 번역이 안 되는 감정")}</span>'
            f'<div class="hero-title">{p["title"]}</div><div class="date">{p["date"]}</div></div></a>'
        )
    mid_html = ""
    if mid_posts:
        cards = "\n".join(
            f'<a class="mid-card" data-category="{p.get("category", "")}" href="{p["file"]}"><img src="{p["thumb"]}" alt="{html.escape(p["title"], quote=True)}" loading="lazy">'
            f'<div class="mid-body"><span class="badge-sm" style="background:{p.get("accent", "#e95c84")}">{p.get("badge", "💗 번역이 안 되는 감정")}</span>'
            f'<div class="mid-title">{p["title"]}</div><div class="date">{p["date"]}</div></div></a>' for p in mid_posts
        )
        mid_html = f'<div class="tier-label">📖 다음 이야기</div><div class="mid-grid">{cards}</div>'
    bottom_html = ""
    if bottom_posts:
        cards = "\n".join(
            f'<a class="bottom-card" data-category="{p.get("category", "")}" href="{p["file"]}"><img src="{p["thumb"]}" alt="{html.escape(p["title"], quote=True)}" loading="lazy">'
            f'<div class="bottom-body"><span class="badge-sm" style="background:{p.get("accent", "#e95c84")}">{p.get("badge", "💗 번역이 안 되는 감정")}</span>'
            f'<div class="bottom-title">{p["title"]}</div></div></a>' for p in bottom_posts
        )
        bottom_html = f'<div class="tier-label">🗂️ 지난 글 모아보기</div><div class="bottom-grid">{cards}</div>'

    with open(os.path.join(DOCS_DIR, "index.html"), "w", encoding="utf-8") as f:
        # [NEW] 클릭 가능한 카테고리 필터 칩. 영문 라벨을 함께 보여줘 외국인 방문자가
        # "어떤 카테고리인지" 3초 안에 파악할 수 있게 한다. "전체(All)"를 기본 활성 상태로 둔다.
        pill_items = [f'<button type="button" class="pill active" data-filter="all" style="background:#333;">🌐 All</button>']
        for filter_key, t in CATEGORY_THEMES.items():
            pill_items.append(f'<button type="button" class="pill" data-filter="{filter_key}" style="background:{t["accent"]}">{t["badge"]} · {t["label"]}</button>')
        category_pills = "".join(pill_items)

        f.write(INDEX_TEMPLATE.format(
            site_title=SITE_TITLE, site_tagline=SITE_TAGLINE, site_url=SITE_URL or ".", ga_snippet=_ga_snippet(),
            adsense_snippet=_adsense_snippet(), fonts_url=_google_fonts_url(),
            hero_html=hero_html, mid_html=mid_html, bottom_html=bottom_html, blog_json_ld=build_blog_index_json_ld(posts),
            category_pills=category_pills, search_console_meta=_search_console_meta(),
            eng_slogan=ENGLISH_SLOGAN, lead_magnet_html=_lead_magnet_html(), social_row_html=_social_row_html(),
            footer_html='<div class="site-footer"><a href="about.html">블로그 소개</a>·<a href="privacy.html">개인정보처리방침</a>·<a href="contact.html">문의하기</a>'
                        f'<div style="margin-top:8px;">© {datetime.now().year} {SITE_TITLE}</div></div>',
            translate_widget=_translate_widget(),
            site_title_short=SITE_TITLE[:12],
        ))

def update_index(new_post: Dict[str, Any]) -> List[Dict[str, Any]]:
    os.makedirs(DOCS_DIR, exist_ok=True)
    posts = []
    if os.path.exists(POSTS_JSON):
        with open(POSTS_JSON, "r", encoding="utf-8") as f: posts = json.load(f)
    posts.insert(0, new_post)
    with open(POSTS_JSON, "w", encoding="utf-8") as f: json.dump(posts, f, ensure_ascii=False, indent=2)
    if PUBLISH_GITHUB_PAGES_SITE:
        render_index_html(posts)
    return posts

def update_post_blogger_url(post_file: str, blogger_url: str) -> None:
    """[NEW] Blogger 발행이 성공한 뒤, 그 글의 posts.json 항목에 실제 Blogger 주소를 채워 넣는다.
    이후 다른 글의 '관련 글' 링크가 (더 이상 존재하지 않는) GitHub Pages 주소 대신
    이 Blogger 주소를 가리키도록 하기 위함."""
    if not blogger_url or not os.path.exists(POSTS_JSON):
        return
    with open(POSTS_JSON, "r", encoding="utf-8") as f:
        posts = json.load(f)
    for p in posts:
        if p.get("file") == post_file:
            p["blogger_url"] = blogger_url
            break
    with open(POSTS_JSON, "w", encoding="utf-8") as f:
        json.dump(posts, f, ensure_ascii=False, indent=2)


# GitHub Pages용 정적 About/Privacy/Contact (Blogger 정책 페이지와 별개, 선택 산출물)
STATIC_PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{page_title} | {site_title}</title>
<meta name="description" content="{page_title} — {site_title}">
<link rel="icon" type="image/png" href="favicon.png">{search_console_meta}
<meta name="robots" content="index,follow">
{ga_snippet}{adsense_snippet}
<style>
  * {{ box-sizing: border-box; }}
  body {{ max-width: 720px; margin: 0 auto; padding: 24px 16px 60px;
    font-family: -apple-system, BlinkMacSystemFont, 'Noto Sans KR', 'Segoe UI', sans-serif;
    line-height: 1.75; color: #1a1a1a; background: #fafafa; }}
  h1 {{ font-size: 1.6em; margin: 0 0 16px; }}
  h2 {{ font-size: 1.2em; margin-top: 1.6em; border-left: 4px solid #2563eb; padding-left: 10px; }}
  a {{ color: #2563eb; }}
  .back {{ display: inline-block; margin-bottom: 20px; font-weight: 700; text-decoration: none; }}
  footer {{ margin-top: 3em; padding-top: 1em; border-top: 1px solid #e5e7eb; font-size: 0.9em; color: #6b7280; }}
</style>
</head>
<body>
<a class="back" href="index.html">← Home</a>
<h1>{page_title}</h1>
{page_body}
<footer>
  <p>{site_title}</p>
  <p>
    <a href="about.html">About</a> ·
    <a href="privacy.html">Privacy</a> ·
    <a href="contact.html">Contact</a>
  </p>
</footer>
</body>
</html>
"""

def generate_static_pages() -> None:
    os.makedirs(DOCS_DIR, exist_ok=True)
    common_kwargs = dict(site_title=SITE_TITLE, search_console_meta=_search_console_meta(), ga_snippet=_ga_snippet(), adsense_snippet=_adsense_snippet())
    contact_block = (
        f"<p><b>Email:</b> {html.escape(CONTACT_EMAIL)}</p>"
        if CONTACT_EMAIL else
        "<p><b>Email:</b> Set the CONTACT_EMAIL secret, then re-run once to refresh this page.</p>"
    )
    about_body = f"""
<p><b>{html.escape(SITE_TITLE)}</b> — {ENGLISH_SLOGAN}</p>
<p>{html.escape(SITE_TAGLINE)}</p>
<h2>Who this blog is for</h2>
<p>Foreign learners of Korean who want more than dictionary definitions: when Koreans actually use an expression, what nuance translation loses, and how it connects to everyday culture.</p>
<h2>How posts are made</h2>
<p>Each article follows an editorial outline (hook, untranslatable nuance, real usage, cultural context, reader prompt). Drafting may be assisted by AI tools; examples and structure are checked against a teaching checklist so posts stay useful for learners—not keyword filler.</p>
<h2>Categories</h2>
<ul>
<li>Untranslatable feelings (e.g. 정, 눈치)</li>
<li>Everyday phrases Koreans use often</li>
<li>Cultural background behind the language</li>
<li>Typical Korean reactions / interjections</li>
</ul>
<p>Information is for learning purposes. Social nuance varies by age, region, and relationship.</p>
"""
    privacy_body = """
<p>This blog may use Google Analytics (GA4) and Google AdSense for statistics and advertising. Cookies may be used; they are not intended to collect information that directly identifies you as an individual.</p>
<h2>Cookies &amp; ads</h2>
<p>Third-party vendors, including Google, use cookies to serve ads based on prior visits. You can opt out of personalized advertising at <a href="https://adssettings.google.com" target="_blank" rel="noopener">Google Ads Settings</a>.</p>
<h2>Contact</h2>
<p>For privacy questions, use the Contact page.</p>
"""
    contact_body = f"""
<p>Questions about an article, corrections, or collaboration ideas are welcome.</p>
{contact_block}
<p>We read messages about factual mistakes in explanations of Korean expressions and update posts when needed.</p>
"""
    pages = {
        "about.html": ("About", about_body),
        "privacy.html": ("Privacy Policy", privacy_body),
        "contact.html": ("Contact", contact_body),
    }
    for filename, (page_title, page_body) in pages.items():
        path = os.path.join(DOCS_DIR, filename)
        # 심사 대비: 소개/개인정보/문의 페이지는 내용이 바뀌면 덮어써 최신 고지를 유지
        with open(path, "w", encoding="utf-8") as f:
            f.write(STATIC_PAGE_TEMPLATE.format(page_title=page_title, page_body=page_body, **common_kwargs))

# =====================================================================
# [NEW] 무료 리드마그넷 PDF — "지금까지 발행된 표현 모음"을 매 실행마다 자동 갱신
# 이메일 구독 시스템(뉴스레터)은 외부 서비스 연동이 필요해 이 파이프라인 범위 밖이지만,
# 다운로드 가능한 PDF 자체는 완전히 자동으로 만들 수 있어 여기서 구현한다.
# =====================================================================
def _find_korean_ttf() -> Optional[str]:
    for path in FONT_CANDIDATES:
        if path == "font.ttf" or not os.path.exists(path):
            continue
        try:
            # [FIX] .ttc(트루타입 컬렉션) 중 일부는 reportlab이 임베딩을 지원하지 않아
            # 등록 시점에 예외가 남. 후보 폰트를 하나씩 실제로 등록해보고 성공하는 것만 채택.
            pdfmetrics.registerFont(TTFont("KRFont_probe", path))
            return path
        except Exception:
            continue
    return None

def build_lead_magnet_pdf(posts: List[Dict[str, Any]]) -> bool:
    """발행된 글들의 표현/뜻을 모아 무료 PDF 가이드를 만든다. reportlab 미설치 시 조용히 건너뜀."""
    if not _REPORTLAB_AVAILABLE or not posts:
        return False
    try:
        font_path = _find_korean_ttf()
        font_name = "Helvetica"
        font_name_bold = "Helvetica-Bold"
        if font_path:
            try:
                pdfmetrics.registerFont(TTFont("KRFont", font_path))
                font_name = font_name_bold = "KRFont"
            except Exception as e:
                logger.warning(f"[리드마그넷] 한글 폰트 등록 실패, 영문 폰트로 대체: {e}")

        out_path = os.path.join(DOCS_DIR, "downloads", "korean-expressions-guide.pdf")
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        c = pdf_canvas.Canvas(out_path, pagesize=A4)
        w, h = A4

        # 표지
        c.setFillColorRGB(0.91, 0.36, 0.52)
        c.rect(0, 0, w, h, fill=1, stroke=0)
        c.setFillColorRGB(1, 1, 1)
        c.setFont(font_name_bold, 26)
        c.drawCentredString(w / 2, h - 160, SITE_TITLE)
        c.setFont(font_name, 13)
        c.drawCentredString(w / 2, h - 195, "Korean Expressions Guide")
        c.setFont(font_name, 10)
        c.drawCentredString(w / 2, h - 220, f"{len(posts)}개 표현 · {datetime.now().strftime('%Y-%m-%d')} 기준")
        c.showPage()

        # 목록 (표현 + 뜻 요약)
        y = h - 60
        c.setFillColorRGB(0.1, 0.1, 0.1)
        for p in posts:
            if y < 80:
                c.showPage()
                y = h - 60
                c.setFillColorRGB(0.1, 0.1, 0.1)
            c.setFont(font_name_bold, 13)
            c.drawString(50, y, p.get("title", "")[:70])
            y -= 26
        c.showPage()
        c.save()
        logger.info(f"[리드마그넷] PDF 갱신 완료: {out_path} ({len(posts)}개 표현)")
        return True
    except Exception as e:
        logger.warning(f"[리드마그넷] PDF 생성 실패(건너뜀): {e}")
        return False

def _lead_magnet_html() -> str:
    """홈페이지에 노출할 무료 PDF 다운로드 배너. 파일이 실제로 존재할 때만 렌더링."""
    pdf_path = os.path.join(DOCS_DIR, "downloads", "korean-expressions-guide.pdf")
    if not os.path.exists(pdf_path):
        return ""
    return (
        '<a class="lead-magnet" href="downloads/korean-expressions-guide.pdf" download>'
        '<span class="lead-magnet-emoji">📘</span>'
        '<span><span class="lead-magnet-title">무료 PDF: 한국인이 매일 쓰는 표현 모음</span>'
        '<div class="lead-magnet-sub">Free PDF guide of real Korean expressions</div></span>'
        '<span class="lead-magnet-cta">다운로드</span></a>'
    )

def _social_row_html() -> str:
    """설정된 SNS 채널만 아이콘으로 노출 (하나도 설정 안 되어 있으면 빈 문자열)"""
    links = []
    if SNS_PINTEREST_URL: links.append(f'<a href="{SNS_PINTEREST_URL}" target="_blank" rel="noopener" aria-label="Pinterest">📌</a>')
    if SNS_INSTAGRAM_URL: links.append(f'<a href="{SNS_INSTAGRAM_URL}" target="_blank" rel="noopener" aria-label="Instagram">📷</a>')
    if SNS_X_URL: links.append(f'<a href="{SNS_X_URL}" target="_blank" rel="noopener" aria-label="X">𝕏</a>')
    if not links:
        return ""
    return f'<div class="social-row">{"".join(links)}</div>'

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

# =====================================================================
# [NEW] Google 색인 생성 자동 요청 (Google Indexing API)
# 새 글을 발행할 때마다 Search Console에서 손으로 누르던 "색인 생성 요청"을 자동화한다.
# 기존 Blogger용 OAuth(GOOGLE_CLIENT_ID/SECRET/REFRESH_TOKEN)를 그대로 재사용하되,
# 리프레시 토큰 발급 시 동의한 스코프에 "indexing"이 포함되어 있어야 동작한다.
#
# 준비물(최초 1회):
# 1) Google Cloud Console에서 "Web Search Indexing API" 사용 설정
# 2) get_refresh_token.py의 SCOPES 목록에 https://www.googleapis.com/auth/indexing 추가 후 재실행
#    (기존 blogger 스코프와 함께 재동의 → GOOGLE_REFRESH_TOKEN 갱신)
# 3) Search Console → 설정 → 사용자 및 권한 → 이 리프레시 토큰을 발급한 Google 계정을
#    "소유자(Owner)"로 추가 (블로그가 걸려있는 실제 속성: 예) learnkoreanseekoreans.blogspot.com)
# 위 준비가 안 되어 있으면 조용히 건너뛰고 로그만 남기며, 파이프라인은 계속 진행된다.
# =====================================================================
def _google_oauth_configured() -> bool: return bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET and GOOGLE_REFRESH_TOKEN)

def request_google_indexing(url: str) -> bool:
    if not url or not _google_oauth_configured():
        return False
    try:
        access_token = _get_blogger_access_token()
        resp = requests.post(
            "https://indexing.googleapis.com/v3/urlNotifications:publish",
            headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
            json={"url": url, "type": "URL_UPDATED"},
            timeout=20,
        )
        if resp.ok:
            logger.info(f"[색인 요청] 완료: {url}")
            return True
        # [FIX] 스코프 미동의(403)나 속성 소유권 미확인(403) 등 원인이 다양해 본문을 그대로 로그에 남김
        logger.warning(f"[색인 요청] 실패(HTTP {resp.status_code}), 발행 자체는 정상 진행됩니다: {resp.text[:300]}")
        return False
    except Exception as e:
        logger.warning(f"[색인 요청] 오류(건너뜀): {e}")
        return False

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



# =====================================================================
# [AdSense / Blogger 레이아웃] 매 글·정책 페이지에 공통 내비/푸터 자동 삽입
# 테마 메뉴를 API로 직접 바꾸기는 어렵기 때문에, 본문 상·하단에 고정 링크 바를 넣어
# About / Privacy / Contact 가 항상 보이게 한다.
# =====================================================================
_BLOGGER_PAGE_SLUGS = {
    "About": "about",
    "Privacy Policy": "privacy-policy",
    "Contact": "contact",
}


def _default_policy_page_urls() -> Dict[str, str]:
    """Secrets/기본값으로 고정된 실제 About·Privacy·Contact URL."""
    return {
        "About": BLOGGER_ABOUT_URL,
        "Privacy Policy": BLOGGER_PRIVACY_URL,
        "Contact": BLOGGER_CONTACT_URL,
    }


def _merge_policy_page_urls(discovered: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """기본 URL을 깔고, API에서 찾은 URL이 있으면 덮어쓴다."""
    merged = _default_policy_page_urls()
    for k, v in (discovered or {}).items():
        if v:
            merged[k] = v.rstrip("/")
    return merged


def _get_blogger_blog_url(access_token: str) -> str:
    """블로그 홈 URL (끝 슬래시 제거). 실패 시 빈 문자열."""
    try:
        resp = requests.get(
            f"https://www.googleapis.com/blogger/v3/blogs/{BLOGGER_BLOG_ID}",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=20,
        )
        if not resp.ok:
            return ""
        return (resp.json().get("url") or "").rstrip("/")
    except Exception as e:
        logger.warning(f"[블로거] 블로그 URL 조회 실패: {e}")
        return ""


def _blogger_page_href(blog_url: str, title: str, page_url_from_api: str = "") -> str:
    """우선순위: 인자 URL → 기본(Secrets) URL → /p/slug 추정."""
    if page_url_from_api:
        return page_url_from_api
    defaults = _default_policy_page_urls()
    if title in defaults and defaults[title]:
        return defaults[title]
    slug = _BLOGGER_PAGE_SLUGS.get(title, title.lower().replace(" ", "-"))
    if blog_url:
        return f"{blog_url}/p/{slug}.html"
    return f"/p/{slug}.html"


def _blogger_site_nav_html(blog_url: str = "", page_urls: Optional[Dict[str, str]] = None) -> str:
    """글 상단 고정 내비 — About / Privacy / Contact + Home."""
    page_urls = page_urls or {}
    home = blog_url or "/"
    about = _blogger_page_href(blog_url, "About", page_urls.get("About", ""))
    privacy = _blogger_page_href(blog_url, "Privacy Policy", page_urls.get("Privacy Policy", ""))
    contact = _blogger_page_href(blog_url, "Contact", page_urls.get("Contact", ""))
    link_style = (
        "color:#333;text-decoration:none;font-size:0.85em;font-weight:600;"
        "padding:6px 10px;border-radius:999px;background:#f3f4f6;display:inline-block;"
    )
    return (
        '<nav class="site-policy-nav" style="margin:0 0 18px;padding:12px 14px;border-radius:12px;'
        'background:linear-gradient(180deg,#fafafa,#f3f4f6);border:1px solid #e5e7eb;'
        'display:flex;flex-wrap:wrap;gap:8px;align-items:center;font-family:system-ui,sans-serif;">'
        f'<a href="{html.escape(home, quote=True)}" style="{link_style}">Home</a>'
        f'<a href="{html.escape(about, quote=True)}" style="{link_style}">About</a>'
        f'<a href="{html.escape(privacy, quote=True)}" style="{link_style}">Privacy</a>'
        f'<a href="{html.escape(contact, quote=True)}" style="{link_style}">Contact</a>'
        '<span style="margin-left:auto;font-size:0.75em;color:#6b7280;">Learn Korean · Understand Koreans</span>'
        '</nav>'
    )


def _blogger_site_footer_html(blog_url: str = "", page_urls: Optional[Dict[str, str]] = None) -> str:
    """글 하단 레이아웃 문구 + 정책 링크 (심사·신뢰용)."""
    page_urls = page_urls or {}
    about = _blogger_page_href(blog_url, "About", page_urls.get("About", ""))
    privacy = _blogger_page_href(blog_url, "Privacy Policy", page_urls.get("Privacy Policy", ""))
    contact = _blogger_page_href(blog_url, "Contact", page_urls.get("Contact", ""))
    home = blog_url or "/"
    return (
        '<footer class="site-policy-footer" style="margin-top:2.5em;padding:18px 16px;border-top:1px solid #e5e7eb;'
        'font-size:0.86em;color:#4b5563;line-height:1.6;font-family:system-ui,sans-serif;">'
        f'<p style="margin:0 0 8px;"><b style="color:#111;">{html.escape(SITE_TITLE)}</b> — '
        'practical notes on Korean expressions, nuance, and everyday culture for learners.</p>'
        '<p style="margin:0 0 10px;">We aim for concrete examples you can use in real conversations—not keyword filler. '
        'Nuance still varies by age, region, and relationship.</p>'
        '<p style="margin:0;display:flex;flex-wrap:wrap;gap:10px;">'
        f'<a href="{html.escape(home, quote=True)}" style="color:#2563eb;">Home</a>'
        f'<a href="{html.escape(about, quote=True)}" style="color:#2563eb;">About</a>'
        f'<a href="{html.escape(privacy, quote=True)}" style="color:#2563eb;">Privacy Policy</a>'
        f'<a href="{html.escape(contact, quote=True)}" style="color:#2563eb;">Contact</a>'
        '</p></footer>'
    )



def _replace_policy_chrome(html_body: str, blog_url: str = "", page_urls: Optional[Dict[str, str]] = None, expression: str = "") -> str:
    """기존 site-policy-nav / footer / reader-value 를 제거하고 올바른 URL로 다시 삽입.
    (한 번 잘못된 /p/ 링크가 들어가면 예전 리페어는 '이미 있음'으로 건너뛰어 고치지 못했음)
    """
    if not html_body:
        html_body = ""
    page_urls = _merge_policy_page_urls(page_urls)
    # 기존 크롬 제거 (중첩·중복 방지)
    cleaned = re.sub(
        r'<nav\b[^>]*class="[^"]*site-policy-nav[^"]*"[^>]*>.*?</nav>',
        '',
        html_body,
        flags=re.DOTALL | re.IGNORECASE,
    )
    cleaned = re.sub(
        r'<footer\b[^>]*class="[^"]*site-policy-footer[^"]*"[^>]*>.*?</footer>',
        '',
        cleaned,
        flags=re.DOTALL | re.IGNORECASE,
    )
    cleaned = re.sub(
        r'<div\b[^>]*class="[^"]*reader-value[^"]*"[^>]*>.*?</div>',
        '',
        cleaned,
        flags=re.DOTALL | re.IGNORECASE,
    )
    # 잘못된 /p/about|/p/privacy|/p/contact 단독 링크도 교정 (크롬 밖 잔존 대비)
    for title, url in page_urls.items():
        if not url:
            continue
        cleaned = re.sub(
            r'https?://[^\s"\']+/p/(about|privacy|privacy-policy|contact)\.html',
            url,
            cleaned,
            flags=re.IGNORECASE,
        )
    nav = _blogger_site_nav_html(blog_url, page_urls)
    value = _reader_value_box_html(expression)
    foot = _blogger_site_footer_html(blog_url, page_urls)
    return nav + value + cleaned.strip() + foot


def _reader_value_box_html(expression: str = "") -> str:
    """본문 상단(내비 아래)에 넣는 '이 글에서 얻는 것' 박스 — 사람 편집 느낌을 보강."""
    focus = html.escape((expression or "").strip())
    focus_line = f' <span class="notranslate">“{focus}”</span>' if focus else ""
    return (
        '<div class="reader-value" style="margin:0 0 20px;padding:14px 16px;border-left:4px solid #2563eb;'
        'background:#eff6ff;border-radius:0 10px 10px 0;font-size:0.92em;color:#1e3a5f;line-height:1.55;">'
        f'<b>What you will get</b>{focus_line}<br>'
        '1) When Koreans actually say it &nbsp;·&nbsp; 2) Why a direct translation falls short &nbsp;·&nbsp; '
        '3) A short cultural cue you can remember</div>'
    )


def _maybe_auto_repair_once() -> None:
    """하루 1회 한도로 과거 글 고정 템플릿/단정 표현 리페어를 자동 실행."""
    if not AUTO_REPAIR_ONCE_PER_DAY:
        return
    marker = os.path.join(DOCS_DIR, ".last_auto_repair_date")
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        if os.path.exists(marker):
            with open(marker, "r", encoding="utf-8") as f:
                if f.read().strip() == today:
                    logger.info("[자동 리페어] 오늘 이미 실행됨 — 건너뜁니다.")
                    return
        logger.info("[자동 리페어] 하루 1회 한도로 repair_old_posts() 실행을 시작합니다.")
        repair_old_posts()
        os.makedirs(DOCS_DIR, exist_ok=True)
        with open(marker, "w", encoding="utf-8") as f:
            f.write(today)
        logger.info("[자동 리페어] 완료 및 날짜 마커 저장")
    except Exception as e:
        logger.warning(f"[자동 리페어] 실패(발행은 계속): {e}")


def ensure_blogger_policy_pages() -> Dict[str, str]:
    """AdSense용 About / Privacy / Contact 페이지를 Blogger에 동기화하고 {제목: url} 맵을 반환.
    각 페이지 본문에도 공통 내비/푸터를 넣어 메뉴처럼 보이게 한다.
    """
    page_urls: Dict[str, str] = _default_policy_page_urls()
    if not _blogger_configured():
        return page_urls
    try:
        access_token = _get_blogger_access_token()
        blog_url = _get_blogger_blog_url(access_token)
        # 1차: 기존 페이지 URL 수집
        list_url = f"https://www.googleapis.com/blogger/v3/blogs/{BLOGGER_BLOG_ID}/pages/"
        resp = requests.get(
            list_url,
            headers={"Authorization": f"Bearer {access_token}"},
            params={"fetchBodies": "false", "maxResults": 50},
            timeout=30,
        )
        existing: Dict[str, Dict[str, str]] = {}
        if resp.ok:
            for item in resp.json().get("items") or []:
                t = (item.get("title") or "").strip()
                existing[t.lower()] = {"id": item.get("id", ""), "url": item.get("url", "")}
                if t in ("About", "Privacy Policy", "Contact") and item.get("url"):
                    page_urls[t] = item["url"]

        contact_block = (
            f"<p><b>Email:</b> {html.escape(CONTACT_EMAIL)}</p>"
            if CONTACT_EMAIL else
            "<p><b>Email:</b> Contact via the form or email listed in blog settings.</p>"
        )
        bodies = {
            "About": (
                f"<p><b>{html.escape(SITE_TITLE)}</b></p>"
                f"<p>{ENGLISH_SLOGAN}</p>"
                f"<p>{html.escape(SITE_TAGLINE)}</p>"
                "<h2>Who this is for</h2>"
                "<p>Learners of Korean who want usage, nuance, and cultural context—not only dictionary definitions.</p>"
                "<h2>Editorial process</h2>"
                "<p>Posts follow a teaching outline. AI may assist drafting; content is checked for concrete examples and clear explanations.</p>"
                "<h2>Site menu</h2>"
                "<p>Use the links at the top of every post: Home · About · Privacy · Contact.</p>"
            ),
            "Privacy Policy": (
                "<p>This blog may use Google Analytics and Google AdSense. Cookies may be used for stats and ads.</p>"
                "<p>You can control personalized ads at "
                '<a href="https://adssettings.google.com" target="_blank" rel="noopener">Google Ads Settings</a>.</p>'
            ),
            "Contact": (
                "<p>Corrections, questions, and collaboration ideas are welcome.</p>" + contact_block
            ),
        }
        for title, core_body in bodies.items():
            nav = _blogger_site_nav_html(blog_url, page_urls)
            foot = _blogger_site_footer_html(blog_url, page_urls)
            payload = {"title": title, "content": nav + core_body + foot}
            meta = existing.get(title.lower())
            if meta and meta.get("id"):
                upd = requests.put(
                    f"https://www.googleapis.com/blogger/v3/blogs/{BLOGGER_BLOG_ID}/pages/{meta['id']}",
                    headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
                    json=payload,
                    timeout=30,
                )
                if upd.ok:
                    url = (upd.json() or {}).get("url") or meta.get("url") or ""
                    if url:
                        page_urls[title] = url
                    logger.info(f"[블로거 페이지] 갱신: {title} → {page_urls.get(title, '')}")
                else:
                    logger.warning(f"[블로거 페이지] 갱신 실패({title}): HTTP {upd.status_code}")
            else:
                cre = requests.post(
                    list_url,
                    headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
                    json={**payload, "isDraft": False},
                    timeout=30,
                )
                if cre.ok:
                    data = cre.json() or {}
                    if data.get("url"):
                        page_urls[title] = data["url"]
                    logger.info(f"[블로거 페이지] 생성: {title} → {page_urls.get(title, '')}")
                else:
                    logger.warning(f"[블로거 페이지] 생성 실패({title}): HTTP {cre.status_code} {cre.text[:200]}")
        return page_urls
    except Exception as e:
        logger.warning(f"[블로거 페이지] 동기화 건너뜀: {e}")
        return page_urls



# =====================================================================
# [NEW] Threads + Instagram 자동 발행 (Blogger 발행 성공 후)
# - 이미지 URL은 공개 접근 가능해야 함 (GitHub Pages thumbs URL 사용)
# - 토큰/ID 미설정 시 스킵. 예외는 로그 후 삼킴 (메인 파이프라인 보호)
# =====================================================================
def _sns_caption(article: Dict[str, Any], blogger_url: str, *, platform: str) -> str:
    """플랫폼별 홍보 캡션 — 구글 블로그 링크를 맨 앞에 두어 전환 유도."""
    title = (article.get("title") or "").strip()
    expr = (article.get("expression") or "").strip()
    cat = (article.get("category") or "").strip()
    link = (blogger_url or "").strip()
    lines = []
    if link:
        lines.append("📖 구글 블로그에서 이어서 읽기")
        lines.append(link)
        lines.append("")
    if expr:
        lines.append(f"Korean expression: “{expr}”")
    if title:
        lines.append(title)
    lines.append("한 컷으로 상황만 보고, 자세한 뉘앙스는 블로그에서 확인하세요.")
    lines.append("Learn Korean → understand how Koreans think & speak.")
    tags = ["#LearnKorean", "#KoreanLanguage", "#한국어", "#KoreanCulture", "#인스타툰"]
    if cat:
        tags.insert(0, f"#{cat.replace(' ', '')}")
    lines.append(" ".join(tags))
    caption = "\n".join(lines)
    limit = 480 if platform == "threads" else 2100
    if len(caption) > limit:
        if link and link not in caption[:limit]:
            caption = caption[: max(0, limit - len(link) - 5)].rstrip() + "…\n" + link
        else:
            caption = caption[: limit - 1].rstrip() + "…"
    return caption



def _wait_media_container_ready(
    status_url: str,
    access_token: str,
    *,
    label: str,
    max_attempts: int = 12,
    delay_sec: float = 3.0,
) -> bool:
    """컨테이너 status_code 가 FINISHED 될 때까지 폴링."""
    for i in range(1, max_attempts + 1):
        try:
            r = requests.get(status_url, params={"fields": "status_code,status", "access_token": access_token}, timeout=30)
            data = r.json() if r.ok else {}
            code = (data.get("status_code") or data.get("status") or "").upper()
            logger.info(f"[{label}] 컨테이너 상태 ({i}/{max_attempts}): {code or r.text[:120]}")
            if code in ("FINISHED", "PUBLISHED"):
                return True
            if code in ("ERROR", "EXPIRED"):
                logger.warning(f"[{label}] 컨테이너 실패: {data}")
                return False
        except Exception as e:
            logger.warning(f"[{label}] 상태 조회 오류: {e}")
        time.sleep(delay_sec)
    return False


def publish_to_threads(article: Dict[str, Any], blogger_url: str, image_url: str) -> Optional[str]:
    """Threads 이미지(+텍스트) 게시. 성공 시 media id 또는 permalink 힌트 반환."""
    if not THREADS_ENABLED:
        return None
    if not (THREADS_USER_ID and THREADS_ACCESS_TOKEN):
        logger.info("[Threads] 미설정(THREADS_USER_ID / THREADS_ACCESS_TOKEN) — 건너뜁니다.")
        return None
    if not image_url:
        logger.warning("[Threads] image_url 비어 있음 — 건너뜁니다.")
        return None
    caption = _sns_caption(article, blogger_url, platform="threads")
    try:
        create = requests.post(
            f"{THREADS_API_BASE}/{THREADS_USER_ID}/threads",
            data={
                "media_type": "IMAGE",
                "image_url": image_url,
                "text": caption,
                "access_token": THREADS_ACCESS_TOKEN,
            },
            timeout=60,
        )
        if not create.ok:
            logger.warning(f"[Threads] 컨테이너 생성 실패 HTTP {create.status_code}: {create.text[:400]}")
            return None
        creation_id = (create.json() or {}).get("id")
        if not creation_id:
            logger.warning(f"[Threads] creation_id 없음: {create.text[:300]}")
            return None
        ready = _wait_media_container_ready(
            f"{THREADS_API_BASE}/{creation_id}",
            THREADS_ACCESS_TOKEN,
            label="Threads",
        )
        if not ready:
            logger.warning("[Threads] 컨테이너 준비 시간 초과 — 발행 시도는 계속합니다.")
        pub = requests.post(
            f"{THREADS_API_BASE}/{THREADS_USER_ID}/threads_publish",
            data={"creation_id": creation_id, "access_token": THREADS_ACCESS_TOKEN},
            timeout=60,
        )
        if not pub.ok:
            logger.warning(f"[Threads] 발행 실패 HTTP {pub.status_code}: {pub.text[:400]}")
            return None
        media_id = (pub.json() or {}).get("id", "")
        logger.info(f"[Threads] 발행 완료 id={media_id}")
        return media_id or creation_id
    except Exception as e:
        logger.warning(f"[Threads] 예외(건너뜀): {e}")
        return None


def publish_to_instagram(article: Dict[str, Any], blogger_url: str, image_url: str) -> Optional[str]:
    """Instagram Professional 계정 이미지 게시 (텍스트 단독 불가 → 썸네일 필수)."""
    if not INSTAGRAM_ENABLED:
        return None
    if not (INSTAGRAM_USER_ID and INSTAGRAM_ACCESS_TOKEN):
        logger.info("[Instagram] 미설정(INSTAGRAM_USER_ID / INSTAGRAM_ACCESS_TOKEN) — 건너뜁니다.")
        return None
    if not image_url:
        logger.warning("[Instagram] image_url 비어 있음 — 건너뜁니다.")
        return None
    caption = _sns_caption(article, blogger_url, platform="instagram")
    try:
        create = requests.post(
            f"{INSTAGRAM_API_BASE}/{INSTAGRAM_USER_ID}/media",
            data={
                "image_url": image_url,
                "caption": caption,
                "access_token": INSTAGRAM_ACCESS_TOKEN,
            },
            timeout=60,
        )
        if not create.ok:
            logger.warning(f"[Instagram] 컨테이너 생성 실패 HTTP {create.status_code}: {create.text[:400]}")
            return None
        creation_id = (create.json() or {}).get("id")
        if not creation_id:
            logger.warning(f"[Instagram] creation_id 없음: {create.text[:300]}")
            return None
        ready = _wait_media_container_ready(
            f"{INSTAGRAM_API_BASE}/{creation_id}",
            INSTAGRAM_ACCESS_TOKEN,
            label="Instagram",
        )
        if not ready:
            logger.warning("[Instagram] 컨테이너 준비 시간 초과 — 발행 시도는 계속합니다.")
        pub = requests.post(
            f"{INSTAGRAM_API_BASE}/{INSTAGRAM_USER_ID}/media_publish",
            data={"creation_id": creation_id, "access_token": INSTAGRAM_ACCESS_TOKEN},
            timeout=60,
        )
        if not pub.ok:
            logger.warning(f"[Instagram] 발행 실패 HTTP {pub.status_code}: {pub.text[:400]}")
            return None
        media_id = (pub.json() or {}).get("id", "")
        logger.info(f"[Instagram] 발행 완료 id={media_id}")
        return media_id or creation_id
    except Exception as e:
        logger.warning(f"[Instagram] 예외(건너뜀): {e}")
        return None


def _publish_threads_carousel(article: Dict[str, Any], blogger_url: str, image_urls: List[str]) -> Optional[str]:
    """Threads 캐러셀(카드뉴스). 실패 시 None."""
    if not (THREADS_ENABLED and THREADS_USER_ID and THREADS_ACCESS_TOKEN):
        return None
    if len(image_urls) < 2:
        return None
    caption = _sns_caption(article, blogger_url, platform="threads")
    try:
        child_ids = []
        for url in image_urls[:10]:
            r = requests.post(
                f"{THREADS_API_BASE}/{THREADS_USER_ID}/threads",
                data={
                    "media_type": "IMAGE",
                    "image_url": url,
                    "is_carousel_item": "true",
                    "access_token": THREADS_ACCESS_TOKEN,
                },
                timeout=60,
            )
            if not r.ok:
                logger.warning(f"[Threads] 캐러셀 자식 실패: {r.status_code} {r.text[:200]}")
                return None
            cid = (r.json() or {}).get("id")
            if not cid:
                return None
            child_ids.append(cid)
            _wait_media_container_ready(f"{THREADS_API_BASE}/{cid}", THREADS_ACCESS_TOKEN, label="Threads-child")
        parent = requests.post(
            f"{THREADS_API_BASE}/{THREADS_USER_ID}/threads",
            data={
                "media_type": "CAROUSEL",
                "children": ",".join(child_ids),
                "text": caption,
                "access_token": THREADS_ACCESS_TOKEN,
            },
            timeout=60,
        )
        if not parent.ok:
            logger.warning(f"[Threads] 캐러셀 부모 실패: {parent.status_code} {parent.text[:300]}")
            return None
        creation_id = (parent.json() or {}).get("id")
        if not creation_id:
            return None
        _wait_media_container_ready(f"{THREADS_API_BASE}/{creation_id}", THREADS_ACCESS_TOKEN, label="Threads-carousel")
        pub = requests.post(
            f"{THREADS_API_BASE}/{THREADS_USER_ID}/threads_publish",
            data={"creation_id": creation_id, "access_token": THREADS_ACCESS_TOKEN},
            timeout=60,
        )
        if not pub.ok:
            logger.warning(f"[Threads] 캐러셀 발행 실패: {pub.status_code} {pub.text[:300]}")
            return None
        mid = (pub.json() or {}).get("id", "")
        logger.info(f"[Threads] 카드뉴스 캐러셀 발행 완료 id={mid}")
        return mid or creation_id
    except Exception as e:
        logger.warning(f"[Threads] 캐러셀 예외: {e}")
        return None


def _publish_instagram_carousel(article: Dict[str, Any], blogger_url: str, image_urls: List[str]) -> Optional[str]:
    """Instagram 캐러셀(카드뉴스)."""
    if not (INSTAGRAM_ENABLED and INSTAGRAM_USER_ID and INSTAGRAM_ACCESS_TOKEN):
        return None
    if len(image_urls) < 2:
        return None
    caption = _sns_caption(article, blogger_url, platform="instagram")
    try:
        child_ids = []
        for url in image_urls[:10]:
            r = requests.post(
                f"{INSTAGRAM_API_BASE}/{INSTAGRAM_USER_ID}/media",
                data={
                    "image_url": url,
                    "is_carousel_item": "true",
                    "access_token": INSTAGRAM_ACCESS_TOKEN,
                },
                timeout=60,
            )
            if not r.ok:
                logger.warning(f"[Instagram] 캐러셀 자식 실패: {r.status_code} {r.text[:200]}")
                return None
            cid = (r.json() or {}).get("id")
            if not cid:
                return None
            child_ids.append(cid)
            _wait_media_container_ready(f"{INSTAGRAM_API_BASE}/{cid}", INSTAGRAM_ACCESS_TOKEN, label="IG-child")
        parent = requests.post(
            f"{INSTAGRAM_API_BASE}/{INSTAGRAM_USER_ID}/media",
            data={
                "media_type": "CAROUSEL",
                "children": ",".join(child_ids),
                "caption": caption,
                "access_token": INSTAGRAM_ACCESS_TOKEN,
            },
            timeout=60,
        )
        if not parent.ok:
            logger.warning(f"[Instagram] 캐러셀 부모 실패: {parent.status_code} {parent.text[:300]}")
            return None
        creation_id = (parent.json() or {}).get("id")
        if not creation_id:
            return None
        _wait_media_container_ready(f"{INSTAGRAM_API_BASE}/{creation_id}", INSTAGRAM_ACCESS_TOKEN, label="IG-carousel")
        pub = requests.post(
            f"{INSTAGRAM_API_BASE}/{INSTAGRAM_USER_ID}/media_publish",
            data={"creation_id": creation_id, "access_token": INSTAGRAM_ACCESS_TOKEN},
            timeout=60,
        )
        if not pub.ok:
            logger.warning(f"[Instagram] 캐러셀 발행 실패: {pub.status_code} {pub.text[:300]}")
            return None
        mid = (pub.json() or {}).get("id", "")
        logger.info(f"[Instagram] 카드뉴스 캐러셀 발행 완료 id={mid}")
        return mid or creation_id
    except Exception as e:
        logger.warning(f"[Instagram] 캐러셀 예외: {e}")
        return None


def publish_to_sns(article: Dict[str, Any], blogger_url: str, image_url: str) -> None:
    """Blogger 성공 후: 인스타툰 → Threads/Instagram 캐러셀 업로드."""
    if not blogger_url:
        return
    card = article.get("_card_news") if isinstance(article.get("_card_news"), dict) else None
    try:
        # 블로그 URL이 생긴 뒤 CTA 슬라이드 보강 위해 1회 더 생성(덮어쓰기)
        card = generate_instatoon_images(article, blogger_url)
        article["_card_news"] = card  # 키 유지(하위호환)
        commit_and_push_changes()
    except Exception as e:
        logger.warning(f"[인스타툰] 생성 실패(썸네일 폴백): {e}")

    urls = (card or {}).get("public_urls") or []
    if not urls:
        # 폴백: 기존 썸네일 단일 이미지
        if image_url and (image_url.startswith("http://") or image_url.startswith("https://")):
            urls = [image_url]
        else:
            logger.warning("[SNS] 업로드할 공개 이미지 URL 없음 — 스킵")
            return

    if len(urls) >= 2:
        th = _publish_threads_carousel(article, blogger_url, urls)
        if not th:
            publish_to_threads(article, blogger_url, urls[0])
        ig = _publish_instagram_carousel(article, blogger_url, urls)
        if not ig:
            publish_to_instagram(article, blogger_url, urls[0])
    else:
        publish_to_threads(article, blogger_url, urls[0])
        publish_to_instagram(article, blogger_url, urls[0])

    if card and card.get("download_dir"):
        logger.info(f"[인스타툰] 로컬 다운로드 폴더: {card['download_dir']}")




def _repair_blogger_hero_image(html_content: str, local_thumb_path: str, title: str, public_thumb_url: str = "") -> str:
    """Blogger 본문 첫 이미지/깨진 히어로를 새 JPEG(+data-URI 폴백)으로 교체."""
    if not html_content:
        return html_content
    hero = _blogger_hero_img_html(public_thumb_url, local_thumb_path, title)
    # 기존 첫 <img ...> 를 히어로로 교체 (nav 아이콘 등 작은 이미지 제외: max-width 스타일 또는 상단부)
    def _repl_first_img(m):
        return hero
    new_html, n = re.subn(
        r'<img\b[^>]*(?:max-width:\s*100%|heroThumb|thumbs/)[^>]*>',
        _repl_first_img,
        html_content,
        count=1,
        flags=re.IGNORECASE,
    )
    if n:
        return new_html
    # 패턴 못 찾으면 nav 다음 / value box 다음에 삽입
    if "site-policy-nav" in html_content and hero not in html_content:
        new_html = re.sub(
            r'(</nav>)',
            r'\1' + hero,
            html_content,
            count=1,
            flags=re.IGNORECASE,
        )
        return new_html
    return html_content


def _blogger_hero_img_html(thumb_url: str, local_thumb_path: str, title: str) -> str:
    """Blogger 본문 히어로. 로컬 JPEG를 data-URI로 넣어 깨짐 방지 + 공개 URL을 src에 병기."""
    alt = html.escape(title, quote=True)
    src = (thumb_url or "").strip()
    data_uri = ""
    try:
        path = local_thumb_path or ""
        if path and not os.path.isfile(path):
            for ext in (".jpg", ".jpeg", ".png", ".webp"):
                alt_path = os.path.splitext(path)[0] + ext
                if os.path.isfile(alt_path):
                    path = alt_path
                    break
        if path and os.path.isfile(path):
            im = Image.open(path).convert("RGB")
            im.thumbnail((1280, 720))
            import io
            buf = io.BytesIO()
            im.save(buf, format="JPEG", quality=82, optimize=True)
            data_uri = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception as e:
        logger.warning(f"[블로거] 히어로 data-URI 준비 실패: {e}")
    style = "max-width:100%;height:auto;border-radius:8px;display:block;background:#1a1a1a;"
    # data-URI를 1순위로 쓰면 Blogger 편집기/본문에서 항상 보임 (외부 404 무관)
    if data_uri:
        return f'<img src="{data_uri}" style="{style}" alt="{alt}" loading="eager">'
    if src.startswith("http://") or src.startswith("https://"):
        return f'<img src="{html.escape(src, quote=True)}" style="{style}" alt="{alt}" loading="eager">'
    return f'<p style="color:#999;padding:24px;background:#eee;border-radius:8px;">(thumbnail unavailable)</p>'



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
        blog_url = _get_blogger_blog_url(access_token)
        # 정책 페이지 URL (가능하면 API에서 수집한 실제 URL)
        page_urls: Dict[str, str] = {}
        try:
            pages_resp = requests.get(
                f"https://www.googleapis.com/blogger/v3/blogs/{BLOGGER_BLOG_ID}/pages/",
                headers={"Authorization": f"Bearer {access_token}"},
                params={"fetchBodies": "false", "maxResults": 50},
                timeout=20,
            )
            if pages_resp.ok:
                for item in pages_resp.json().get("items") or []:
                    t = (item.get("title") or "").strip()
                    if t in ("About", "Privacy Policy", "Contact") and item.get("url"):
                        page_urls[t] = item["url"]
        except Exception as e:
            logger.warning(f"[블로거] 페이지 URL 조회 실패(내비는 추정 경로 사용): {e}")

        page_urls = _merge_policy_page_urls(page_urls)
        # Posts로 올라간 About/Privacy/Contact 도 제목으로 한 번 더 탐색
        try:
            posts_scan = requests.get(
                f"https://www.googleapis.com/blogger/v3/blogs/{BLOGGER_BLOG_ID}/posts/",
                headers={"Authorization": f"Bearer {access_token}"},
                params={"maxResults": 50, "fetchBodies": "false"},
                timeout=20,
            )
            if posts_scan.ok:
                for item in posts_scan.json().get("items") or []:
                    t = (item.get("title") or "").strip()
                    if t in ("About", "Privacy Policy", "Contact", "Privacy", "About this blog") and item.get("url"):
                        key = "Privacy Policy" if t in ("Privacy", "Privacy Policy") else ("About" if "About" in t else "Contact")
                        if t == "Contact":
                            key = "Contact"
                        if t in ("About", "About this blog"):
                            key = "About"
                        page_urls[key] = item["url"]
        except Exception as e:
            logger.warning(f"[블로거] 정책 글(Posts) URL 스캔 실패: {e}")
        page_urls = _merge_policy_page_urls(page_urls)
        nav_html = _blogger_site_nav_html(blog_url, page_urls)
        value_html = _reader_value_box_html(article.get("expression", ""))
        footer_html = _blogger_site_footer_html(blog_url, page_urls)
        content_html = (
            f'{_translate_widget()}'
            f'{nav_html}'
            f'{value_html}'
            f'<div style="position:relative;margin:0;">'
            f'{_blogger_hero_img_html(thumb_url, local_thumb_path, article.get("title") or "")}'
            f'{_tts_buttons_html(article.get("expression", ""), theme)}'
            f'</div>'
            f'<span style="display:inline-block;background:{theme["accent"]};color:#fff;font-size:0.85em;font-weight:bold;padding:4px 12px;border-radius:999px;margin:14px 0 4px;">{theme["badge"]}</span>'
            f'{_make_blogger_safe_html(article["html_body"])}'
            f'{footer_html}'
            f'<script type="application/ld+json">{blogger_json_ld}</script>'
        )
        url = f"https://www.googleapis.com/blogger/v3/blogs/{BLOGGER_BLOG_ID}/posts/"
        # 라벨: 카테고리 + 고정 주제 라벨 → Blogger 사이드바/탐색에 구조가 보이게 (심사·체류에 도움)
        labels = []
        cat = (article.get("category") or "").strip()
        if cat:
            labels.append(cat)
        labels.append("Learn Korean")
        labels.append("Korean Culture")
        expr = (article.get("expression") or "").strip()
        if expr and expr not in labels:
            labels.append(expr[:50])
        post_payload = {
            "title": article["title"],
            "content": content_html,
            "labels": labels[:5],
        }
        if ADSENSE_REVIEW_MODE:
            logger.info("[블로거] ADSENSE_REVIEW_MODE=ON — 본문 수동 광고/제휴 블록 없이 발행합니다. Blogger 자동 광고만 사용하세요.")
        # [FIX] 짧은 간격으로 연달아 요청하면 토큰/권한이 멀쩡해도 구글 쪽에서 일시적으로
        # 403/429/503을 반환하는 사례가 확인됨 (같은 토큰으로 몇 분 뒤 재시도하면 정상 발행됨).
        # 영구적 권한 문제와 구분하기 위해 지수 백오프로 최대 3회 재시도한다.
        last_error = None
        for attempt in range(1, 4):
            resp = requests.post(url, headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}, json=post_payload, timeout=30)
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
        (f'<img src="{thumb_hosted_url}" alt="{html.escape(article["title"], quote=True)}" width="1280" height="720" /><br>' if thumb_hosted_url else "")
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
        subprocess.run(["git", "add", "docs", "keywords_queue.json", "downloads"], check=False, capture_output=True)
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

def _extract_expression_from_title(title: str, strict: bool = False) -> str:
    """제목에서 한국어 표현을 최대한 안전하게 추출한다. 여러 제목 스타일을 순서대로 시도:
    1) 따옴표(홑/쌍) 안 내용의 앞쪽 한글(+공백) 구간 — 로마자 표기나 물음표가 섞여도 앞부분만 추출
       예) '흥', "괜찮아요(Gwaenchanayo)", "바쁘시죠?" 모두 처리
    2) 따옴표 안이 로마자뿐인 경우("Nunchi" 등), 괄호 안 한글 표기를 찾는다: (눈치)
    3) [strict=False일 때만] 그래도 못 찾으면 제목 전체에서 첫 한글 어절을 최후 수단으로 추출.
       [FIX] 이 3번 단계는 "한국어 표현" 글이 아닌 예전 다른 주제 글(다이어트, 여행 등)의 제목에서도
       아무 한글이나 집어 정상 추출된 것처럼 오판하는 원인이었다. repair_old_posts처럼 "이 글이
       애초에 표현 글이 맞는지"를 판별해야 하는 곳에서는 strict=True로 3번 단계를 건너뛴다.
    """
    if not title:
        return ""
    # 1순위: 따옴표 바로 안쪽이 한글로 시작해서 한글로 끝나는 가장 명확한 패턴.
    # [FIX] "Beyond 'If It's Okay': Unpacking '괜찮으시면' in Korean"처럼 영어 축약형의
    # 어퍼스트로피(It's)가 따옴표 쌍 매칭을 앞에서 깨뜨리는 문제가 있었다. 한글 경계를
    # 직접 기준으로 삼으면 이런 축약형은애초에 후보가 되지 않아 안전하게 건너뛴다.
    m = re.search(r'["\']([가-힣][가-힣\s]{0,18})["\']', title)
    if m:
        return m.group(1).strip()
    # 2순위: 따옴표 안에 로마자 표기가 뒤섞인 경우 - 따옴표 쌍 후보를 모은 뒤 앞쪽 한글만 추출
    for cand in re.findall(r'["\']([^"\']{1,40})["\']', title):
        mm = re.match(r'([가-힣][가-힣\s]*)', cand.strip())
        if mm and mm.group(1).strip():
            return mm.group(1).strip()
    m = re.search(r'\(([가-힣][가-힣\s]{0,18})\)', title)
    if m:
        return m.group(1).strip()
    if strict:
        return ""
    m = re.search(r'([가-힣]{1,20})', title)
    return m.group(1).strip() if m else ""


# =====================================================================
# [H.O.L.D. 리페어] 과거 글의 고정 5단 H2 문구 변주 + 문화 단정 완화
# - 매 글마다 다른 소제목이 보이도록 title 시드 기반 결정적 변주 (재실행해도 동일)
# - "한국인은 항상 ~" 류 무출처 단정을 완화된 표현으로 치환
# =====================================================================
_FIXED_H2_VARIANTS: Dict[str, List[str]] = {
    "오늘의 표현": [
        "이 말 한 마디에 담긴 것",
        "오늘 파헤쳐 볼 표현",
        "한 단어로 설명이 안 되는 그 감정",
        "먼저 이 상황부터",
        "이 표현, 어디서 들어보셨나요?",
    ],
    "왜 영어로 직역이 안 될까?": [
        "왜 영어로는 이 맛이 안 날까",
        "가장 가까운 영어 단어의 한계",
        "번역기가 놓치는 뉘앙스",
        "직역하면 어색해지는 이유",
        "비슷한 영어 표현으로는 부족한 점",
    ],
    "한국인은 어떤 상황에서 쓸까?": [
        "실제로는 이럴 때 쓴다",
        "대화 속에서 어떻게 나오는지",
        "한국인이 이 말을 꺼내는 순간",
        "말투와 상황 예시",
        "일상에서 마주치는 장면",
    ],
    "문화 이야기": [
        "이 표현 뒤에 있는 관계의 결",
        "한 가지 배경으로 자주 이야기되는 것",
        "사회·관계와 맞닿는 지점",
        "왜 이 말이 자주 쓰이는지",
        "문화적 맥락을 조금 더 보면",
    ],
    "여러분의 언어에서는 어떤가요?": [
        "당신의 언어에서는?",
        "비슷한 말이 있나요?",
        "한 단어로 뭐라고 부르시나요?",
        "이런 순간, 당신은 뭐라고 말하나요?",
        "한번 떠올려 보세요",
    ],
}


def _pick_variant(seed: str, key: str, options: List[str]) -> str:
    """동일 seed+key면 항상 같은 후보를 고른다 (리페어 재실행 시 소제목이 계속 바뀌지 않게)."""
    h = int(hashlib.md5(f"{seed}::{key}".encode("utf-8")).hexdigest(), 16)
    return options[h % len(options)]


def _vary_fixed_h2_titles(html: str, seed: str) -> str:
    """과거 글의 고정 5단 H2를 시드 기반 변주 문구로 교체한다. 이미 변주된 글은 그대로 둔다."""
    if not html:
        return html
    out = html
    for fixed, options in _FIXED_H2_VARIANTS.items():
        # <h2>고정문구</h2> 또는 인라인 스타일이 붙은 h2 안 텍스트
        pattern = re.compile(
            r'(<h2\b[^>]*>)\s*' + re.escape(fixed) + r'\s*(</h2>)',
            flags=re.IGNORECASE,
        )
        if pattern.search(out):
            variant = _pick_variant(seed, fixed, options)
            out = pattern.sub(rf'\1{variant}\2', out)
    return out


def _soften_culture_claims(html: str) -> str:
    """문화 섹션 등에서 흔히 나오는 무출처 절대 단정을 완화된 표현으로 치환한다."""
    if not html:
        return html
    replacements = [
        (r'한국인은 항상', '많은 한국인은 종종'),
        (r'한국인들은 항상', '많은 한국인들은 종종'),
        (r'모든 한국인은', '많은 한국인은'),
        (r'모든 한국인들은', '많은 한국인들은'),
        (r'한국 문화에서는 반드시', '한국 문화에서 흔히'),
        (r'한국 문화에서는', '한국 문화에서 흔히'),
        (r'한국 사회에서는 반드시', '한국 사회에서 흔히'),
        (r'한국 사회에서는', '한국 사회에서 흔히'),
        (r'반드시 그렇게 한다', '그렇게 하는 경우가 많다'),
        (r'절대적으로', '비교적'),
        (r'예외 없이', '대체로'),
        (r'언제나 그렇다', '그런 경우가 많다'),
    ]
    out = html
    for pat, repl in replacements:
        out = re.sub(pat, repl, out)
    return out


def _apply_hold_content_repair(html: str, seed: str) -> str:
    """H.O.L.D. 리페어 파이프라인: H2 변주 → 문화 단정 완화."""
    html = _vary_fixed_h2_titles(html, seed)
    html = _soften_culture_claims(html)
    return html


# =====================================================================

# =====================================================================
# [SEO 리페어] 기존 글 제목을 Meaning / What Does 패턴으로 일괄 리라이트
# =====================================================================
_SEO_TITLE_PATTERNS = [
    '"{expr}" Meaning in Korean: What Does It Really Mean?',
    'What Does "{expr}" Mean? Korean Expression Explained',
    '"{expr}" Meaning: What Koreans Actually Mean',
    'Why "{expr}" Has No Direct English Translation',
    '"{expr}" Meaning in Korean — Usage & Cultural Nuance',
]


def _title_already_seo(title: str) -> bool:
    t = (title or "").lower()
    keys = ("meaning", "what does", "no direct english translation", "korean expression explained")
    return any(k in t for k in keys)


def _seo_rewrite_title(old_title: str, expression: str = "") -> str:
    """표현을 추출해 SEO 제목 패턴 중 하나로 결정적 변환. 이미 SEO형이면 유지."""
    expr = (expression or "").strip() or _extract_expression_from_title(old_title, strict=False)
    if not expr:
        return old_title
    if _title_already_seo(old_title) and expr in (old_title or ""):
        return old_title
    # 표현이 제목에 없고 SEO형이면 표현만 보강하지 않고 패턴 재작성
    h = int(hashlib.md5(expr.encode("utf-8")).hexdigest(), 16)
    pattern = _SEO_TITLE_PATTERNS[h % len(_SEO_TITLE_PATTERNS)]
    new_title = pattern.format(expr=expr)
    # 과도하게 긴 제목 방지
    if len(new_title) > 90:
        new_title = f'What Does "{expr}" Mean? Korean Expression Explained'
    return new_title


def _rewrite_title_in_html(html_body: str, old_title: str, new_title: str) -> str:
    """본문 안에 옛 제목이 노출된 경우(관련글 등 제외) 최소한의 치환."""
    if not html_body or not old_title or old_title == new_title:
        return html_body
    # og/title 태그는 Blogger가 제목 필드로 관리하므로 content 본문만 안전 치환
    return html_body.replace(old_title, new_title)


# [NEW + H.O.L.D.] 이전 글 자동 복구
# - expression 누락으로 텍스트/발음버튼이 빠진 과거 글 일괄 수정
# - 고정 5단 H2 문구를 글마다 다른 변주 소제목으로 교체 (AdSense 패턴 리스크 완화)
# - 문화 섹션 무출처 단정 표현 완화
# - 기존 글 제목을 Meaning / What Does SEO 패턴으로 일괄 리라이트
# GitHub Pages(로컬 파일)는 확실하게 복구하고, Blogger는 제목 매칭 + 고아 글 H.O.L.D. 본문 패치까지 수행한다.
# 실행: python generate_post.py repair
# =====================================================================
def repair_old_posts() -> None:
    if not os.path.exists(POSTS_JSON):
        logger.info("[복구] posts.json이 없어 복구할 글이 없습니다.")
        return
    with open(POSTS_JSON, "r", encoding="utf-8") as f:
        posts = json.load(f)
    logger.info(f"[복구] 총 {len(posts)}개 글 중 대상 선별을 시작합니다...")

    # [NEW] Blogger 단독 발행으로 전환하면서, GitHub Pages에 남아있던 공개 산출물(개별 글
    # HTML·홈페이지·sitemap·robots)을 정리한다. 이미지(docs/thumbs)와 posts.json(내부 상태),
    # dashboard.html(비공개 관리용)은 그대로 둔다.
    if not PUBLISH_GITHUB_PAGES_SITE:
        removed_public_files = 0
        if os.path.isdir(POSTS_DIR):
            for fname in os.listdir(POSTS_DIR):
                try:
                    os.remove(os.path.join(POSTS_DIR, fname))
                    removed_public_files += 1
                except Exception as e:
                    logger.warning(f"[복구] 공개 글 페이지 삭제 실패({fname}): {e}")
        for fname in ("index.html", "sitemap.xml", "robots.txt"):
            fpath = os.path.join(DOCS_DIR, fname)
            if os.path.exists(fpath):
                try:
                    os.remove(fpath)
                    removed_public_files += 1
                except Exception as e:
                    logger.warning(f"[복구] {fname} 삭제 실패: {e}")
        logger.info(f"[복구] GitHub Pages 공개 산출물 정리 완료 — {removed_public_files}개 파일 삭제 (이미지·posts.json·대시보드는 유지)")

    fixed_thumbs = 0
    fixed_card_news = 0
    fixed_buttons = 0
    deleted_other_niche = 0
    skipped_no_expression = 0
    kept_posts = []
    for p in posts:
        title = p.get("title", "")
        category = p.get("category", "번역감정")
        # [FIX→개편] 예전(재테크/여행 등 다른 주제) 블로그 시절 글은 현재 4개 카테고리
        # (번역감정/일상표현/한국문화/리액션)에 속하지 않으므로 "표현" 개념 자체가 없다.
        # 더 이상 건너뛰기만 하지 않고, 실제로 삭제한다 (본문 HTML/썸네일 파일 + posts.json 항목).
        if category not in CATEGORY_THEMES:
            deleted_other_niche += 1
            for rel_path in (p.get("file"), p.get("thumb")):
                if not rel_path:
                    continue
                full_path = os.path.join(DOCS_DIR, rel_path)
                try:
                    if os.path.exists(full_path):
                        os.remove(full_path)
                except Exception as e:
                    logger.warning(f"[복구] 다른 주제 글 파일 삭제 실패({rel_path}): {e}")
            continue
        kept_posts.append(p)

        theme = get_theme(category)
        expression = _extract_expression_from_title(title, strict=True)
        if not expression:
            # strict 실패 시 느슨 추출로 SEO 제목만이라도 시도
            expression = _extract_expression_from_title(title, strict=False)
        if not expression:
            skipped_no_expression += 1
            logger.warning(f"[복구] 제목에서 표현을 추출하지 못해 건너뜁니다: {title}")
            continue

        # 0) SEO 제목 리라이트 (posts.json)
        new_title = _seo_rewrite_title(title, expression)
        if new_title != title:
            p["title"] = new_title
            title = new_title
            logger.info(f"[복구][SEO 제목] {expression} → {new_title}")

        # 1) 썸네일 재생성 — 항상 JPEG로 저장하고 posts.json 경로를 .jpg로 통일
        old_thumb_rel = (p.get("thumb") or "").strip()
        base_name = os.path.splitext(os.path.basename(old_thumb_rel) or "thumb")[0]
        if not base_name or base_name == "thumb":
            base_name = slugify(expression or title)[:40] or "thumb"
        new_thumb_rel = f"thumbs/{base_name}.jpg"
        thumb_path = os.path.join(DOCS_DIR, new_thumb_rel)
        os.makedirs(os.path.dirname(thumb_path), exist_ok=True)
        try:
            generate_thumbnail(title, thumb_path, theme, category, "", expression)
            if not os.path.isfile(thumb_path):
                # 생성기가 다른 확장자로 쓴 경우 흡수
                for ext in (".jpg", ".jpeg", ".png", ".webp"):
                    alt = os.path.join(DOCS_DIR, "thumbs", base_name + ext)
                    if os.path.isfile(alt):
                        if ext != ".jpg":
                            Image.open(alt).convert("RGB").save(thumb_path, format="JPEG", quality=88)
                        break
            if os.path.isfile(thumb_path):
                p["thumb"] = new_thumb_rel
                fixed_thumbs += 1
                logger.info(f"[복구] 썸네일 재생성: {new_thumb_rel}")
            else:
                logger.warning(f"[복구] 썸네일 파일이 생성되지 않음: {title}")
        except Exception as e:
            logger.warning(f"[복구] 썸네일 재생성 실패({title}): {e}")

        # 1-b) 이전 글 인스타툰 없으면 자동 생성
        try:
            slug_cn = _instatoon_slug(expression, title)
            need_card = True
            for base in (INSTATOON_DOWNLOAD_DIR, INSTATOON_PUBLIC_DIR):
                folder = os.path.join(base, slug_cn)
                if os.path.isdir(folder):
                    try:
                        if any(fn.lower().endswith(".png") for fn in os.listdir(folder)):
                            need_card = False
                            break
                    except Exception:
                        pass
            if need_card:
                article_stub = {
                    "title": title,
                    "expression": expression,
                    "category": category,
                    "meta_description": (p.get("meta_description") or title),
                    "html_body": "",
                }
                generate_instatoon_images(article_stub, (p.get("blogger_url") or "").strip())
                fixed_card_news += 1
                logger.info(f"[복구] 인스타툰 생성: {slug_cn}")
        except Exception as e:
            logger.warning(f"[복구] 인스타툰 생성 실패({title}): {e}")

        # 2) 본문 HTML의 히어로 영역에 발음 듣기 버튼이 없거나 낡은 형태면 최신 버튼으로 교체
        post_path = os.path.join(DOCS_DIR, p["file"])
        if os.path.exists(post_path):
            try:
                with open(post_path, "r", encoding="utf-8") as f:
                    html = f.read()
                original_html = html
                # [H.O.L.D. 리페어] 고정 5단 H2 변주 + 문화 단정 완화
                html = _apply_hold_content_repair(html, title or p.get("file", ""))
                btn_html = _tts_buttons_html(expression, theme)
                # [FIX] 단순 "playKoreanTTS 문자열 포함 여부"만 보면, 과거 다른 방식(이미지 위
                # 오버레이 등)으로 들어간 낡은/깨진 버튼도 "이미 있음"으로 오판해 방치하게 된다.
                # 지금 코드가 만드는 정확한 마크업이 그대로 있을 때만 "이미 있음"으로 인정한다.
                if btn_html and btn_html in html:
                    pass
                else:
                    cleaned = re.sub(r'<button\b[^>]*playKoreanTTS.*?</button>', '', html, flags=re.DOTALL)
                    # [FIX] id="heroThumb" 속성은 비교적 최근에 추가된 것이라, 그 이전에
                    # 발행된 글들은 이 정규식에 하나도 안 걸려 "0개 패치"로 조용히 건너뛰어졌다.
                    # <div class="hero"> 블록 전체(이미지 태그 형태와 무관하게)를 기준으로 넓힌다.
                    new_html = re.sub(
                        r'(<div class="hero">.*?<img[^>]*>)(\s*</div>)',
                        lambda m: m.group(1) + btn_html + m.group(2),
                        cleaned, count=1, flags=re.DOTALL,
                    )
                    if new_html != cleaned:
                        html = new_html
                        fixed_buttons += 1
                    elif btn_html and btn_html not in html:
                        logger.warning(f"[복구] 히어로 이미지 패턴을 찾지 못해 발음버튼을 못 넣었습니다: {title}")
                if html != original_html:
                    with open(post_path, "w", encoding="utf-8") as f:
                        f.write(html)
            except Exception as e:
                logger.warning(f"[복구] 본문/발음버튼 패치 실패({title}): {e}")

    # [NEW] 다른 주제 글을 실제로 삭제했으므로, posts.json을 남은 글(kept_posts) 기준으로 다시 쓴다.
    # index.html/sitemap은 GitHub Pages를 공개 사이트로 발행할 때만 재생성한다 (지금은 Blogger 단독 발행).
    with open(POSTS_JSON, "w", encoding="utf-8") as f:
        json.dump(kept_posts, f, ensure_ascii=False, indent=2)
    if PUBLISH_GITHUB_PAGES_SITE:
        render_index_html(kept_posts)
        update_seo_files(kept_posts)

    logger.info(
        f"[복구] GitHub Pages 완료 — 썸네일 {fixed_thumbs}개, 인스타툰 {fixed_card_news}개, 발음버튼 {fixed_buttons}개 패치, "
        f"다른 주제 글 {deleted_other_niche}개 삭제 (표현 추출 실패 {skipped_no_expression}개는 그대로 둠)"
    )

    # 3) Blogger는 제목 매칭으로 최선을 다해 복구 (실패해도 전체 복구는 계속 진행)
    if _blogger_configured():
        try:
            access_token = _get_blogger_access_token()
            repair_blog_url = _get_blogger_blog_url(access_token)
            repair_page_urls: Dict[str, str] = {}
            try:
                pg = requests.get(
                    f"https://www.googleapis.com/blogger/v3/blogs/{BLOGGER_BLOG_ID}/pages/",
                    headers={"Authorization": f"Bearer {access_token}"},
                    params={"fetchBodies": "false", "maxResults": 50},
                    timeout=20,
                )
                if pg.ok:
                    for item in pg.json().get("items") or []:
                        t = (item.get("title") or "").strip()
                        if t in ("About", "Privacy Policy", "Contact") and item.get("url"):
                            repair_page_urls[t] = item["url"]
            except Exception:
                pass
            repair_page_urls = _merge_policy_page_urls(repair_page_urls)
            resp = requests.get(
                f"https://www.googleapis.com/blogger/v3/blogs/{BLOGGER_BLOG_ID}/posts/",
                headers={"Authorization": f"Bearer {access_token}"},
                params={"maxResults": 500, "fetchBodies": "true"},
                timeout=30,
            )
            resp.raise_for_status()
            blogger_posts = resp.json().get("items", [])
            # [FIX] Blogger가 제목의 따옴표를 스마트 따옴표(" " / ' ')로 자동 변환하거나
            # 앞뒤 공백을 바꾸는 경우가 있어, 완전히 동일한 문자열이어야 매칭되는 dict 방식은
            # 계속 0건으로 실패했을 가능성이 높다. 양쪽 다 정규화(따옴표 통일+공백 제거) 후 비교한다.
            def _normalize_title(t: str) -> str:
                t = (t or "").strip()
                for a, b in [("\u201c", '"'), ("\u201d", '"'), ("\u2018", "'"), ("\u2019", "'")]:
                    t = t.replace(a, b)
                return t

            local_titles = {_normalize_title(p.get("title", "")): p for p in kept_posts}
            logger.info(f"[복구] Blogger에서 글 {len(blogger_posts)}개 조회됨, 로컬 글 {len(local_titles)}개와 제목 매칭 시도")

            # bp["url"]로 blogger_url 매핑을 먼저 전부 만들어둔다 (관련글 링크 교체에 사용)
            blogger_url_by_title = {_normalize_title(bp.get("title", "")): bp.get("url", "") for bp in blogger_posts}

            blogger_fixed = 0
            matched = 0
            already_up_to_date = 0
            no_expression = 0
            no_img_tag = 0
            stale_button_replaced = 0
            related_link_fixed = 0
            blogger_url_bootstrapped = 0
            hold_content_fixed = 0
            orphan_hold_fixed = 0
            seo_title_fixed = 0
            for bp in blogger_posts:
                norm_title = _normalize_title(bp.get("title", ""))
                local = local_titles.get(norm_title)
                content = bp.get("content", "") or ""
                new_content = content
                bp_title = bp.get("title", "") or ""
                # [SEO] 제목 리라이트 (표현 추출 가능 시)
                expr_seo = _extract_expression_from_title(bp_title, strict=True) or _extract_expression_from_title(bp_title, strict=False)
                new_bp_title = _seo_rewrite_title(bp_title, expr_seo) if expr_seo else bp_title
                if new_bp_title != bp_title:
                    seo_title_fixed += 1
                    new_content = _rewrite_title_in_html(new_content, bp_title, new_bp_title)

                # [H.O.L.D. 리페어] posts.json 매칭 여부와 무관하게, 고정 5단 H2·문화 단정이 있으면 본문 변주
                repaired = _apply_hold_content_repair(new_content, bp_title or bp.get("id", ""))
                if repaired != new_content:
                    new_content = repaired
                    if local:
                        hold_content_fixed += 1
                    else:
                        orphan_hold_fixed += 1

                # [레이아웃] 잘못된 /p/ 링크 포함 기존 내비를 올바른 Secrets/기본 URL로 강제 교체
                expr_for_box = ""
                if local:
                    expr_for_box = _extract_expression_from_title(bp_title, strict=True) or ""
                else:
                    expr_for_box = _extract_expression_from_title(bp_title, strict=True) or ""
                before_chrome = new_content
                new_content = _replace_policy_chrome(
                    new_content, repair_blog_url, repair_page_urls, expression=expr_for_box
                )
                if new_content != before_chrome:
                    pass
                # [FIX] 리페어 시 이전 글 썸네일(JPEG) 복구 — Blogger 본문 히어로 교체
                if local:
                    rel = (local.get("thumb") or "").strip()
                    local_thumb = os.path.join(DOCS_DIR, rel) if rel else ""
                    pub = f"{SITE_URL.rstrip('/')}/{rel}" if (SITE_URL and rel) else ""
                    if local_thumb and os.path.isfile(local_thumb):
                        before_img = new_content
                        new_content = _repair_blogger_hero_image(
                            new_content, local_thumb, new_bp_title or bp_title, pub
                        )
                        if new_content != before_img:
                            logger.info(f"[복구] Blogger 썸네일 복구: {rel}")

                if not local:
                    # 매칭 안 되는 글도 H.O.L.D. 본문만 고친 뒤 필요 시 업데이트
                    if new_content != content:
                        upd = requests.put(
                            f"https://www.googleapis.com/blogger/v3/blogs/{BLOGGER_BLOG_ID}/posts/{bp['id']}",
                            headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
                            json={"title": new_bp_title, "content": new_content},
                            timeout=30,
                        )
                        if upd.ok:
                            blogger_fixed += 1
                            if new_bp_title != bp_title:
                                logger.info(f"[복구][SEO 제목] {bp_title} → {new_bp_title}")
                        else:
                            logger.warning(f"[복구] Blogger 고아 글 패치 실패({bp_title}): HTTP {upd.status_code}")
                    continue

                matched += 1

                # [NEW] posts.json에 이 글의 실제 Blogger 주소를 채워 넣는다 (다음 글들의
                # "관련 글" 링크가 이 글을 추천할 때 쓸 수 있도록 — 없으면 매번 후보에서 빠진다)
                bp_url = bp.get("url", "")
                if bp_url and local.get("blogger_url") != bp_url:
                    local["blogger_url"] = bp_url
                    blogger_url_bootstrapped += 1

                expression = _extract_expression_from_title(bp_title, strict=True)
                if not expression:
                    no_expression += 1
                    logger.warning(f"[복구] Blogger 글 표현 추출 실패(본문 H.O.L.D. 패치는 계속): {bp_title}")
                    btn_html = ""
                else:
                    theme = get_theme(local.get("category", "번역감정"))
                    btn_html = _tts_buttons_html(expression, theme)

                # 1) 발음 버튼 정규화: 낡거나 깨진 버튼 흔적은 지우고 최신 버튼으로 다시 넣는다
                if btn_html and not (btn_html in new_content):
                    cleaned = re.sub(r'<button\b[^>]*playKoreanTTS.*?</button>', '', new_content, flags=re.DOTALL)
                    if cleaned != new_content:
                        stale_button_replaced += 1
                    with_btn = re.sub(r'(<img [^>]*>)', lambda m: m.group(1) + btn_html, cleaned, count=1)
                    if with_btn == cleaned:
                        no_img_tag += 1
                        logger.warning(f"[복구] Blogger 글에서 <img> 태그를 못 찾아 버튼을 못 넣었습니다: {bp_title}")
                    else:
                        new_content = with_btn

                # 2) [NEW] "이 글도 함께 보면 좋아요" 관련 글 링크가 (더 이상 없는) GitHub Pages
                # 주소를 가리키고 있으면, 같은 글의 실제 Blogger 주소로 교체한다.
                def _fix_related_link(m):
                    old_href = m.group(1)
                    if "github.io" not in old_href:
                        return m.group(0)
                    link_text = m.group(2)
                    replacement_url = blogger_url_by_title.get(_normalize_title(link_text), "")
                    if not replacement_url:
                        return ""  # 대응하는 Blogger 글을 못 찾으면 죽은 링크를 남기느니 통째로 제거
                    return m.group(0).replace(old_href, replacement_url)

                relinked = re.sub(
                    r'🔗 이 글도 함께 보면 좋아요: <a href="([^"]*)">([^<]*)</a>',
                    _fix_related_link, new_content,
                )
                if relinked != new_content:
                    related_link_fixed += 1
                    new_content = relinked

                # 제목만 SEO로 바뀌고 본문이 동일해도 업데이트
                if new_content == content and new_bp_title == bp_title:
                    already_up_to_date += 1
                    continue
                upd = requests.put(
                    f"https://www.googleapis.com/blogger/v3/blogs/{BLOGGER_BLOG_ID}/posts/{bp['id']}",
                    headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
                    json={"title": new_bp_title, "content": new_content},
                    timeout=30,
                )
                if upd.ok:
                    blogger_fixed += 1
                    if new_bp_title != bp_title:
                        logger.info(f"[복구][SEO 제목] {bp_title} → {new_bp_title}")
                    if local and new_bp_title != bp_title:
                        local["title"] = new_bp_title
                else:
                    logger.warning(f"[복구] Blogger 글 패치 실패({bp_title}): HTTP {upd.status_code}")

            # [FIX] About/Privacy/Contact 글 자체 푸터에 남아 있는 /p/ 링크를 Secrets URL로 강제 교정
            policy_titles = {
                "about": "About",
                "privacy policy": "Privacy Policy",
                "privacy": "Privacy Policy",
                "contact": "Contact",
            }
            for bp in blogger_posts:
                raw_t = (bp.get("title") or "").strip()
                key = policy_titles.get(raw_t.lower())
                if not key:
                    continue
                content = bp.get("content", "") or ""
                fixed = _replace_policy_chrome(content, repair_blog_url, repair_page_urls, expression="")
                # 정책 글에는 reader-value(표현 학습 박스)가 어색할 수 있어 제거
                fixed = re.sub(
                    r'<div\b[^>]*class="[^"]*reader-value[^"]*"[^>]*>.*?</div>',
                    '',
                    fixed,
                    flags=re.DOTALL | re.IGNORECASE,
                )
                if fixed == content:
                    continue
                upd = requests.put(
                    f"https://www.googleapis.com/blogger/v3/blogs/{BLOGGER_BLOG_ID}/posts/{bp['id']}",
                    headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
                    json={"title": bp["title"], "content": fixed},
                    timeout=30,
                )
                if upd.ok:
                    blogger_fixed += 1
                    logger.info(f"[복구] 정책 글 링크 교정: {raw_t}")
                else:
                    logger.warning(f"[복구] 정책 글 교정 실패({raw_t}): HTTP {upd.status_code}")

            # [NEW] blogger_url이 채워진 kept_posts를 posts.json에 다시 저장 (반드시 여기서 저장해야
            # add_internal_link가 다음 글부터 이 Blogger 주소들을 관련 글 후보로 쓸 수 있다)
            with open(POSTS_JSON, "w", encoding="utf-8") as f:
                json.dump(kept_posts, f, ensure_ascii=False, indent=2)

            logger.info(
                f"[복구] Blogger 완료 — 매칭 {matched}개 중 {blogger_fixed}개 패치 "
                f"(SEO 제목 {seo_title_fixed}개, H.O.L.D. 본문 {hold_content_fixed}개, 고아글 H.O.L.D. {orphan_hold_fixed}개, "
                f"낡은 버튼 교체 {stale_button_replaced}개, 관련글 링크 교체 {related_link_fixed}개, "
                f"blogger_url 채움 {blogger_url_bootstrapped}개, 이미 최신 {already_up_to_date}개, "
                f"표현 추출 실패 {no_expression}개, img 태그 없음 {no_img_tag}개)"
            )
        except Exception as e:
            logger.warning(f"[복구] Blogger 복구 중 오류(건너뜀): {e}")
    else:
        logger.info("[복구] Blogger 미설정으로 Blogger 복구는 건너뜁니다.")

    commit_and_push_changes()
    logger.info("[복구] 전체 완료, 변경사항 push 완료")

def run() -> None:
    is_repair_only = len(sys.argv) > 1 and sys.argv[1].strip().lower() == "repair"
    if is_repair_only:
        repair_old_posts()
        return

    is_refresh_only = len(sys.argv) > 1 and sys.argv[1].strip().lower() == "refresh"

    # [개편] 트렌드 감지 대신 에버그린 주제뱅크에서 큐를 보충
    refill_evergreen_queue()
    if is_refresh_only:
        return

    # 수동 제목 입력 여부 확인
    manual_title = ""
    if len(sys.argv) > 1 and sys.argv[1].strip() and sys.argv[1].strip().lower() not in ["publish", "refresh", "repair"]:
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

    # [AdSense] 하루 1회: 과거 글 고정 템플릿·단정 표현 자동 리페어
    # (repair 전용 실행이 아닐 때만 — is_repair_only 분기는 위에서 이미 return)
    _maybe_auto_repair_once()

    ensure_nojekyll()
    ensure_brand_assets()
    ensure_pwa_assets()  # [NEW] PWA 매니페스트/아이콘/서비스워커
    generate_static_pages()
    ensure_blogger_policy_pages()  # AdSense: About/Privacy/Contact + 내비 문구 동기화

    try:
        article = generate_article(title)
    except Exception as e:
        logger.error(f"[Gemini] 글 생성 실패 → 로컬 폴백 사용: {e}")
        article = _fallback_article_local(title)
    article = fix_character_count_claims(article)  # [NEW] AI의 글자 수 오기재를 Python이 강제 교정
    ok, reason = validate_article_quality(article)
    if not ok:
        logger.warning(f"[품질] 1차 생성 미달({reason}) — 1회 재생성 시도")
        try:
            article = generate_article(title)
            article = fix_character_count_claims(article)
        except Exception as e2:
            logger.warning(f"[품질] 재생성 불가({e2}) — 폴백/기존 본문으로 발행 계속")
            if not article.get("html_body"):
                article = _fallback_article_local(title)
        ok2, reason2 = validate_article_quality(article)
        if not ok2:
            logger.warning(f"[품질] 재생성 후에도 미달({reason2}) — 발행은 계속하되 로그에 남김")
        else:
            logger.info("[품질] 재생성 후 기준 통과")
    logger.info(f"글 생성 완료: {article['title']}")

    article = add_internal_link(article)
    article = insert_manual_ads(article)  # ADSENSE_REVIEW_MODE=true면 내부에서 no-op
    article = add_coupang_markup(article)  # 심사 모드면 no-op
    article = add_ymyl_disclaimer(article)
    article = add_editorial_footer(article)  # 학습 목적·편집 고지 (AdSense 신뢰)

    post_meta, json_ld, thumb_url, local_thumb_path, post_url = save_post(article)
    posts = update_index(post_meta)

    update_dashboard(posts)
    if PUBLISH_GITHUB_PAGES_SITE:
        update_seo_files(posts)
    build_lead_magnet_pdf(posts)  # [NEW] 무료 PDF 리드마그넷 자동 갱신

    # [인스타툰] Blogger/SNS 전 5컷 생성 → downloads/instatoon + docs/instatoon
    try:
        card_meta = generate_instatoon_images(article, blogger_url="")
        article["_card_news"] = card_meta
        logger.info(f"[인스타툰] 사전 생성 완료: {card_meta.get('download_dir')}")
    except Exception as e:
        logger.warning(f"[인스타툰] 사전 생성 실패: {e}")
        article["_card_news"] = {}

    commit_and_push_changes()  # [NEW] 외부 발행 전 GitHub Pages에 이미지가 실제로 존재하도록 먼저 push

    blogger_url = publish_to_blogger(article, post_url, thumb_url, local_thumb_path)
    if blogger_url:
        # [NEW] 이 글의 실제 Blogger 주소를 posts.json에 저장해, 다음 글들의 "관련 글" 링크가
        # 이 글을 가리킬 때 (더 이상 없는) GitHub Pages 주소가 아닌 이 주소를 쓰게 한다.
        update_post_blogger_url(post_meta["file"], blogger_url)
    # [FIX] 구글 블로그(Blogger)만 메인으로 발행한다. 워드프레스는 더 이상 병행 발행하지 않는다.

    # [NEW] 발행 직후 Google에 색인 생성을 자동으로 요청한다 (Search Console에서 손으로 누르던 작업 자동화)
    if blogger_url:
        request_google_indexing(blogger_url)  # Blogger가 메인 발행처이므로 이 주소만 색인 요청
        # [NEW] Threads + Instagram 자동 공유 (토큰 없으면 내부에서 스킵)
        # 한 컷에 블로그 URL 반영 후 SNS (클릭 전환용)
        try:
            article["_card_news"] = generate_instatoon_images(article, blogger_url)
            commit_and_push_changes()
        except Exception as _e:
            logger.warning(f"[인스타툰] 발행 URL 반영 재생성 실패: {_e}")
        publish_to_sns(article, blogger_url, thumb_url)

    if not manual_title and not is_manual_trigger:
        increment_daily_count()

    logger.info(f"저장 완료: docs/{post_meta['file']}, docs/{post_meta['thumb']}")


if __name__ == "__main__":
    try:
        run()
    except Exception as e:
        logger.error(f"스크립트 실행 중 치명적인 오류 발생: {e}")
        sys.exit(1)
