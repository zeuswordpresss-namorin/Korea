# -*- coding: utf-8 -*-
"""
GitHub Actions 위에서 실행되는 자동 블로그 파이프라인 스크립트 (통합판)
- 구글 트렌드 자동 수집 + 자동 포스팅 파이프라인 통합
- UI 개선(표 좌측상단 오류 수정) 및 서론 호기심 유발 프롬프트 적용
- Pollinations AI 기반 다채로운 썸네일 및 일러스트/아이콘 자동 생성 적용 (안정성 강화)
- 잘못된 마크다운 URL 일괄 수정 및 재시도 로직 강화
"""

import base64
import hashlib
import hmac
import io
import json
import os
import random
import re
import sys
import textwrap
import time
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime

import requests
from PIL import Image, ImageDraw, ImageFont

# =====================================================================
# 구글 트렌드 관련 설정
# =====================================================================
TRENDS_RSS_URLS = [
    "https://trends.google.com/trending/rss?geo=KR",
    "https://trends.google.com/trends/trendingsearches/daily/rss?geo=KR",
]
TOP_N = 7
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

SYSTEM_PROMPT = """당신은 한국어 SEO 블로그 콘텐츠 작가 겸 구조화 데이터(스키마 마크업) 전문가입니다.
아래 규칙을 지켜 작성하세요:
1. 제목은 검색 의도를 반영하되 과장/낚시성 표현은 피한다.
1-1. meta_description은 검색결과 스니펫에 노출되는 요약문이다. 100~140자 내외로 작성한다.
2. 소제목(H2)을 4~6개 사용해 구조화한다.
3. 확인되지 않은 구체적 수치·통계·자격요건·금리·지원금액을 지어내지 않는다.
4. 글자 수는 1500~2200자 내외.
5. [중요] 서론은 방문자의 호기심을 강하게 자극하는 '훅(Hook)'으로 시작한다.
6. 가독성을 위해 본문 중 최소 1곳에 <table> 또는 <ul>/<ol> 목록을 반드시 포함한다. 단, 질문-답변(Q&A) 내용은 절대 <table>로 만들지 않는다.
7. "product_keyword"에는 이 글 내용과 실제로 관련된 쇼핑 키워드를 넣는다. 억지로 만들지 말고 빈 문자열("")로 두어도 된다.
8. 콘텐츠 내용을 보고 구글 상위노출에 가장 유리한 스키마 타입("FAQPage", "HowTo", "Article") 중 하나를 고른다.
9. 고른 스키마 타입에 맞는 데이터(faq_items, howto_steps)를 함께 채운다.
10. "category"에 알맞은 것을 고른다: ["뷰티패션", "푸드맛집", "여행", "테크IT", "재테크머니", "헬스운동", "홈인테리어", "대출보험", "정부지원금", "라이프스타일"]
11. category가 "대출보험" 또는 "정부지원금"이면 단정적으로 추천하지 않는다.
12. "product_list"에 6개 이하로 상품/브랜드/모델을 채운다. 비교·소개형 글이 아니면 빈 배열로 둔다.
13. 출력은 반드시 아래 JSON 형식만 반환한다:
{
  "title": "...",
  "html_body": "...",
  "meta_description": "...",
  "schema_type": "Article",
  "faq_items": [{"question": "...", "answer": "..."}],
  "howto_steps": [{"name": "...", "text": "..."}],
  "category": "라이프스타일",
  "product_keyword": "",
  "product_list": [{"name": "...", "description": "..."}]
}"""

