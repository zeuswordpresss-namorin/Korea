# -*- coding: utf-8 -*-
"""
GitHub Actions 위에서 실행되는 자동 블로그 파이프라인 스크립트 (통합판)
- [스토리텔링 강화] 호기심 천국, 세상에 이런 일이 스타일의 흥미진진한 트렌드 원인 분석형 프롬프트 적용
- [업그레이드] 조회수 10000회(1만) 이상 핫이슈 필터링 및 하루 최대 5회 발행 제한
- [업그레이드] 방문자 언어 감지 자동 번역 (버튼 숨김) 및 표 1.5배 확대 기능
- [수정] 표 좌측상단 라운드 깨짐 현상, AI 마크다운 링크 파싱 오류, FAQ 정규식 삭제 오류 완전 해결
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
# 구글 트렌드 관련 설정
# =====================================================================
TRENDS_RSS_URL = "https://trends.google.com/trends/trendingsearches/daily/rss?geo=KR"
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

WORDPRESS_URL = os.environ.get("WORDPRESS_URL", "").rstrip("/")
WORDPRESS_USERNAME = os.environ.get("WORDPRESS_USERNAME", "")
WORDPRESS_APP_PASSWORD = os.environ.get("WORDPRESS_APP_PASSWORD", "")

FONT_CANDIDATES = [
    "font.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
]

DOCS_DIR = "docs"
POSTS_DIR = os.path.join(DOCS_DIR, "posts")
POSTS_JSON = os.path.join(DOCS_DIR, "posts.json")

GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.5-flash:generateContent?key={api_key}"
)

# 프롬프트를 흥미진진한 스토리텔러 톤으로 전면 개편
SYSTEM_PROMPT = """당신은 사람들의 호기심을 강하게 자극하는 미스터리/정보 큐레이션 전문 스토리텔러이자 한국어 SEO 블로그 작가입니다. 
TV 프로그램 '호기심 천국'이나 '순간포착 세상에 이런 일이'의 내레이션처럼 독자의 상상력을 자극하고, 몰랐던 사실을 알아가는 즐거움을 주는 다채로운 톤으로 작성하세요.

아래 규칙을 지켜 작성하세요:
1. 제목은 검색 의도를 반영하되 흥미를 유발하도록 작성한다. (예: "OOO, 대체 왜 난리일까? 숨겨진 진짜 이유") 단, 입력받은 키워드의 의미를 벗어나지 않으며 25~40자 내외로 구글 검색결과에서 잘리지 않게 한다.
1-1. meta_description은 검색결과 스니펫에 노출되는 요약문이다. 핵심 키워드를 앞부분에 배치하고, 클릭을 유도하는 호기심 자극 문장으로 100~140자 내외로 작성한다.
2. 소제목(H2)을 4~6개 사용해 구조화한다.
3. [매우 중요] 단순한 사전적 뜻풀이나 정보 나열은 절대 금지합니다. 대신 "왜 지금 이 단어가 검색어 1위로 급상승했을까?", "이 이슈 이면에 숨겨진 진짜 이유는 무엇일까?"에 초점을 맞춰 비하인드 스토리, 관련 에피소드, 사람들이 몰랐던 놀라운 사실을 파헤치는 흥미진진한 전개를 보여주세요.
4. 글자 수는 1500~2200자 내외.
5. [중요] 서론(Hook)은 독자에게 충격적이거나 매우 흥미로운 질문을 던지며 시작합니다. (예: "혹시 OOO에 대해 들어보셨나요? 평범해 보이던 이 단어가 오늘 대한민국 인터넷을 발칵 뒤집어 놓았습니다. 과연 그 이면에는 어떤 사연이 숨어 있을까요?")
6. 가독성을 위해 본문 중 최소 1곳에 <table> (수치/스펙 비교용 정리표) 또는 <ul>/<ol> 목록을 반드시 포함한다. (질문-답변 내용은 표로 만들지 않음)
7. "product_keyword"에는 이 글 내용과 실제로 관련된, 쿠팡에서 검색했을 때 진짜 상품이 나올 만한 쇼핑 키워드(2~4단어)를 넣는다. 억지로 연결하기 어렵다면 반드시 빈 문자열("")로 둔다.
8. 콘텐츠 내용을 보고 아래 3가지 중 구글 상위노출에 가장 유리한 스키마 타입을 스스로 판단해서 고른다:
   - "FAQPage": 질문/답변 형태로 정리하기 좋은 주제일 때
   - "HowTo": 순서가 있는 절차/방법을 안내하는 주제일 때
   - "Article": 위 둘에 해당하지 않는 스토리텔링, 정보, 이슈형 글일 때
