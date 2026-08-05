# -*- coding: utf-8 -*-
"""
GitHub Actions 위에서 실행되는 자동 블로그 파이프라인 스크립트 (통합판)
- [스토리텔링 강화] 호기심 천국, 세상에 이런 일이 스타일의 흥미진진한 트렌드 원인 분석형 프롬프트 적용
- [업그레이드] 조회수 10000회(1만) 이상 핫이슈만 감지 시 발행 (일일 발행 횟수 상한 없음)
- [업그레이드] 방문자 언어 감지 자동 번역 (버튼 숨김) 및 표 1.5배 확대 기능
- [수정] 원본 코드 구조 유지 및 마크다운 Table 렌더링 깨짐 현상 완벽 수정
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
import xml.etree.ElementTree as ET
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
# 구글 트렌드 관련 설정 (조회수 파싱을 위해 daily RSS만 사용)
# =====================================================================
TRENDS_RSS_URL = "https://trends.google.com/trending/rss?geo=KR"
REQUEST_TIMEOUT = 15
QUEUE_FILE = "keywords_queue.json"

# =====================================================================
# 환경변수로 받는 설정값
# =====================================================================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
SITE_TITLE = os.environ.get("SITE_TITLE", "내 자동 블로그")
SITE_TAGLINE = os.environ.get("SITE_TAGLINE", "매일 자동으로 업데이트되는 정보 큐레이션 블로그")
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

# --- 워드프레스 자동 발행 관련 환경변수 ---
WORDPRESS_URL = os.environ.get("WORDPRESS_URL", "").rstrip("/")
WORDPRESS_USERNAME = os.environ.get("WORDPRESS_USERNAME", "")
WORDPRESS_APP_PASSWORD = os.environ.get("WORDPRESS_APP_PASSWORD", "")
WORDPRESS_CLIENT_ID = os.environ.get("WORDPRESS_CLIENT_ID", "")
WORDPRESS_CLIENT_SECRET = os.environ.get("WORDPRESS_CLIENT_SECRET", "")

FONT_CANDIDATES = [
    "font.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothic-Bold.ttf",
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

# 프롬프트를 흥미진진한 스토리텔러 톤으로 전면 개편 (표 오류 수정 포함)
SYSTEM_PROMPT = """당신은 사람들의 호기심을 강하게 자극하는 미스터리/정보 큐레이션 전문 스토리텔러이자 한국어 SEO 블로그 작가입니다. 
TV 프로그램 '호기심 천국'이나 '순간포착 세상에 이런 일이'의 내레이션처럼 독자의 상상력을 자극하고, 몰랐던 사실을 알아가는 즐거움을 주는 톤으로 작성하되, 사람이 직접 쓴 것처럼 자연스럽고 담백해야 합니다. 광고 카피처럼 과장되거나 기계적으로 반복되는 말투는 피하세요.

아래 규칙을 지켜 작성하세요:
1. 제목은 검색 의도를 반영하되 흥미를 유발하도록 작성한다. 아래 9가지 후킹(hook) 기법 중 이 주제에 가장 잘 맞는 것을 1~2개 골라 제목과 도입부에 녹여낸다:
   ① 호기심 갭 ② 구체성/숫자 ③ 손실회피 ④ 정체성/소속 ⑤ 대조(vs) ⑥ Before-After ⑦ 사회적 증거 ⑧ 의외성 ⑨ 낮은 진입장벽
   (예: "OOO, 대체 왜 난리일까? 숨겨진 진짜 이유") 단, 입력받은 키워드의 의미를 벗어나지 않으며 25~40자 내외로 한다.
1-1. meta_description은 검색결과 스니펫에 노출되는 요약문이다. 핵심 키워드를 앞부분에 배치하고, 호기심 자극 문장으로 100~140자 내외로 작성한다.
2. 소제목(H2)을 4~6개 사용해 구조화한다.
3. [매우 중요] 단순한 사전적 뜻풀이나 정보 나열은 절대 금지합니다. 대신 "왜 지금 이 단어가 검색어 1위로 급상승했을까?", "이 이슈 이면에 숨겨진 진짜 이유는 무엇일까?"에 초점을 맞춰 비하인드 스토리, 에피소드, 놀라운 사실을 파헤쳐주세요.
3-1. [문체/가독성] 다음 AI 특유의 어색한 말투를 피한다:
   - "~일까요?", "~습니다!" 같은 패턴으로만 끝맺지 말고 평서문/의문문/짧은 문장을 자연스럽게 섞는다.
   - 과장 수식어("정말", "충격적인", "발칵")는 글 전체에서 2~3회 이하로 아껴 쓴다.
   - 문단은 2~4문장으로 짧게 끊어 모바일 가독성을 높인다.