# =====================================================================
# 카테고리별 트렌디 테마 및 프롬프트
# =====================================================================
CATEGORY_THEMES = {
    "뷰티패션": {"gradient": [(255, 107, 157), (255, 154, 158), (250, 208, 196)], "accent": "#ff6b9d", "badge": "💄 뷰티·패션", "label": "BEAUTY", "font": "Gowun+Dodum", "decor": ["💄", "💅", "👗", "👠", "💋"]},
    "푸드맛집": {"gradient": [(255, 107, 53), (247, 147, 30), (255, 210, 63)], "accent": "#ff6b35", "badge": "🍽️ 푸드·맛집", "label": "FOOD", "font": "Jua", "decor": ["🍕", "🍔", "🍰", "🍜", "☕"]},
    "여행": {"gradient": [(17, 153, 142), (56, 239, 125), (100, 210, 255)], "accent": "#11998e", "badge": "✈️ 여행", "label": "TRAVEL", "font": "Gowun+Dodum", "decor": ["✈️", "🌴", "🗺️", "🧳", "📸"]},
    "테크IT": {"gradient": [(30, 60, 114), (42, 82, 152), (0, 198, 255)], "accent": "#2a5298", "badge": "💻 테크·IT", "label": "TECH", "font": "Noto+Sans+KR:wght@700", "decor": ["💻", "📱", "🔌", "🤖", "⚡"]},
    "재테크머니": {"gradient": [(17, 105, 79), (56, 173, 118), (168, 224, 99)], "accent": "#11694f", "badge": "💰 재테크", "label": "MONEY", "font": "Noto+Sans+KR:wght@700", "decor": ["💰", "💵", "📈", "🪙", "🏦"]},
    "헬스운동": {"gradient": [(19, 78, 94), (113, 178, 128), (168, 224, 99)], "accent": "#134e5e", "badge": "💪 헬스·운동", "label": "FITNESS", "font": "Jua", "decor": ["💪", "🏋️", "🥗", "🏃", "🥑"]},
    "홈인테리어": {"gradient": [(196, 132, 88), (218, 170, 122), (238, 210, 175)], "accent": "#c48458", "badge": "🏠 홈·인테리어", "label": "HOME", "font": "Gowun+Dodum", "decor": ["🏠", "🪴", "🛋️", "🖼️", "🛏️"]},
    "대출보험": {"gradient": [(20, 30, 48), (36, 59, 85), (65, 90, 119)], "accent": "#1e3a5f", "badge": "🏦 대출·보험", "label": "FINANCE", "font": "Noto+Sans+KR:wght@700", "decor": ["🏦", "📄", "💳", "✅", "💼"], "ymyl": True},
    "정부지원금": {"gradient": [(0, 91, 82), (0, 128, 105), (82, 183, 136)], "accent": "#00695c", "badge": "🏛️ 정부지원금", "label": "SUPPORT", "font": "Noto+Sans+KR:wght@700", "decor": ["🏛️", "📋", "📅", "✅", "📢"], "ymyl": True},
    "라이프스타일": {"gradient": [(66, 133, 244), (156, 39, 176), (234, 67, 121)], "accent": "#4a90d9", "badge": "✨ 라이프스타일", "label": "LIFESTYLE", "font": "Noto+Sans+KR:wght@700", "decor": ["✨", "🌸", "☕", "🎧", "🌿"]},
}
DEFAULT_THEME = CATEGORY_THEMES["라이프스타일"]

def get_theme(category: str) -> dict:
    return CATEGORY_THEMES.get(category, DEFAULT_THEME)

# 프롬프트 간소화 (에러 방지)
ILLUSTRATION_PROMPTS = {
    "뷰티패션": "minimalist sketch cosmetics fashion",
    "푸드맛집": "minimalist sketch food cafe",
    "여행": "minimalist sketch travel landscape",
    "테크IT": "minimalist sketch laptop tech",
    "재테크머니": "minimalist sketch coins finance",
    "헬스운동": "minimalist sketch fitness dumbbell",
    "홈인테리어": "minimalist sketch cozy home interior",
    "대출보험": "minimalist sketch bank contract",
    "정부지원금": "minimalist sketch government building",
    "라이프스타일": "minimalist sketch coffee book lifestyle",
}
ILLUSTRATION_SUFFIX = ", clean line art, simple outline, white background, no text"