9. 고른 스키마 타입에 맞는 데이터를 함께 채운다: (FAQPage는 "faq_items", HowTo는 "howto_steps" 채우기, Article은 빈 배열)
10. 제목/키워드를 보고 카테고리 중 가장 알맞은 것 하나를 "category"에 고른다. ["뷰티패션", "푸드맛집", "여행", "테크IT", "재테크머니", "헬스운동", "홈인테리어", "대출보험", "정부지원금", "라이프스타일"]
11. category가 "대출보험" 또는 "정부지원금"이면 일반적인 조건 위주로 설명하고 공식 기관 확인이 필요하다는 점을 덧붙인다.
12. 이 글이 여러 구체적인 대상을 비교/소개하는 성격이면 "product_list"에 1문장 설명과 함께 채운다. (최대 6개). 아니면 빈 배열.
13. 출력은 반드시 아래 JSON 형식만 반환한다. 다른 설명, 코드블록 기호(```) 없이 순수 JSON만 출력한다:
{
  "title": "...",
  "html_body": "...",
  "meta_description": "...",
  "schema_type": "Article 또는 FAQPage 또는 HowTo",
  "faq_items": [{"question": "...", "answer": "..."}],
  "howto_steps": [{"name": "...", "text": "..."}],
  "category": "위 10개 중 하나",
  "product_keyword": "쇼핑 키워드 또는 빈 문자열",
  "product_list": [{"name": "...", "description": "..."}]
}
html_body는 <h2>, <p>, <table>, <ul> 등을 사용한 순수 HTML 구조여야 합니다. (마크다운 사용 금지)"""

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

ILLUSTRATION_PROMPTS = {
    "뷰티패션": "minimalist pencil sketch style illustration of cosmetics lipstick and fashion clothing items, clean line art",
    "푸드맛집": "minimalist pencil sketch style illustration of food dishes and cafe coffee items, clean line art",
    "여행": "minimalist pencil sketch style illustration of travel landscape airplane suitcase palm tree, clean line art",
    "테크IT": "minimalist pencil sketch style illustration of laptop computer and technology icons, clean modern line art",
    "재테크머니": "minimalist pencil sketch style illustration of coins money and finance growth chart, clean line art",
    "헬스운동": "minimalist pencil sketch style illustration of fitness workout dumbbell and healthy food, clean line art",
    "홈인테리어": "minimalist pencil sketch style illustration of cozy home interior furniture and plants, clean line art",
    "대출보험": "minimalist pencil sketch style illustration of bank building document and contract, clean professional line art",
    "정부지원금": "minimalist pencil sketch style illustration of government building document and checklist, clean line art",
    "라이프스타일": "minimalist pencil sketch style illustration of coffee book and cozy lifestyle items, clean line art",
}

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
# 구글 트렌드 파싱 (트래픽 필터 포함) 및 큐/제한 관리 함수들
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
        
        ns = {"ht": "[https://trends.google.com/trends/trendingsearches/daily](https://trends.google.com/trends/trendingsearches/daily)"}
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

def check_daily_limit() -> bool:
    queue = load_queue()
    today_str = datetime.now().strftime("%Y-%m-%d")
    daily_stats = queue.get("daily_stats", {"date": "", "count": 0})
    
    if daily_stats.get("date") != today_str:
        return True
    if daily_stats.get("count", 0) >= 5:
        return False
    return True

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
<script async src="[https://www.googletagmanager.com/gtag/js?id=](https://www.googletagmanager.com/gtag/js?id=){GA_MEASUREMENT_ID}"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){{dataLayer.push(arguments);}}
  gtag('js', new Date());
  gtag('config', '{GA_MEASUREMENT_ID}');
</script>"""

ENABLE_AUTO_TRANSLATE = os.environ.get("ENABLE_AUTO_TRANSLATE", "true").strip().lower() != "false"

def _translate_widget() -> str:
    if not ENABLE_AUTO_TRANSLATE:
        return ""
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
    if article.get("product_list"):
        graph_nodes.append({
            "@type": "ItemList", "name": f"{title} - 소개된 상품 목록",
            "itemListElement": [{"@type": "ListItem", "position": i, "item": {"@type": "Product", "name": p.get("name", ""), "description": p.get("description", "")}} for i, p in enumerate(article["product_list"][:6], 1)],
        })
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
<meta property="og:type" content="article">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{meta_description}">
<meta property="og:image" content="{thumb_url}">
<meta property="og:url" content="{canonical_url}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{title}">
<meta name="twitter:description" content="{meta_description}">
<meta name="twitter:image" content="{thumb_url}">
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
    return f"[https://fonts.googleapis.com/css2?family=](https://fonts.googleapis.com/css2?family=){families}&family=Noto+Sans+KR:wght@400;700;900&display=swap"

INDEX_TEMPLATE = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{site_title}</title>
<meta name="description" content="{site_title} - 자동으로 업데이트되는 블로그">
<link rel="canonical" href="{site_url}/">
<link rel="icon" type="image/png" href="favicon.png">{search_console_meta}
<link rel="preconnect" href="[https://fonts.googleapis.com](https://fonts.googleapis.com)">
<link href="{fonts_url}" rel="stylesheet">
<script type="application/ld+json">
{blog_json_ld}
</script>{ga_snippet}{adsense_snippet}
<style>
  /* (CSS 부분 생략됨: 기존 코드와 동일) */
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

STATIC_PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{page_title} - {site_title}</title>
<link rel="icon" type="image/png" href="favicon.png">{search_console_meta}
<style>
  body {{ max-width: 720px; margin: 40px auto; padding: 0 20px; font-family: -apple-system, sans-serif; line-height: 1.6; color:#222; }}
  a.back {{ display: inline-block; margin-bottom: 20px; color: #4a90d9; text-decoration: none; }}
</style>
</head>
<body>
<a class="back" href="index.html">← 블로그로</a>
<h1>{page_title}</h1>
{page_body}
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
  a {{ color: #4a90d9; }}
  .card {{ background:#f7f7f9; border-radius:8px; padding:16px; margin: 10px 0; }}
  a.back {{ display: inline-block; margin-bottom: 20px; color: #4a90d9; text-decoration: none; }}
</style>
</head>
<body>
<a class="back" href="index.html">← 블로그로</a>
<h1>📊 성과 관리 대시보드</h1>
<div class="card">
  <b>실시간 트래픽 확인 (GA4)</b><br>
  플레이스토어 "Google Analytics" 앱 설치 후 이 사이트의 방문자/인기글을 확인하세요.<br>
  <a href="[https://analytics.google.com](https://analytics.google.com)" target="_blank">analytics.google.com 바로가기</a>
</div>
<div class="card">
  <b>수익(쿠팡 마크업 수수료) 확인</b><br>
  쿠팡파트너스 앱 또는 사이트에서 클릭수/수익을 확인하세요.<br>
  <a href="[https://partners.coupang.com](https://partners.coupang.com)" target="_blank">partners.coupang.com 바로가기</a>
</div>
<div class="card">
  <b>광고 수익(애드센스) 확인</b><br>
  플레이스토어 "Google AdSense" 앱 설치 후 페이지뷰/광고 수익(전면광고 포함)을 확인하세요.<br>
  <a href="[https://www.google.com/adsense](https://www.google.com/adsense)" target="_blank">adsense.google.com 바로가기</a>
</div>
<div class="card">
  <b>검색 노출 확인 (Google Search Console)</b><br>
  사이트가 구글 검색에 얼마나 노출/클릭되는지 확인하세요. 최초 1회 소유권 인증이 필요합니다.<br>
  <a href="[https://search.google.com/search-console](https://search.google.com/search-console)" target="_blank">[search.google.com/search-console](https://search.google.com/search-console) 바로가기</a>
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
<urlset xmlns="[http://www.sitemaps.org/schemas/sitemap/0.9](http://www.sitemaps.org/schemas/sitemap/0.9)">
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

def generate_article(title: str) -> Dict[str, Any]:
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY 환경변수가 비어있습니다. 저장소 Secrets 설정을 확인하세요.")

    url = GEMINI_URL.format(api_key=GEMINI_API_KEY)
    payload = {
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"role": "user", "parts": [{"text": f"오늘의 핫이슈/급상승 트렌드 키워드: '{title}'\n\n이 단어가 도대체 왜 갑자기 검색어 1위에 오르며 화제가 되었는지, 그 이면에 숨겨진 비하인드 스토리나 놀라운 사실은 무엇인지 '호기심 천국'이나 '세상에 이런 일이'처럼 독자의 흥미를 자극하는 전개로 블로그 글을 작성해주세요. 단순한 뜻풀이는 지양해주세요."}]}],
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
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            
            # [FIX] 응답 앞뒤의 불필요한 마크다운 기호 및 공백을 정규식으로 안전하게 파싱
            match = re.search(r"\{.*\}", text.strip(), re.DOTALL)
            if match:
                cleaned = match.group(0)
            else:
                cleaned = text.strip().replace("```json", "").replace("```", "").strip()

            decoder = json.JSONDecoder()
            article, _ = decoder.raw_decode(cleaned)
            article["keyword"] = title

            desc = article.get("meta_description", "").strip()
            if len(desc) > 160:
                desc = desc[:157].rstrip() + "..."
            article["meta_description"] = desc

            return article
        except (KeyError, IndexError) as e:
            raise ValueError(f"Gemini 응답 형식이 예상과 다릅니다: {e}")
        except json.JSONDecodeError as e:
            raise ValueError(f"AI 응답을 JSON으로 해석하지 못했습니다: {e}")
        except requests.exceptions.RequestException as e:
            last_error = str(e)
            time.sleep(10)

    raise RuntimeError(f"3번 시도했지만 계속 실패했습니다: {last_error}")

def _load_font(size: int):
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    logger.warning("한글 폰트를 찾지 못해 기본 폰트로 대체합니다.")
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

def _hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))

def _fetch_stock_photo(category: str, size: Tuple[int, int], seed: int) -> Tuple[Optional[Image.Image], Optional[Dict[str, str]]]:
    if not PEXELS_API_KEY:
        return None, None
    query = STOCK_SEARCH_TERMS.get(category, STOCK_SEARCH_TERMS["라이프스타일"])
    try:
        resp = requests.get(
            "[https://api.pexels.com/v1/search](https://api.pexels.com/v1/search)",
            headers={"Authorization": PEXELS_API_KEY},
            params={"query": query, "orientation": "landscape", "per_page": 15, "size": "large"},
            timeout=15,
        )
        resp.raise_for_status()
        photos = resp.json().get("photos", [])
        if not photos:
            return None, None
        photo = photos[seed % len(photos)]
        img_url = photo["src"].get("large2x") or photo["src"].get("large") or photo["src"]["original"]
        img_resp = requests.get(img_url, timeout=20)
        img_resp.raise_for_status()
        img = Image.open(io.BytesIO(img_resp.content)).convert("RGB")

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
            "photographer_url": photo.get("photographer_url", "[https://www.pexels.com](https://www.pexels.com)"),
            "photo_url": photo.get("url", "[https://www.pexels.com](https://www.pexels.com)"),
            "source": "Pexels",
        }
        return img, credit
    except Exception as e:
        logger.warning(f"[무료 이미지] Pexels 검색/다운로드 실패, 그라데이션으로 대체: {e}")
        return None, None

def generate_thumbnail(title: str, output_path: str, theme: Dict[str, Any], category: str = "라이프스타일") -> Optional[Dict[str, str]]:
    seed = int(hashlib.md5(title.encode("utf-8")).hexdigest(), 16) % 100000
    photo, credit = _fetch_stock_photo(category, THUMB_SIZE, seed)

    if photo is not None:
        img = photo.convert("RGBA")
    else:
        img = _make_gradient_background(THUMB_SIZE, theme["gradient"]).convert("RGBA")

    draw = ImageDraw.Draw(img)
    accent_rgb = _hex_to_rgb(theme["accent"])

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

    if credit:
        credit_font = _load_font(20)
        credit_text = f'Photo by {credit["name"]} on {credit["source"]}'
        cb = draw.textbbox((0, 0), credit_text, font=credit_font)
        cw, ch = cb[2] - cb[0], cb[3] - cb[1]
        cx = THUMB_SIZE[0] - cw - 16
        cy = THUMB_SIZE[1] - bar_h - ch - 14
        draw.rectangle([cx - 8, cy - 4, cx + cw + 8, cy + ch + 8], fill=(0, 0, 0, 110))
        draw.text((cx, cy - cb[1]), credit_text, font=credit_font, fill=(255, 255, 255, 235))

    img.convert("RGB").save(output_path, format="WEBP", quality=85, method=6)
    return credit

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

def _coupang_deeplink(search_url: str) -> Optional[str]:
    if not (COUPANG_ACCESS_KEY and COUPANG_SECRET_KEY): return None
    domain = "[https://api-gateway.coupang.com](https://api-gateway.coupang.com)"
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
    theme = get_theme(article.get("category", "라이프스타일"))
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
    if candidate.get("category") == article.get("category", "라이프스타일"): score += 3.0
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

def _fetch_content_photo(category: str, seed: int, size=(1000, 560)):
    prompt = ILLUSTRATION_PROMPTS.get(category, ILLUSTRATION_PROMPTS["라이프스타일"]).replace("flat vector illustration of", "photo illustration of") + ", high quality, natural lighting"
    url = f"[https://image.pollinations.ai/prompt/](https://image.pollinations.ai/prompt/){urllib.parse.quote(prompt)}?width={size[0]}&height={size[1]}&seed={seed}&nologo=true"
    try:
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
        img = Image.open(io.BytesIO(resp.content)).convert("RGB")
        if img.size != size: img = img.resize(size)
        return img
    except Exception as e:
        logger.warning(f"[본문 이미지] 생성 실패, 삽입 건너뜁니다: {e}")
        return None

def enhance_tables(html_body: str, accent: str) -> str:
    counter = {"n": 0}
    def _style_cells(raw_table: str, min_width: int, is_modal: bool = False) -> str:
        font_size = "1.5em" if is_modal else "0.92em"
        pad_th = "18px 21px" if is_modal else "12px 14px"
        pad_td = "18px 21px" if is_modal else "12px 14px"
        
        styled = re.sub(
            r"<table\b[^>]*>",
            f'<table style="width:100%;min-width:{min_width}px;border-collapse:collapse;font-size:{font_size};"',
            raw_table, count=1,
        )
        styled = re.sub(
            r"<th\b[^>]*>",
            f'<th style="padding:{pad_th};text-align:left;background:{accent}1f;font-weight:800;'
            f'color:#111;border-bottom:2px solid {accent}80;white-space:nowrap;">',
            styled,
        )
        styled = re.sub(
            r"<td\b[^>]*>",
            f'<td style="padding:{pad_td};text-align:left;border-bottom:1px solid #ececec;line-height:1.65;vertical-align:top;">',
            styled,
        )
        return styled

    def wrap_table(match):
        counter["n"] += 1
        uid = f"tblzoom{counter['n']}_{random.randint(1000, 9999)}"
        table_html = match.group(0)
        styled_table = _style_cells(table_html, 460, False)
        modal_table = _style_cells(table_html, 630, True)

        # [FIX] 표 좌측상단 라운드 깨짐 완벽 방지: 바깥쪽 div에서 overflow:hidden 및 박스 그림자로 통제
        return (
            f'<div style="margin:1.2em 0 0.4em;border-radius:8px;box-shadow:0 0 0 1px #eee;overflow:hidden;background:#fff;">'
            f'<div style="overflow-x:auto;-webkit-overflow-scrolling:touch;">{styled_table}</div></div>'
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

def insert_content_image(article: Dict[str, Any], slug: str) -> Dict[str, Any]:
    category = article.get("category", "라이프스타일")
    seed = int(hashlib.md5((article["title"] + "-inline").encode("utf-8")).hexdigest(), 16) % 100000
    photo = _fetch_content_photo(category, seed)
    if photo is None: return article
    filename = f"{slug}-inline.webp"
    path = os.path.join(DOCS_DIR, "thumbs", filename)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    photo.save(path, format="WEBP", quality=82, method=6)

    img_html = f'<img src="../thumbs/{filename}" alt="{article["title"]} 관련 이미지" loading="lazy" style="width:100%;border-radius:10px;margin:20px 0;">'
    idx = article["html_body"].find("</h2>")
    if idx != -1: article["html_body"] = article["html_body"][:idx + 5] + img_html + article["html_body"][idx + 5:]
    else: article["html_body"] = img_html + article["html_body"]
    return article

def _fetch_product_icon(product_name: str, seed: int, size=(160, 160)):
    prompt = f"minimalist pencil sketch icon of {product_name}, single centered object, clean line art, simple outline, white background, no text, no watermark"
    url = f"[https://image.pollinations.ai/prompt/](https://image.pollinations.ai/prompt/){urllib.parse.quote(prompt)}?width={size[0]}&height={size[1]}&seed={seed}&nologo=true"
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        img = Image.open(io.BytesIO(resp.content)).convert("RGB")
        if img.size != size: img = img.resize(size)
        return img
    except Exception as e:
        logger.warning(f"[상품 아이콘] 생성 실패: {e}")
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
    search_url = f"[https://www.coupang.com/np/search?q=](https://www.coupang.com/np/search?q=){urllib.parse.quote(product_keyword)}"
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
    category = article.get("category", "라이프스타일")
    theme = get_theme(category)
    slug = slugify(article["keyword"])
    today = datetime.now().strftime("%Y-%m-%d")
    thumb_filename = f"{slug}-{today}.webp"
    post_filename = f"{slug}-{today}.html"
    photo_credit = generate_thumbnail(article["title"], os.path.join(DOCS_DIR, "thumbs", thumb_filename), theme, category)
    photo_credit_html = ""
    if photo_credit:
        photo_credit_html = (
            f'<p style="margin:6px 0 0;font-size:0.78em;color:#aaa;">'
            f'사진: <a href="{photo_credit["photo_url"]}" target="_blank" rel="nofollow noopener">'
            f'{photo_credit["name"]}</a> / {photo_credit["source"]} (무료 이미지, 출처 표기)</p>'
        )

    # [FIX] AI가 마크다운으로 링크나 볼드체를 뱉어낼 경우 순수 HTML로 안전하게 변환
    html_body = article.get("html_body", "")
    html_body = re.sub(r"\[([^\]]+)\]\((https?://[^\)]+)\)", r'<a href="\2" target="_blank" rel="noopener">\1</a>', html_body)
    html_body = re.sub(r"\*\*([^\*]+)\*\*", r'<strong>\1</strong>', html_body)
    article["html_body"] = html_body

    # [FIX] FAQ 제거 정규식 안전장치: 단일 p 태그나 단일 table 까지만 지우도록 제한
    cleaned_body = re.sub(
        r"<h[23]>[^<]*자주\s*묻는\s*질문[^<]*</h[23]>\s*(?:<p>.*?</p>\s*)?(?:<table.*?</table>)?",
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
            f'<div class="hero-body"><span class="hero-badge" style="background:{p.get("accent", "#4a90d9")}">{p.get("badge", "✨ 라이프스타일")}</span>'
            f'<div class="hero-title">{p["title"]}</div><div class="date">{p["date"]}</div></div></a>'
        )
    mid_html = ""
    if mid_posts:
        cards = "\n".join(
            f'<a class="mid-card" href="{p["file"]}"><img src="{p["thumb"]}" alt="{p["title"]}" loading="lazy">'
            f'<div class="mid-body"><span class="badge-sm" style="background:{p.get("accent", "#4a90d9")}">{p.get("badge", "✨ 라이프스타일")}</span>'
            f'<div class="mid-title">{p["title"]}</div><div class="date">{p["date"]}</div></div></a>' for p in mid_posts
        )
        mid_html = f'<div class="tier-label">📖 다음 이야기</div><div class="mid-grid">{cards}</div>'
    bottom_html = ""
    if bottom_posts:
        cards = "\n".join(
            f'<a class="bottom-card" href="{p["file"]}"><img src="{p["thumb"]}" alt="{p["title"]}" loading="lazy">'
            f'<div class="bottom-body"><span class="badge-sm" style="background:{p.get("accent", "#4a90d9")}">{p.get("badge", "✨ 라이프스타일")}</span>'
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
        ))
    return posts

def generate_static_pages() -> None:
    os.makedirs(DOCS_DIR, exist_ok=True)
    common_kwargs = dict(site_title=SITE_TITLE, search_console_meta=_search_console_meta(), ga_snippet=_ga_snippet(), adsense_snippet=_adsense_snippet())
    pages = {
        "about.html": ("블로그 소개", f"<p>{SITE_TITLE}에 오신 것을 환영합니다.</p><p>{SITE_TAGLINE}</p><p>이 블로그는 다양한 주제의 정보를 정리해서 소개하며, 콘텐츠 제작 과정 일부에 AI 도구를 활용하고 있습니다. 게시된 정보는 참고용이며, 중요한 결정을 내리실 때는 반드시 공식 출처를 함께 확인해주세요.</p>"),
        "privacy.html": ("개인정보처리방침", "<p>본 블로그는 구글 애널리틱스(GA4) 및 구글 애드센스를 통해 방문자 통계와 광고를 제공할 수 있습니다. 이 과정에서 쿠키(Cookie)가 사용될 수 있으며, 쿠키를 통해 수집되는 정보에는 개인을 직접 식별할 수 있는 정보는 포함되지 않습니다.</p><h2>쿠키 및 광고</h2><p>구글을 포함한 제3자 광고 공급업체는 쿠키를 사용하여 사용자의 이전 방문 기록을 기반으로 광고를 게재합니다. 이용자는 <a href=\"[https://adssettings.google.com](https://adssettings.google.com)\" target=\"_blank\">구글 광고 설정</a>에서 맞춤 광고를 비활성화할 수 있습니다.</p><h2>문의</h2><p>개인정보 관련 문의사항은 문의하기 페이지를 통해 연락 주시기 바랍니다.</p>"),
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
    resp = requests.post("[https://oauth2.googleapis.com/token](https://oauth2.googleapis.com/token)", data={"client_id": GOOGLE_CLIENT_ID, "client_secret": GOOGLE_CLIENT_SECRET, "refresh_token": GOOGLE_REFRESH_TOKEN, "grant_type": "refresh_token"}, timeout=15)
    resp.raise_for_status()
    return resp.json()["access_token"]
def _make_blogger_safe_html(html_body: str) -> str:
    if SITE_URL:
        return html_body.replace('href="../posts/', f'href="{SITE_URL}/posts/').replace('href="../thumbs/', f'href="{SITE_URL}/thumbs/').replace('src="../thumbs/', f'src="{SITE_URL}/thumbs/')
    return re.sub(r'<img src="\.\./thumbs/[^"]*"[^>]*>', "", re.sub(r'<a href="\.\./(posts|thumbs)/[^"]*"[^>]*>(.*?)</a>', r"\2", html_body))

def publish_to_blogger(article: Dict[str, Any], canonical_url: str, thumb_url: str, local_thumb_path: str) -> None:
    if not _blogger_configured(): return
    try:
        access_token = _get_blogger_access_token()
        theme = get_theme(article.get("category", "라이프스타일"))
        today = datetime.now().strftime("%Y-%m-%d")
        blogger_json_ld = build_json_ld(article, canonical_url, thumb_url, today, platform="blogger")
        try:
            with open(local_thumb_path, "rb") as f: img_src = f"data:image/webp;base64,{base64.b64encode(f.read()).decode('ascii')}"
        except: img_src = thumb_url
        content_html = (
            f'{_translate_widget()}'
            f'<img src="{img_src}" style="max-width:100%;border-radius:8px;" alt="{article["title"]}">'
            f'<span style="display:inline-block;background:{theme["accent"]};color:#fff;font-size:0.85em;font-weight:bold;padding:4px 12px;border-radius:999px;margin:14px 0 4px;">{theme["badge"]}</span>'
            f'{_make_blogger_safe_html(article["html_body"])}<script type="application/ld+json">{blogger_json_ld}</script>'
        )
        url = f"[https://www.googleapis.com/blogger/v3/blogs/](https://www.googleapis.com/blogger/v3/blogs/){BLOGGER_BLOG_ID}/posts/"
        resp = requests.post(url, headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}, json={"title": article["title"], "content": content_html}, timeout=30)
        resp.raise_for_status()
        logger.info(f"[블로거] 발행 완료: {resp.json().get('url', '(URL 확인 불가)')}")
    except Exception as e:
        logger.error(f"[블로거] 발행 실패: {e}")

def _wordpress_configured() -> bool:
    return bool(WORDPRESS_URL and WORDPRESS_USERNAME and WORDPRESS_APP_PASSWORD)

def publish_to_wordpress(article: Dict[str, Any], canonical_url: str, thumb_url: str, local_thumb_path: str) -> None:
    if not _wordpress_configured(): return
    try:
        auth_token = base64.b64encode(f"{WORDPRESS_USERNAME}:{WORDPRESS_APP_PASSWORD}".encode("utf-8")).decode("ascii")
        auth_header = f"Basic {auth_token}"
        theme = get_theme(article.get("category", "라이프스타일"))

        featured_media_id = None
        try:
            with open(local_thumb_path, "rb") as f:
                img_bytes = f.read()
            media_resp = requests.post(
                f"{WORDPRESS_URL}/wp-json/wp/v2/media",
                headers={
                    "Authorization": auth_header,
                    "Content-Disposition": f'attachment; filename="{os.path.basename(local_thumb_path)}"',
                    "Content-Type": "image/webp",
                },
                data=img_bytes,
                timeout=30,
            )
            media_resp.raise_for_status()
            featured_media_id = media_resp.json().get("id")
        except Exception as e:
            logger.warning(f"[워드프레스] 대표이미지 업로드 실패, 이미지 없이 발행합니다: {e}")

        content_html = (
            f'<span style="display:inline-block;background:{theme["accent"]};color:#fff;font-size:0.85em;'
            f'font-weight:bold;padding:4px 12px;border-radius:999px;margin:0 0 14px;">{theme["badge"]}</span>'
            f'{article["html_body"]}'
            f'<p style="color:#999;font-size:12px;">원문: <a href="{canonical_url}" target="_blank" rel="noopener">{canonical_url}</a></p>'
        )
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
        logger.info(f"[워드프레스] 발행 완료: {resp.json().get('link', '(URL 확인 불가)')}")
    except Exception as e:
        logger.error(f"[워드프레스] 발행 실패: {e}")

def ensure_nojekyll() -> None:
    os.makedirs(DOCS_DIR, exist_ok=True)
    if not os.path.exists(os.path.join(DOCS_DIR, ".nojekyll")):
        open(os.path.join(DOCS_DIR, ".nojekyll"), "w").close()

def run() -> None:
    is_refresh_only = len(sys.argv) > 1 and sys.argv[1].strip().lower() == "refresh"
    
    fetch_and_update_trends_queue()
    if is_refresh_only:
        return

    manual_title = ""
    if len(sys.argv) > 1 and sys.argv[1].strip() and sys.argv[1].strip().lower() not in ["publish", "refresh"]:
        manual_title = sys.argv[1].strip()

    title = ""
    if manual_title:
        title = manual_title
    else:
        if not check_daily_limit():
            logger.info("오늘의 자동 발행 한도(5회)를 모두 소진하여 포스팅을 생략합니다.")
            return
            
        queue = load_queue()
        if not queue.get("pending"):
            logger.info("대기 중인 (10000회 이상) 핫이슈 키워드가 없습니다.")
            return
            
        title = queue["pending"].pop(0)
        queue.setdefault("completed", []).append(title)
        save_queue(queue)

    logger.info(f"[처리 시작] 제목: {title}")

    ensure_nojekyll()
    ensure_brand_assets()
    generate_static_pages()

    article = generate_article(title)
    logger.info(f"글 생성 완료: {article['title']}")

    article = add_internal_link(article)
    article = insert_manual_ads(article)
    article = add_coupang_markup(article)
    article = add_ymyl_disclaimer(article)

    post_meta, json_ld, thumb_url, local_thumb_path, post_url = save_post(article)
    posts = update_index(post_meta)

    update_dashboard(posts)
    update_seo_files(posts)
    publish_to_blogger(article, post_url, thumb_url, local_thumb_path)
    publish_to_wordpress(article, post_url, thumb_url, local_thumb_path)

    if not manual_title:
        increment_daily_count()

    logger.info(f"저장 완료: docs/{post_meta['file']}, docs/{post_meta['thumb']}")


if __name__ == "__main__":
    try:
        run()
    except Exception as e:
        logger.error(f"스크립트 실행 중 치명적인 오류 발생: {e}")
        sys.exit(1)