3-2. [콘텐츠 품질] 이 글은 시간이 지나도 유효한(에버그린) 정보 가치를 지녀야 합니다. 구체적 정보(배경, 맥락, 숫자, 비교, 실용적 시사점)를 반드시 포함하세요.
4. 글자 수는 1500~2200자 내외.
5. 서론(Hook)은 독자에게 충격적이거나 매우 흥미로운 질문을 던지며 시작합니다. 
6. [★ 매우 중요한 표 작성 규칙 ★] 가독성을 위해 본문 중 최소 1곳에 데이터/스펙/특징 비교용 정리표를 반드시 포함합니다. 
   단, 웹페이지 렌더링 오류 방지를 위해 마크다운 기호(|---|)는 절대 사용하지 마세요! 
   반드시 순수 HTML 태그(<table>, <thead>, <tbody>, <tr>, <th>, <td>)만 사용하여 표를 작성하세요.
7. "product_keyword"에는 이 글 내용과 실제로 관련된, 쿠팡에서 검색했을 때 진짜 상품이 나올 만한 쇼핑 키워드(2~4단어)를 넣는다.
8. 콘텐츠 내용을 보고 스키마 타입(FAQPage, HowTo, Article)을 고른다.
9. 고른 스키마 타입에 맞는 데이터를 함께 채운다.
10. 제목/키워드를 보고 카테고리 중 가장 알맞은 것 하나를 고른다. ["뷰티패션", "푸드맛집", "여행", "테크IT", "재테크머니", "헬스운동", "홈인테리어", "대출보험", "정부지원금", "라이프스타일"]
11. category가 "대출보험" 또는 "정부지원금"이면 일반적인 조건 위주로 설명하고 공식 기관 확인이 필요하다는 점을 덧붙인다.
12. "product_list"에 1문장 설명과 함께 채운다. (최대 6개). 
12-1. "image_keywords"에는 영어 스톡사진 검색어 2~4단어를 넣는다 (밈이나 고유명사는 보편적 장면 묘사로 변환).
13. 출력은 반드시 아래 JSON 형식만 반환한다. 다른 설명, 코드블록 기호(```) 없이 순수 JSON만 출력한다:
{
  "title": "...",
  "html_body": "...",
  "meta_description": "...",
  "schema_type": "Article",
  "faq_items": [],
  "howto_steps": [],
  "category": "라이프스타일",
  "product_keyword": "",
  "product_list": [],
  "image_keywords": "..."
}
html_body는 <h2>, <p>, <table>, <ul> 등을 사용한 HTML 조각이어야 한다."""

CATEGORY_THEMES = {
    "뷰티패션": {"gradient": [(255, 107, 157), (255, 154, 158), (250, 208, 196)], "accent": "#ff6b9d", "badge": "💄 뷰티·패션", "label": "BEAUTY", "font": "Gowun+Dodum", "decor": ["💄", "💅", "👗", "👠", "💋", "🎀", "💎", "🌸"]},
    "푸드맛집": {"gradient": [(255, 107, 53), (247, 147, 30), (255, 210, 63)], "accent": "#ff6b35", "badge": "🍽️ 푸드·맛집", "label": "FOOD", "font": "Jua", "decor": ["🍕", "🍔", "🍰", "🍜", "🍩", "☕", "🍓", "🧁"]},
    "여행": {"gradient": [(17, 153, 142), (56, 239, 125), (100, 210, 255)], "accent": "#11998e", "badge": "✈️ 여행", "label": "TRAVEL", "font": "Gowun+Dodum", "decor": ["✈️", "🌴", "🗺️", "🧳", "🏖️", "📸", "🚗", "🗼"]},
    "테크IT": {"gradient": [(30, 60, 114), (42, 82, 152), (0, 198, 255)], "accent": "#2a5298", "badge": "💻 테크·IT", "label": "TECH", "font": "Noto+Sans+KR:wght@700", "decor": ["💻", "⌨️", "🖥️", "📱", "🔌", "🤖", "⚡", "🛰️"]},
    "재테크머니": {"gradient": [(17, 105, 79), (56, 173, 118), (168, 224, 99)], "accent": "#11694f", "badge": "💰 재테크", "label": "MONEY", "font": "Noto+Sans+KR:wght@700", "decor": ["💰", "💵", "📈", "🪙", "🏦", "💳", "📊", "🐷"]},
    "헬스운동": {"gradient": [(19, 78, 94), (113, 178, 128), (168, 224, 99)], "accent": "#134e5e", "badge": "💪 헬스·운동", "label": "FITNESS", "font": "Jua", "decor": ["💪", "🏋️", "🥗", "🧘", "🏃", "⏱️", "🚴", "🥑"]},
    "홈인테리어": {"gradient": [(196, 132, 88), (218, 170, 122), (238, 210, 175)], "accent": "#c48458", "badge": "🏠 홈·인테리어", "label": "HOME", "font": "Gowun+Dodum", "decor": ["🏠", "🪴", "🕯️", "🛋️", "🖼️", "🧺", "🪞", "🛏️"]},
    "라이프스타일": {"gradient": [(66, 133, 244), (156, 39, 176), (234, 67, 121)], "accent": "#4a90d9", "badge": "✨ 라이프스타일", "label": "LIFESTYLE", "font": "Noto+Sans+KR:wght@700", "decor": ["✨", "🌸", "☕", "📓", "🎧", "🕊️", "🌿", "⭐"]},
    "대출보험": {"gradient": [(20, 30, 48), (36, 59, 85), (65, 90, 119)], "accent": "#1e3a5f", "badge": "🏦 대출·보험", "label": "FINANCE", "font": "Noto+Sans+KR:wght@700", "decor": ["🏦", "📄", "💳", "🔍", "📞", "✅", "💼", "🧾"], "ymyl": True},
    "정부지원금": {"gradient": [(0, 91, 82), (0, 128, 105), (82, 183, 136)], "accent": "#00695c", "badge": "🏛️ 정부지원금", "label": "SUPPORT", "font": "Noto+Sans+KR:wght@700", "decor": ["🏛️", "📋", "🖊️", "📅", "✅", "💌", "🪪", "📢"], "ymyl": True},
}
DEFAULT_THEME = CATEGORY_THEMES["라이프스타일"]

def get_theme(category: str) -> Dict[str, Any]:
    return CATEGORY_THEMES.get(category, DEFAULT_THEME)

PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", "")
STOCK_SEARCH_TERMS = {
    "뷰티패션": "cosmetics makeup fashion",
    "푸드맛집": "food restaurant dish",
    "여행": "travel landscape destination",
    "테크IT": "laptop computer technology",
    "재테크머니": "money finance coins",
    "헬스운동": "fitness workout gym",
    "홈인테리어": "home interior cozy",
    "대출보험": "bank finance document",
    "정부지원금": "government building document",
    "라이프스타일": "lifestyle coffee cozy",
}

# =====================================================================
# 구글 트렌드 큐 관리
# =====================================================================
def fetch_high_traffic_trends(min_traffic: int = 10000) -> List[str]:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    }
    try:
        response = requests.get(TRENDS_RSS_URL, timeout=REQUEST_TIMEOUT, headers=headers)
        response.raise_for_status()
        root = ET.fromstring(response.content)
        ns = {"ht": "[https://trends.google.com/trending/rss](https://trends.google.com/trending/rss)"}
        high_traffic_keywords = []
        
        for item in root.iter("item"):
            title_text = item.findtext("title")
            traffic_text = item.findtext("ht:approx_traffic", namespaces=ns)
            
            if title_text and title_text.strip():
                traffic = 0
                if traffic_text:
                    clean_traffic = re.sub(r"[^\d]", "", traffic_text)
                    if clean_traffic.isdigit():
                        traffic = int(clean_traffic)
                
                if traffic >= min_traffic:
                    high_traffic_keywords.append(title_text.strip())
                    
        return high_traffic_keywords
    except Exception as e:
        logger.warning(f"트렌드 조회수 파싱 실패: {e}")
        return []

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

def fetch_and_update_trends_queue() -> None:
    logger.info("=" * 60)
    logger.info("[구글 트렌드] 조회수 10000(1만) 이상 인기 검색어 수집 시작...")
    trends = fetch_high_traffic_trends(min_traffic=10000)
    
    if not trends:
        logger.info("조건(10000회 이상)을 만족하는 신규 핫이슈 트렌드가 없거나 수집에 실패했습니다.")
        logger.info("=" * 60)
        return

    queue = load_queue()
    existing_keywords = set(queue.get("pending", [])) | set(queue.get("completed", []))
    new_keywords = [t for t in trends if t not in existing_keywords]
    skipped_count = len(trends) - len(new_keywords)

    queue["pending"].extend(new_keywords)
    save_queue(queue)

    logger.info(f"[처리 완료] 10000회 이상 신규 추가된 키워드: {len(new_keywords)}개 (중복 제외됨: {skipped_count}개)")
    logger.info(f"[현재 상태] 대기 중인 전체 키워드: {len(queue['pending'])}개")
    logger.info("=" * 60)

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
<script async src="[https://www.googletagmanager.com/gtag/js?id=](https://www.googletagmanager.com/gtag/js?id=){GA_MEASUREMENT_ID}"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){{dataLayer.push(arguments);}}
  gtag('js', new Date());
  gtag('config', '{GA_MEASUREMENT_ID}');
</script>"""

ENABLE_AUTO_TRANSLATE = os.environ.get("ENABLE_AUTO_TRANSLATE", "true").strip().lower() != "false"

def _translate_widget() -> str:
    if not ENABLE_AUTO_TRANSLATE: return ""
    return """
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
<script src="//[translate.google.com/translate_a/element.js?cb=googleTranslateElementInit](https://translate.google.com/translate_a/element.js?cb=googleTranslateElementInit)"></script>"""

def _adsense_snippet() -> str:
    if not ADSENSE_CLIENT_ID: return ""
    return f'\n<script async src="[https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=](https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=){ADSENSE_CLIENT_ID}" crossorigin="anonymous"></script>'

def build_faq_section_html(article: Dict[str, Any], accent: str = "#4a90d9") -> str:
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
            "@context": "[https://schema.org](https://schema.org)", "@type": "FAQPage",
            "mainEntity": [{"@type": "Question", "name": qa.get("question", ""), "acceptedAnswer": {"@type": "Answer", "text": qa.get("answer", "")}} for qa in article["faq_items"]],
        }
    elif schema_type == "HowTo" and article.get("howto_steps"):
        data = {
            "@context": "[https://schema.org](https://schema.org)", "@type": "HowTo", "name": title, "description": meta_description,
            "step": [{"@type": "HowToStep", "name": s.get("name", ""), "text": s.get("text", "")} for s in article["howto_steps"]],
        }
    else:
        schema_type = article_type
        data = {
            "@context": "[https://schema.org](https://schema.org)", "@type": article_type, "headline": title, "description": meta_description,
            "image": thumb_url, "datePublished": date, "author": {"@type": "Organization", "name": SITE_TITLE},
        }

    data.pop("@context", None)
    breadcrumb = {
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": SITE_TITLE, "item": (SITE_URL + "/") if SITE_URL else "../index.html"},
            {"@type": "ListItem", "position": 2, "name": article.get("category", "라이프스타일"), "item": (SITE_URL + "/") if SITE_URL else "../index.html"},
            {"@type": "ListItem", "position": 3, "name": title, "item": canonical_url},
        ],
    }
    graph_nodes = [data, breadcrumb]
    return json.dumps({"@context": "[https://schema.org](https://schema.org)", "@graph": graph_nodes}, ensure_ascii=False, indent=2)

def build_blog_index_json_ld(posts: List[Dict[str, Any]]) -> str:
    data = {
        "@context": "[https://schema.org](https://schema.org)", "@type": "Blog", "name": SITE_TITLE, "url": (SITE_URL + "/") if SITE_URL else ".",
        "blogPost": [{"@type": "BlogPosting", "headline": p["title"], "url": (f"{SITE_URL}/{p['file']}" if SITE_URL else p["file"]), "datePublished": p["date"], "image": (f"{SITE_URL}/{p['thumb']}" if SITE_URL else p["thumb"])} for p in posts[:10]],
    }
    return json.dumps(data, ensure_ascii=False, indent=2)

POST_TEMPLATE = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<meta name="description" content="{meta_description}">
<link rel="canonical" href="{canonical_url}">
<link rel="icon" type="image/png" href="../favicon.png">{search_console_meta}
<link rel="preconnect" href="[https://fonts.googleapis.com](https://fonts.googleapis.com)">
<link href="[https://fonts.googleapis.com/css2?family=](https://fonts.googleapis.com/css2?family=){font}&family=Noto+Sans+KR:wght@400;700&display=swap" rel="stylesheet">
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
  
  /* 표 오류 수정 및 가독성을 위한 1.5배 확대 디자인 업데이트 */
  table {{ width: 100%; min-width: 460px; border-collapse: collapse; font-size: 1.25em; margin: 25px 0; background-color: #fff; box-shadow: 0 2px 8px rgba(0,0,0,0.05); }}
  th, td {{ padding: 16px 18px; border: 1px solid #ddd; text-align: left; line-height: 1.6; }}
  th {{ background: {accent}14; font-weight: 800; color: #111; }}
  
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
  @media (min-width: 900px) {{ body {{ max-width: 760px; }} }}
  .translate-widget {{ position: fixed; top: 10px; right: 10px; z-index: 999; font-size: 0.8em; }}
  body {{ top: 0 !important; }}
  .goog-te-banner-frame, .skiptranslate {{ display: none !important; }}
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
    return f"[https://fonts.googleapis.com/css2?family=](https://fonts.googleapis.com/css2?family=){families}&family=Noto+Sans+KR:wght@400;700;900&display=swap"

INDEX_TEMPLATE = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{site_title}</title>
<link rel="icon" type="image/png" href="favicon.png">{search_console_meta}
<link rel="preconnect" href="[https://fonts.googleapis.com](https://fonts.googleapis.com)">
<link href="{fonts_url}" rel="stylesheet">
<script type="application/ld+json">
{blog_json_ld}
</script>{ga_snippet}{adsense_snippet}
<style>
  * {{ box-sizing: border-box; }}
  body {{ max-width: 1000px; margin: 0 auto; padding: 0 0 60px; font-family: 'Noto Sans KR', sans-serif; background:#f5f5f7; color:#1a1a1a; }}
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
  
  .hero {{ display:block; text-decoration:none; color:#1a1a1a; background:#fff; border-radius:20px; overflow:hidden; box-shadow: 0 6px 24px rgba(0,0,0,0.10); }}
  .hero img {{ width:100%; aspect-ratio: 16/9; object-fit:cover; display:block; }}
  .hero-body {{ padding: clamp(16px, 4vw, 22px) clamp(18px, 5vw, 26px) 28px; }}
  .hero-badge {{ display:inline-block; font-size:0.8em; font-weight:700; color:#fff; padding:5px 14px; border-radius:999px; margin-bottom:12px; }}
  .hero-title {{ font-size: clamp(1.25em, 4.5vw, 1.7em); font-weight:800; line-height:1.35; word-break: keep-all; }}

  .mid-grid {{ display:grid; grid-template-columns: 1fr 1fr; gap:18px; }}
  .mid-card {{ text-decoration:none; color:#1a1a1a; background:#fff; border-radius:16px; overflow:hidden; box-shadow: 0 3px 14px rgba(0,0,0,0.08); transition: transform .15s ease; }}
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
  
  @media (max-width: 480px) {{
    .masthead img {{ aspect-ratio: 1600/620; }}
    .mid-grid {{ grid-template-columns: 1fr; gap: 14px; }}
    .bottom-grid {{ grid-template-columns: repeat(2, 1fr); }}
  }}
  @media (min-width: 1000px) {{ .bottom-grid {{ grid-template-columns: repeat(5, 1fr); }} }}
  .goog-te-banner-frame, .skiptranslate {{ display: none !important; }}
  body {{ top: 0 !important; }}
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
  table {{ width: 100%; border-collapse: collapse; font-size: 0.9em; }}
  th, td {{ text-align: left; padding: 8px 4px; border-bottom: 1px solid #eee; }}
  .card {{ background:#f7f7f9; border-radius:8px; padding:16px; margin: 10px 0; }}
  a.back {{ display: inline-block; margin-bottom: 20px; color: #4a90d9; text-decoration: none; }}
</style>
</head>
<body>
<a class="back" href="index.html">← 블로그로</a>
<h1>📊 성과 관리 대시보드</h1>
<h2>발행된 글 목록 ({post_count}개)</h2>
<table><tr><th>날짜</th><th>제목</th><th>바로가기</th></tr>{rows}</table>
</body>
</html>
"""

STATIC_PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{page_title} - {site_title}</title>
<style>
  body {{ max-width: 760px; margin: 40px auto; padding: 0 20px 60px; font-family: 'Noto Sans KR', -apple-system, sans-serif; line-height: 1.75; color: #1a1a1a; }}
  a.back {{ display: inline-block; margin-bottom: 20px; color: #4a90d9; text-decoration: none; font-weight: 700; }}
  h1 {{ font-size: 1.6em; border-bottom: 2px solid #eee; padding-bottom: 10px; }}
</style>
</head>
<body>
<a class="back" href="index.html">← 블로그로</a>
<h1>{page_title}</h1>
{page_body}
</body>
</html>
"""

SITEMAP_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="[http://www.sitemaps.org/schemas/sitemap/0.9](http://www.sitemaps.org/schemas/sitemap/0.9)">
<url><loc>{site_url}/</loc></url>
{url_entries}
</urlset>"""
ROBOTS_TXT = "User-agent: *\nAllow: /\n\nSitemap: {site_url}/sitemap.xml\n"
THUMB_SIZE = (1280, 720)

# =====================================================================
# 유틸리티 (AI 오류 교정, 썸네일 생성 등)
# =====================================================================
def slugify(text: str) -> str:
    text = re.sub(r"[^\w\s-]", "", text).strip()
    return re.sub(r"[\s]+", "-", text) or "post"

KOREAN_COUNT_WORDS = {
    1: "한", 2: "두", 3: "세", 4: "네", 5: "다섯", 6: "여섯", 7: "일곱", 8: "여덟",
    9: "아홉", 10: "열", 11: "열한", 12: "열두", 13: "열세", 14: "열네", 15: "열다섯",
    16: "열여섯", 17: "열일곱", 18: "열여덟", 19: "열아홉", 20: "스무",
}
_COUNT_WORD_PATTERN = re.compile("(" + "|".join(re.escape(w) for w in sorted(KOREAN_COUNT_WORDS.values(), key=len, reverse=True)) + r")\s?(글자|자)\b")

def fix_character_count_claims(article: Dict[str, Any]) -> Dict[str, Any]:
    keyword = article.get("keyword", "")
    correct_len = len(re.sub(r"\s+", "", keyword))
    if correct_len not in KOREAN_COUNT_WORDS: return article
    correct_word = KOREAN_COUNT_WORDS[correct_len]
    def _replace(m: re.Match) -> str: return f"{correct_word} {m.group(2)}"
    for field in ("title", "html_body", "meta_description"):
        if article.get(field): article[field] = _COUNT_WORD_PATTERN.sub(_replace, article[field])
    return article

def generate_article(title: str) -> Dict[str, Any]:
    if not GEMINI_API_KEY: raise RuntimeError("GEMINI_API_KEY 환경변수가 비어있습니다.")
    url = GEMINI_URL.format(api_key=GEMINI_API_KEY)
    payload = {
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"role": "user", "parts": [{"text": f"오늘의 핫이슈/급상승 트렌드 키워드: '{title}'\n이 단어가 왜 검색어 1위에 오르며 화제가 되었는지, 비하인드 스토리나 놀라운 사실은 무엇인지 흥미를 자극하는 전개로 작성해주세요."}]}],
        "generationConfig": {"responseMimeType": "application/json", "maxOutputTokens": 8192},
    }
    
    for attempt in range(1, 4):
        try:
            resp = requests.post(url, json=payload, timeout=60)
            resp.raise_for_status()
            text = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip().removeprefix("```json").removesuffix("```").strip()
            article = json.loads(text)
            article["keyword"] = title
            return article
        except Exception as e:
            logger.warning(f"[Gemini] 응답 실패 혹은 파싱 오류 ({attempt}/3): {e}")
            time.sleep(10)
    raise RuntimeError("Gemini API 콘텐츠 생성에 반복 실패했습니다.")

def _load_font(size: int):
    for path in FONT_CANDIDATES:
        if os.path.exists(path) and os.path.getsize(path) > 0:
            try: return ImageFont.truetype(path, size)
            except Exception: pass
    return ImageFont.load_default()

def _make_gradient_background(size: Tuple[int, int], colors: List[Tuple[int, int, int]]):
    w, h = size
    base, top = Image.new("RGB", size, colors[0]), Image.new("RGB", size, colors[-1])
    mask = Image.new("L", size)
    mask.putdata([int(((x / w + y / h) / 2) * 255) for y in range(h) for x in range(w)])
    blended = Image.composite(top, base, mask)
    mid, mid_mask = Image.new("RGB", size, colors[1]), Image.new("L", size)
    mid_mask.putdata([int(80 * (1 - abs((x / w + y / h) / 2 - 0.5) * 2)) for y in range(h) for x in range(w)])
    return Image.composite(mid, blended, mid_mask)

def _hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    return tuple(int(hex_color.lstrip("#")[i:i+2], 16) for i in (0, 2, 4))

def _fetch_stock_photo(query: str, fallback_query: str, size: Tuple[int, int], seed: int) -> Tuple[Optional[Image.Image], Optional[Dict[str, str]]]:
    if not PEXELS_API_KEY: return None, None
    for attempt_query in [q for q in (query, fallback_query) if q]:
        try:
            resp = requests.get("[https://api.pexels.com/v1/search](https://api.pexels.com/v1/search)", headers={"Authorization": PEXELS_API_KEY}, params={"query": attempt_query, "orientation": "landscape", "per_page": 15}, timeout=15)
            photos = resp.json().get("photos", [])
            if not photos: continue
            photo = photos[seed % len(photos)]
            img_resp = requests.get(photo["src"].get("large2x") or photo["src"]["original"], timeout=20)
            img = Image.open(io.BytesIO(img_resp.content)).convert("RGB")
            
            w, h = img.size
            tr = size[0] / size[1]
            if (w / h) > tr: img = img.crop(((w - int(h * tr)) // 2, 0, (w + int(h * tr)) // 2, h))
            else: img = img.crop((0, (h - int(w / tr)) // 2, w, (h + int(w / tr)) // 2))
            
            return img.resize(size), {"name": photo.get("photographer"), "photo_url": photo.get("url"), "source": "Pexels"}
        except Exception: continue
    return None, None

def generate_thumbnail(title: str, output_path: str, theme: Dict[str, Any], category: str = "라이프스타일", image_keywords: str = "") -> Optional[Dict[str, str]]:
    seed = int(hashlib.md5(title.encode("utf-8")).hexdigest(), 16) % 100000
    photo, credit = _fetch_stock_photo(image_keywords, STOCK_SEARCH_TERMS.get(category, "lifestyle"), THUMB_SIZE, seed)
    img = photo.convert("RGBA") if photo else _make_gradient_background(THUMB_SIZE, theme["gradient"]).convert("RGBA")
    draw = ImageDraw.Draw(img)
    
    label_font, label_text = _load_font(30), theme["label"]
    lb = draw.textbbox((0, 0), label_text, font=label_font)
    draw.rounded_rectangle([24, 24, 24 + (lb[2]-lb[0]) + 36, 24 + (lb[3]-lb[1]) + 16], radius=20, fill=_hex_to_rgb(theme["accent"]) + (230,))
    draw.text((42, 32 - lb[1]), label_text, font=label_font, fill=(255, 255, 255, 255))
    draw.rectangle([(0, THUMB_SIZE[1] - 18), (THUMB_SIZE[0], THUMB_SIZE[1])], fill=_hex_to_rgb(theme["accent"]) + (255,))
    
    img.convert("RGB").save(output_path, format="WEBP", quality=85, method=6)
    return credit

def ensure_brand_assets() -> None:
    os.makedirs(DOCS_DIR, exist_ok=True)
    logo_path = os.path.join(DOCS_DIR, "logo.webp")
    if not os.path.exists(logo_path):
        img = _make_gradient_background((512, 512), [(15, 23, 42), (51, 65, 85)]).convert("RGBA")
        ImageDraw.Draw(img).text((150, 100), SITE_TITLE[:1] or "B", font=_load_font(220), fill=(255, 255, 255, 255))
        img.convert("RGB").save(logo_path, format="WEBP")
        img.resize((64, 64)).save(os.path.join(DOCS_DIR, "favicon.png"), format="PNG")
    banner_path = os.path.join(DOCS_DIR, "banner.webp")
    if not os.path.exists(banner_path):
        _make_gradient_background((1600, 420), [(15, 23, 42), (51, 65, 85)]).save(banner_path, format="WEBP")

# =====================================================================
# 발행(Blogger, WP) 및 저장 로직
# =====================================================================
def add_internal_link(article: Dict[str, Any]) -> Dict[str, Any]:
    if not os.path.exists(POSTS_JSON): return article
    with open(POSTS_JSON, "r", encoding="utf-8") as f: posts = json.load(f)
    if posts:
        pick = random.choice(posts[:5])
        article["html_body"] += f'<p style="margin-top:2em;padding-top:1em;border-top:1px dashed #ddd;">🔗 이 글도 함께 보면 좋아요: <a href="../{pick["file"]}">{pick["title"]}</a></p>'
    return article

def add_ymyl_disclaimer(article: Dict[str, Any]) -> Dict[str, Any]:
    if get_theme(article.get("category", "")).get("ymyl"):
        article["html_body"] += '<div style="background:#fff8e1;padding:14px;margin:24px 0;font-size:0.92em;">⚠️ 본 글은 참고용이며 공식 채널 확인이 필요합니다.</div>'
    return article

def save_post(article: Dict[str, Any]) -> Tuple[Dict[str, Any], str, str, str, str]:
    os.makedirs(POSTS_DIR, exist_ok=True); os.makedirs(os.path.join(DOCS_DIR, "thumbs"), exist_ok=True)
    theme = get_theme(article.get("category", "라이프스타일"))
    slug, today = slugify(article["keyword"]), datetime.now().strftime("%Y-%m-%d")
    thumb_filename, post_filename = f"{slug}-{today}.webp", f"{slug}-{today}.html"
    generate_thumbnail(article["title"], os.path.join(DOCS_DIR, "thumbs", thumb_filename), theme, article.get("category", ""), article.get("image_keywords", ""))
    
    static_html_body = article["html_body"] + build_faq_section_html(article, theme["accent"])
    
    post_url = f"{SITE_URL}/posts/{post_filename}" if SITE_URL else f"posts/{post_filename}"
    thumb_url = f"{SITE_URL}/thumbs/{thumb_filename}" if SITE_URL else f"../thumbs/{thumb_filename}"
    json_ld = build_json_ld(article, post_url, thumb_url, today)
    
    html = POST_TEMPLATE.format(
        title=article["title"], meta_description=article.get("meta_description", ""), date=today,
        html_body=static_html_body, thumb_filename=thumb_filename, canonical_url=post_url, thumb_url=thumb_url,
        json_ld=json_ld, ga_snippet=_ga_snippet(), adsense_snippet=_adsense_snippet(),
        font=theme["font"], font_family=theme["font"].split(":")[0].replace("+", " "),
        accent=theme["accent"], badge=theme["badge"], related_html="", post_nav="",
        decor_html=build_decor_html(theme, seed=slug), bottom_ad="", search_console_meta=_search_console_meta(),
        translate_widget=_translate_widget(), photo_credit_html=""
    )
    with open(os.path.join(POSTS_DIR, post_filename), "w", encoding="utf-8") as f: f.write(html)
    return {"title": article["title"], "file": f"posts/{post_filename}", "thumb": f"thumbs/{thumb_filename}", "date": today}, json_ld, thumb_url, os.path.join(DOCS_DIR, "thumbs", thumb_filename), post_url

def update_index(new_post: Dict[str, Any]) -> List[Dict[str, Any]]:
    posts = []
    if os.path.exists(POSTS_JSON):
        with open(POSTS_JSON, "r", encoding="utf-8") as f: posts = json.load(f)
    posts.insert(0, new_post)
    with open(POSTS_JSON, "w", encoding="utf-8") as f: json.dump(posts, f, ensure_ascii=False, indent=2)
    return posts

def strip_interactive_widgets(html_body: str) -> str:
    html_body = re.sub(r'<div style="text-align:right;margin:0 0 1\.2em;">.*?</div>', '', html_body, flags=re.DOTALL)
    html_body = re.sub(r'<div id="tblzoom[^"]*"[^>]*>.*?</div>\s*</div>', '', html_body, flags=re.DOTALL)
    html_body = re.sub(r'<div style="overflow-x:auto;[^>]*>(<table.*?>.*?</table>)</div>', r'\1', html_body, flags=re.DOTALL)
    return html_body

def build_wordpress_gutenberg_content(html_body: str) -> str:
    clean_html = strip_interactive_widgets(html_body)
    return f"\n{clean_html}\n"

def publish_to_wordpress(article: Dict[str, Any], canonical_url: str, thumb_url: str, local_thumb_path: str) -> Optional[str]:
    if not (WORDPRESS_URL and WORDPRESS_USERNAME and WORDPRESS_APP_PASSWORD): return None
    try:
        content_body = build_wordpress_gutenberg_content(article["html_body"])
        api_url = f"{WORDPRESS_URL}/wp-json/wp/v2/posts"
        auth = requests.auth.HTTPBasicAuth(WORDPRESS_USERNAME, WORDPRESS_APP_PASSWORD)
        
        post_data = {"title": article["title"], "content": content_body, "status": "publish"}
        resp = requests.post(api_url, auth=auth, json=post_data, timeout=30)
        resp.raise_for_status()
        logger.info(f"[워드프레스] 발행 완료: {resp.json().get('link')}")
        return resp.json().get('link')
    except Exception as e:
        logger.error(f"[워드프레스] 발행 실패: {e}")
        return None

def commit_and_push_changes() -> bool:
    try:
        subprocess.run(["git", "config", "user.name", "auto-blog-bot"], check=True)
        subprocess.run(["git", "config", "user.email", "bot@noreply.github.com"], check=True)
        subprocess.run(["git", "add", "."], check=True)
        if subprocess.run(["git", "diff", "--cached", "--quiet"]).returncode == 0: return True
        subprocess.run(["git", "commit", "-m", f"Auto Build: {datetime.now().strftime('%Y-%m-%d %H:%M')}"], check=True)
        subprocess.run(["git", "push"], check=True)
        return True
    except subprocess.CalledProcessError: return False

# =====================================================================
# 메인 파이프라인
# =====================================================================
def run() -> None:
    is_refresh_only = len(sys.argv) > 1 and sys.argv[1].strip().lower() == "refresh"
    fetch_and_update_trends_queue()
    if is_refresh_only: return

    os.makedirs(DOCS_DIR, exist_ok=True)
    if not os.path.exists(os.path.join(DOCS_DIR, ".nojekyll")): open(os.path.join(DOCS_DIR, ".nojekyll"), "w").close()
    ensure_brand_assets()

    queue = load_queue()
    if not queue.get("pending"): return

    keyword = queue["pending"].pop(0)
    logger.info(f"[처리 시작] 제목: {keyword}")

    try:
        article = generate_article(keyword)
        article = fix_character_count_claims(article)
        article = add_internal_link(article)
        article = add_ymyl_disclaimer(article)

        post_meta, json_ld, thumb_url, local_thumb_path, canonical_url = save_post(article)
        update_index(post_meta)

        commit_and_push_changes()
        publish_to_wordpress(article, canonical_url, thumb_url, local_thumb_path)

        queue.setdefault("completed", []).append(keyword)
        save_queue(queue)
        logger.info(f"==> 성공적으로 발행 및 완료 처리됨: {keyword}")

    except Exception as e:
        logger.error(f"처리 중 오류 발생: {e}")
        queue["pending"].insert(0, keyword)
        save_queue(queue)
        sys.exit(1)

if __name__ == "__main__":
    run()