# =====================================================================
# 구글 트렌드 및 큐 관리 함수들
# =====================================================================
def fetch_top_trends(n: int = TOP_N) -> list[str]:
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    last_error = None
    for url in TRENDS_RSS_URLS:
        try:
            response = requests.get(url, timeout=REQUEST_TIMEOUT, headers=headers)
            response.raise_for_status()
            root = ET.fromstring(response.content)
            titles = [item.findtext("title").strip() for item in root.iter("item") if item.findtext("title")]
            if titles:
                return titles[:n]
        except Exception as e:
            last_error = f"{url} 실패: {e}"
    raise RuntimeError(f"모든 트렌드 URL에서 수집 실패. 마지막 오류: {last_error}")

def load_queue() -> dict:
    if not os.path.exists(QUEUE_FILE):
        return {"pending": [], "completed": []}
    try:
        with open(QUEUE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {"pending": [], "completed": []}

def save_queue(queue: dict) -> None:
    with open(QUEUE_FILE, "w", encoding="utf-8") as f:
        json.dump(queue, f, ensure_ascii=False, indent=2)

def fetch_and_update_trends_queue():
    print("=" * 60)
    print("[구글 트렌드] 수집 시작...")
    try:
        trends = fetch_top_trends(TOP_N)
    except Exception as e:
        print(f"[경고] {e}")
        return
    queue = load_queue()
    existing = set(queue.get("pending", [])) | set(queue.get("completed", []))
    new_keywords = [t for t in trends if t not in existing]
    queue.setdefault("pending", []).extend(new_keywords)
    save_queue(queue)
    print(f"[수집 완료] 신규 추가: {len(new_keywords)}개 / 대기 중: {len(queue['pending'])}개")
    print("=" * 60)

# =====================================================================
# HTML 및 렌더링 템플릿들
# =====================================================================
def _search_console_meta() -> str:
    return f'\n<meta name="google-site-verification" content="{GOOGLE_SITE_VERIFICATION}">' if GOOGLE_SITE_VERIFICATION else ""

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
    if not ENABLE_AUTO_TRANSLATE: return ""
    return """
<div style="position:fixed;top:10px;right:10px;z-index:999;">
  <button onclick="var e=document.getElementById('gt-box');e.style.display=(e.style.display==='none'||!e.style.display)?'block':'none';"
    style="border:none;border-radius:999px;background:#fff;color:#333;font-weight:700;font-size:12px;padding:9px 14px;box-shadow:0 2px 8px rgba(0,0,0,0.25);cursor:pointer;">번역</button>
  <div id="gt-box" style="display:none;margin-top:6px;background:#fff;padding:6px 8px;border-radius:10px;box-shadow:0 2px 10px rgba(0,0,0,0.18);">
    <div id="google_translate_element"></div>
  </div>
</div>
<script>function googleTranslateElementInit() { new google.translate.TranslateElement({pageLanguage: 'ko', autoDisplay: false}, 'google_translate_element'); }</script>
<script src="https://translate.google.com/translate_a/element.js?cb=googleTranslateElementInit"></script>"""

def _adsense_snippet() -> str:
    if not ADSENSE_CLIENT_ID: return ""
    return f'\n<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client={ADSENSE_CLIENT_ID}" crossorigin="anonymous"></script>'

def build_faq_section_html(article: dict, accent: str = "#4a90d9") -> str:
    if not article.get("faq_items"): return ""
    cards = []
    for i, qa in enumerate(article["faq_items"], 1):
        cards.append(f'<details style="margin:14px 0;background:#f7f8fa;border-left:4px solid {accent};border-radius:8px;padding:2px 18px;" open>'
                     f'<summary style="cursor:pointer;padding:14px 0;font-weight:800;font-size:1.08em;outline:none;">Q{i}. {qa.get("question", "")}</summary>'
                     f'<p style="margin:0;padding:0 0 16px;color:#555;line-height:1.75;">A. {qa.get("answer", "")}</p></details>')
    return '<h2 style="margin-top:2em;">자주 묻는 질문(FAQ)</h2>' + "".join(cards)

def build_json_ld(article: dict, canonical_url: str, thumb_url: str, date: str, platform: str = "github") -> str:
    schema_type = article.get("schema_type", "Article")
    data = {"@context": "https://schema.org", "@type": schema_type}
    if schema_type == "FAQPage" and article.get("faq_items"):
        data["mainEntity"] = [{"@type": "Question", "name": qa.get("question"), "acceptedAnswer": {"@type": "Answer", "text": qa.get("answer")}} for qa in article["faq_items"]]
    else:
        data.update({"headline": article["title"], "description": article.get("meta_description", ""), "image": thumb_url, "datePublished": date, "author": {"@type": "Organization", "name": SITE_TITLE}})
    graph = {"@context": "https://schema.org", "@graph": [data]}
    return json.dumps(graph, ensure_ascii=False)

def build_blog_index_json_ld(posts: list) -> str:
    data = {"@context": "https://schema.org", "@type": "Blog", "name": SITE_TITLE, "url": (SITE_URL + "/") if SITE_URL else "."}
    data["blogPost"] = [{"@type": "BlogPosting", "headline": p["title"], "url": p["file"], "datePublished": p["date"]} for p in posts[:10]]
    return json.dumps(data, ensure_ascii=False)

POST_TEMPLATE = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<meta name="description" content="{meta_description}">
<link rel="canonical" href="{canonical_url}">
<link rel="icon" type="image/png" href="../favicon.png">{search_console_meta}
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family={font}&family=Noto+Sans+KR:wght@400;700&display=swap" rel="stylesheet">
<script type="application/ld+json">{json_ld}</script>{ga_snippet}{adsense_snippet}
<style>
  * {{ box-sizing: border-box; }} body {{ max-width: 720px; margin: 0 auto; padding: 0 16px 60px; font-family: 'Noto Sans KR', sans-serif; line-height: 1.75; color: #1a1a1a; background: #fafafa; }}
  img {{ max-width: 100%; height: auto; display: block; }}
  .hero {{ margin: 0 -16px 24px; }} .hero img {{ width: 100%; aspect-ratio: 16/9; object-fit: cover; }}
  .badge {{ background: {accent}; color: #fff; font-size: 0.85em; font-weight: 700; padding: 5px 14px; border-radius: 999px; }}
  h1 {{ font-family: '{font_family}', sans-serif; font-size: clamp(1.4em, 5vw, 1.9em); margin-bottom: 8px; }}
  h2 {{ font-family: '{font_family}', sans-serif; border-left: 5px solid {accent}; padding-left: 10px; margin-top: 2em; }}
  table {{ width: 100%; border-collapse: collapse; }} th, td {{ padding: 11px 14px; border-bottom: 1px solid #eee; text-align: left; }} th {{ background: {accent}14; }}
  a.back {{ display: inline-block; margin: 20px 0; color: {accent}; text-decoration: none; font-weight: 700; }}
</style>
</head>
<body>
{translate_widget}
<a class="back" href="../index.html">← 목록으로</a>
<div class="hero"><img src="../thumbs/{thumb_filename}" alt="{title}"></div>
<span class="badge">{badge}</span>
<h1>{title}</h1>
<p style="color:#999;font-size:0.85em;">{date}</p>
{html_body}
{related_html}
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
<link rel="icon" type="image/png" href="favicon.png">{search_console_meta}
<link href="{fonts_url}" rel="stylesheet">
<script type="application/ld+json">{blog_json_ld}</script>{ga_snippet}{adsense_snippet}
<style>
  body {{ max-width: 1000px; margin: 0 auto; font-family: 'Noto Sans KR', sans-serif; background:#f5f5f7; color:#1a1a1a; }}
  .masthead img {{ width: 100%; object-fit: cover; aspect-ratio: 1600/420; }}
  .brand-row {{ display:flex; align-items:center; gap:12px; margin: 18px 20px; }}
  .hero, .mid-card, .bottom-card {{ background:#fff; border-radius:16px; display:block; text-decoration:none; color:#111; overflow:hidden; margin: 16px 20px; box-shadow: 0 4px 12px rgba(0,0,0,0.05); }}
  .hero img, .mid-card img {{ width:100%; aspect-ratio:16/9; object-fit:cover; }}
  .pad {{ padding: 16px; }}
</style>
</head>
<body>
{translate_widget}
<div class="masthead"><img src="banner.webp" alt="banner"></div>
<div class="brand-row">
  <img src="logo.webp" alt="logo" style="width:44px;border-radius:50%;">
  <h1 style="margin:0;font-size:1.5em;">{site_title}</h1>
  <a href="dashboard.html" style="margin-left:auto;font-size:0.8em;text-decoration:none;background:#eee;padding:6px 12px;border-radius:20px;color:#333;">📊 성과관리</a>
</div>
<p style="padding:0 20px;color:#666;">{site_tagline}</p>
{hero_html}
</body>
</html>
"""

DASHBOARD_TEMPLATE = """<!DOCTYPE html>
<html lang="ko">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>대시보드</title></head>
<body style="max-width:760px;margin:40px auto;padding:0 20px;font-family:sans-serif;">
<a href="index.html">← 홈으로</a>
<h1>📊 대시보드</h1>
<ul>
  <li><a href="https://analytics.google.com" target="_blank">Google Analytics (GA4)</a></li>
  <li><a href="https://search.google.com/search-console" target="_blank">Search Console</a></li>
  <li><a href="https://www.google.com/adsense" target="_blank">AdSense</a></li>
  <li><a href="https://partners.coupang.com" target="_blank">Coupang Partners</a></li>
</ul>
<h2>발행된 글 ({post_count}개)</h2>
<table style="width:100%;text-align:left;"><tr><th>날짜</th><th>제목</th></tr>{rows}</table>
</body></html>
"""

SITEMAP_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url><loc>{site_url}/</loc></url>
{url_entries}
</urlset>"""

ROBOTS_TXT = "User-agent: *\nAllow: /\n\nSitemap: {site_url}/sitemap.xml\n"

# =====================================================================
# 기타 유틸리티 및 AI 생성부
# =====================================================================
def get_title_from_args_or_queue() -> str:
    if len(sys.argv) > 1 and sys.argv[1].strip(): return sys.argv[1].strip()
    queue = load_queue()
    if not queue.get("pending"): raise RuntimeError("대기 중인 키워드가 없습니다.")
    title = queue["pending"].pop(0)
    queue.setdefault("completed", []).append(title)
    save_queue(queue)
    return title

def generate_article(title: str) -> dict:
    url = GEMINI_URL.format(api_key=GEMINI_API_KEY)
    payload = {"systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]}, "contents": [{"role": "user", "parts": [{"text": f"제목: '{title}' 블로그 작성"}]}]}
    for attempt in range(1, 4):
        try:
            resp = requests.post(url, json=payload, timeout=60)
            resp.raise_for_status()
            text = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            article = json.loads(text)
            article["keyword"] = title
            return article
        except Exception as e:
            print(f"Gemini 오류 (시도 {attempt}): {e}")
            time.sleep(10)
    raise RuntimeError("Gemini API 호출 최종 실패")

# 통합된 안전한 무료 AI 이미지 생성 함수
def _fetch_image_from_pollinations(prompt: str, size: tuple, seed: int) -> Image.Image:
    safe_prompt = prompt[:300]
    url = f"[https://image.pollinations.ai/prompt/](https://image.pollinations.ai/prompt/){urllib.parse.quote(safe_prompt)}?width={size[0]}&height={size[1]}&seed={seed}&nologo=true"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
    
    for attempt in range(1, 4):
        try:
            resp = requests.get(url, headers=headers, timeout=60)
            resp.raise_for_status()
            
            # Content-Type 검사
            content_type = resp.headers.get("Content-Type", "")
            if not content_type.startswith("image/"):
                print(f"  → [이미지 실패] Content-Type 불일치: {content_type}")
                time.sleep(5)
                continue
                
            img_bytes = io.BytesIO(resp.content)
            img = Image.open(img_bytes)
            img.verify() # 파일 손상 검증
            
            img_bytes.seek(0)
            valid_img = Image.open(img_bytes).convert("RGBA")
            if valid_img.size != size:
                valid_img = valid_img.resize(size)
            return valid_img
        except Exception as e:
            print(f"  → [Pollinations 생성 실패] (시도 {attempt}/3): {e}")
            time.sleep(10 * attempt)
    return None

def generate_thumbnail(title: str, output_path: str, theme: dict, category: str = "라이프스타일") -> None:
    img = Image.new("RGBA", (1280, 720), theme["gradient"][1]) # 기본 그라데이션 단순화
    seed = int(hashlib.md5(title.encode("utf-8")).hexdigest(), 16) % 100000
    prompt = ILLUSTRATION_PROMPTS.get(category, ILLUSTRATION_PROMPTS["라이프스타일"]) + ILLUSTRATION_SUFFIX
    
    illustration = _fetch_image_from_pollinations(prompt, (1280, 720), seed)
    if illustration:
        img = Image.blend(img, illustration, alpha=0.15)
        
    draw = ImageDraw.Draw(img)
    try: font = ImageFont.truetype(FONT_CANDIDATES[0] if os.path.exists(FONT_CANDIDATES[0]) else FONT_CANDIDATES[1], 70)
    except: font = ImageFont.load_default()
    
    draw.text((100, 300), title[:25], font=font, fill=(255,255,255,255))
    img.convert("RGB").save(output_path, format="WEBP", quality=85)

def insert_content_image(article: dict, slug: str) -> dict:
    category = article.get("category", "라이프스타일")
    seed = int(hashlib.md5((article["title"] + "inline").encode("utf-8")).hexdigest(), 16) % 100000
    prompt = ILLUSTRATION_PROMPTS.get(category, ILLUSTRATION_PROMPTS["라이프스타일"]).replace("sketch", "photo") + " natural lighting, high quality"
    
    photo = _fetch_image_from_pollinations(prompt, (1000, 560), seed)
    if not photo: return article
    
    filename = f"{slug}-inline.webp"
    photo.convert("RGB").save(os.path.join(DOCS_DIR, "thumbs", filename), format="WEBP")
    
    img_html = f'<img src="../thumbs/{filename}" style="width:100%;border-radius:10px;margin:20px 0;">'
    article["html_body"] = img_html + article["html_body"]
    return article

def build_product_list_html(article: dict, slug: str, accent: str) -> str:
    products = article.get("product_list") or []
    if not products: return ""
    cards = []
    for i, item in enumerate(products[:6], 1):
        seed = int(hashlib.md5(f"{slug}-prod-{i}".encode("utf-8")).hexdigest(), 16) % 100000
        prompt = f"minimalist sketch icon of {item.get('name', '')}" + ILLUSTRATION_SUFFIX
        icon = _fetch_image_from_pollinations(prompt, (160, 160), seed)
        
        if icon:
            icon_name = f"{slug}-p{i}.webp"
            icon.convert("RGB").save(os.path.join(DOCS_DIR, "thumbs", icon_name), format="WEBP")
            icon_html = f'<img src="../thumbs/{icon_name}" style="width:56px;height:56px;border-radius:10px;object-fit:cover;">'
        else:
            icon_html = f'<div style="width:56px;height:56px;border-radius:10px;background:{accent}22;"></div>'
            
        cards.append(f'<div style="display:flex;gap:14px;margin:10px 0;background:#f7f8fa;padding:12px;border-radius:10px;">{icon_html}'
                     f'<div><b>{item.get("name","")}</b><p style="margin:0;color:#555;font-size:0.9em;">{item.get("description","")}</p></div></div>')
    return '<h2>추천 상품</h2>' + "".join(cards)

def save_post(article: dict):
    os.makedirs(POSTS_DIR, exist_ok=True)
    os.makedirs(os.path.join(DOCS_DIR, "thumbs"), exist_ok=True)
    
    category = article.get("category", "라이프스타일")
    theme = get_theme(category)
    slug = re.sub(r"[^\w\s-]", "", article["keyword"]).strip().replace(" ", "-") or "post"
    today = datetime.now().strftime("%Y-%m-%d")
    
    thumb_filename = f"{slug}-{today}.webp"
    generate_thumbnail(article["title"], os.path.join(DOCS_DIR, "thumbs", thumb_filename), theme, category)
    
    article = insert_content_image(article, slug)
    article["html_body"] += build_faq_section_html(article, theme["accent"])
    article["html_body"] += build_product_list_html(article, slug, theme["accent"])
    
    post_url = f"{SITE_URL}/posts/{slug}-{today}.html"
    thumb_url = f"{SITE_URL}/thumbs/{thumb_filename}"
    json_ld = build_json_ld(article, post_url, thumb_url, today)
    
    html = POST_TEMPLATE.format(
        title=article["title"], meta_description=article.get("meta_description",""),
        date=today, html_body=article["html_body"], thumb_filename=thumb_filename,
        canonical_url=post_url, json_ld=json_ld, ga_snippet=_ga_snippet(),
        adsense_snippet=_adsense_snippet(), font=theme["font"], font_family=theme["font"].split(":")[0].replace("+", " "),
        accent=theme["accent"], badge=theme["badge"], search_console_meta=_search_console_meta(),
        translate_widget=_translate_widget(), related_html=""
    )
    
    with open(os.path.join(POSTS_DIR, f"{slug}-{today}.html"), "w", encoding="utf-8") as f:
        f.write(html)
        
    return {"title": article["title"], "file": f"posts/{slug}-{today}.html", "thumb": f"thumbs/{thumb_filename}", "date": today}

def run():
    print("[시스템] 시작합니다.")
    fetch_and_update_trends_queue()
    title = get_title_from_args_or_queue()
    print(f"[타겟 키워드] {title}")
    
    os.makedirs(DOCS_DIR, exist_ok=True)
    
    # 더미 로고/배너 생성 (실제 운영 시 사전 제작본 교체 요망)
    Image.new("RGB", (512, 512), (15,23,42)).save(os.path.join(DOCS_DIR, "logo.webp"))
    Image.new("RGB", (1600, 420), (15,23,42)).save(os.path.join(DOCS_DIR, "banner.webp"))
    
    article = generate_article(title)
    post_meta = save_post(article)
    
    posts = []
    if os.path.exists(POSTS_JSON):
        with open(POSTS_JSON, "r", encoding="utf-8") as f:
            posts = json.load(f)
    posts.insert(0, post_meta)
    with open(POSTS_JSON, "w", encoding="utf-8") as f: json.dump(posts, f, ensure_ascii=False)
    
    hero_html = "".join([f'<a class="hero" href="{p["file"]}"><div class="pad"><h3>{p["title"]}</h3></div></a>' for p in posts[:5]])
    with open(os.path.join(DOCS_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(INDEX_TEMPLATE.format(
            site_title=SITE_TITLE, site_tagline=SITE_TAGLINE, fonts_url=_google_fonts_url(),
            hero_html=hero_html, blog_json_ld=build_blog_index_json_ld(posts),
            ga_snippet=_ga_snippet(), adsense_snippet=_adsense_snippet(),
            search_console_meta=_search_console_meta(), translate_widget=_translate_widget()
        ))
        
    rows = "".join([f'<tr><td>{p["date"]}</td><td><a href="{p["file"]}">{p["title"]}</a></td></tr>' for p in posts])
    with open(os.path.join(DOCS_DIR, "dashboard.html"), "w", encoding="utf-8") as f:
        f.write(DASHBOARD_TEMPLATE.format(post_count=len(posts), rows=rows))
        
    with open(os.path.join(DOCS_DIR, "sitemap.xml"), "w", encoding="utf-8") as f:
        f.write(SITEMAP_TEMPLATE.format(site_url=SITE_URL, url_entries="".join([f"<url><loc>{SITE_URL}/{p['file']}</loc></url>" for p in posts])))
        
    print("[시스템] 성공적으로 모든 과정을 완료했습니다.")

if __name__ == "__main__":
    try: run()
    except Exception as e:
        print(f"[전체 오류] {e}")
        sys.exit(1)

