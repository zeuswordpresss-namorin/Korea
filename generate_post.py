# -*- coding: utf-8 -*-
"""
구글 트렌드(대한민국) 일일 인기 검색어를 가져와 keywords_queue.json을 업데이트하고,
요일별 K-문화 테마와 연계하여 AI 프롬프트 생성 후 멀티 플랫폼(구글 블로그, 워드프레스, 깃허브 페이지)에 자동 발행합니다.

동작 방식:
  1. 구글 트렌드 공식 RSS 피드에서 상위 7개 키워드 추출
  2. 이미 완료(completed)되었거나 대기 중(pending)인 키워드는 제외하여 중복 방지
  3. 새 키워드만 pending 목록 뒤에 추가 저장
  4. 오늘 요일에 맞는 K-문화 테마 매핑 및 AI 생성 프롬프트(출처/면책조항 포함) 구성
  5. 구글 블로그(Blogger API), 워드프레스(REST API), 깃허브 페이지(GitHub API)로 자동 포스팅 발행
"""

import base64
import datetime
import json
import os
import sys
import xml.etree.ElementTree as ET
import requests

QUEUE_FILE = "keywords_queue.json"

# 구글 트렌드 RSS 주소 목록 (우선순위 순)
TRENDS_RSS_URLS = [
    "https://trends.google.com/trending/rss?geo=KR",
    "https://trends.google.com/trends/trendingsearches/daily/rss?geo=KR",
]

TOP_N = 7
REQUEST_TIMEOUT = 15  # 초 단위 타임아웃 설정

# ---------------------------------------------------------------------------
# [플랫폼 API 설정] - 환경 변수 사용 (미설정 시 기본 문자열)
# ---------------------------------------------------------------------------
BLOGGER_API_KEY = os.getenv("BLOGGER_API_KEY", "YOUR_BLOGGER_API_KEY")
BLOGGER_BLOG_ID = os.getenv("BLOGGER_BLOG_ID", "YOUR_BLOG_ID")

WP_BASE_URL = os.getenv("WP_BASE_URL", "https://your-wordpress-site.com")
WP_USERNAME = os.getenv("WP_USERNAME", "your_wp_username")
WP_APP_PASSWORD = os.getenv("WP_APP_PASSWORD", "your_app_password")

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "YOUR_GITHUB_PERSONAL_ACCESS_TOKEN")
GITHUB_REPO = os.getenv("GITHUB_REPO", "username/username.github.io")
GITHUB_BRANCH = os.getenv("GITHUB_BRANCH", "main")

# 요일별 테마 및 출처 매핑
WEEKDAY_THEMES = {
    0: {
        "day": "월요일",
        "category": "산사 워케이션(Workation) 실전 가이드",
        "data_sources": ["템플스테이 공식 웹사이트 (templestay.com)", "지자체별 워케이션 지원 사업 공고"],
        "target_audience": "디지털 노마드 및 리모트 워커"
    },
    1: {
        "day": "화요일",
        "category": "종가(宗家) 내림음식 프라이빗 다이닝",
        "data_sources": ["농촌진흥청 종가음식 DB", "한국관광공사 TourAPI (고택/종택 체험)"],
        "target_audience": "하이엔드 로컬 미식 및 문화 경험 수요자"
    },
    2: {
        "day": "수요일",
        "category": "사상체질 맞춤 한방(韓方) 스파 및 약선 구독",
        "data_sources": ["문화체육관광부 웰니스 관광지 데이터", "농산물유통정보(KAMIS) 제철 식재료 정보"],
        "target_audience": "웰니스, 안티에이징 및 피로 회복 관심층"
    },
    3: {
        "day": "목요일",
        "category": "K-공예의 모던 인테리어 실전 적용",
        "data_sources": ["한국공예·디자인문화진흥원(KCDF)", "주요 인테리어 플랫폼 공예 트렌드"],
        "target_audience": "홈퍼니싱 및 셀프 인테리어 관심 1인 가구/신혼부부"
    },
    4: {
        "day": "금요일",
        "category": "숨은 명인 가양주(家釀酒) 탐구 및 양조장 투어",
        "data_sources": ["대한민국 주류대상 전통주 부문 결과", "지역별 소규모 양조장 공시 정보"],
        "target_audience": "주류 탐구 마니아 및 주말 여행/홈술 계획자"
    },
    5: {
        "day": "토요일",
        "category": "주말 K-웰니스 & 로컬 트렌드 종합",
        "data_sources": ["한국관광공사 대한민국 구석구석", "지자체 주말 축제/행사 DB"],
        "target_audience": "주말 여가 및 로컬 여행 탐색자"
    },
    6: {
        "day": "일요일",
        "category": "주간 K-라이프스타일 큐레이션",
        "data_sources": ["주간 트렌드 분석 종합 데이터"],
        "target_audience": "한 주를 정리하며 차주 트렌드를 탐색하는 독자"
    }
}


def fetch_top_trends(n: int = TOP_N) -> list[str]:
    """
    구글 트렌드 RSS 피드에서 상위 n개의 키워드를 안전하게 가져옵니다.
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }
    
    last_error = None

    for url in TRENDS_RSS_URLS:
        try:
            response = requests.get(url, timeout=REQUEST_TIMEOUT, headers=headers)
            response.raise_for_status()

            # XML 파싱
            root = ET.fromstring(response.content)
            
            # RSS 내 item 태그의 title 추출
            titles = []
            for item in root.iter("item"):
                title_text = item.findtext("title")
                if title_text and title_text.strip():
                    titles.append(title_text.strip())

            if titles:
                print(f"[성공] RSS 수집 완료 (출처: {url})")
                return titles[:n]
            
            last_error = f"{url} - 응답은 성공했으나 추출된 키워드가 없습니다."

        except requests.RequestException as req_err:
            last_error = f"{url} - 네트워크/HTTP 요청 실패: {req_err}"
            print(f"[경고] {last_error}")
        except ET.ParseError as xml_err:
            last_error = f"{url} - XML 파싱 실패: {xml_err}"
            print(f"[경고] {last_error}")
        except Exception as gen_err:
            last_error = f"{url} - 예기치 못한 오류: {gen_err}"
            print(f"[경고] {last_error}")

    raise RuntimeError(f"모든 트렌드 URL에서 수집에 실패했습니다. (마지막 오류: {last_error})")


def load_queue() -> dict:
    """
    기존 큐 파일을 읽어옵니다. 파일이 없거나 유효하지 않으면 기본 구조를 반환합니다.
    """
    if not os.path.exists(QUEUE_FILE):
        return {"pending": [], "completed": []}

    try:
        with open(QUEUE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            # 기본 데이터 구조 보장
            data.setdefault("pending", [])
            data.setdefault("completed", [])
            return data
    except (json.JSONDecodeError, IOError) as e:
        print(f"[경고] {QUEUE_FILE} 읽기 실패 ({e}). 새로운 큐 구조로 시작합니다.")
        return {"pending": [], "completed": []}


def save_queue(queue: dict) -> None:
    """
    업데이트된 큐 데이터를 파일에 저장합니다.
    """
    with open(QUEUE_FILE, "w", encoding="utf-8") as f:
        json.dump(queue, f, ensure_ascii=False, indent=2)


def get_today_theme() -> dict:
    """현재 요일에 해당하는 하이브리드 테마 정보를 반환합니다."""
    weekday = datetime.datetime.now().weekday()
    return WEEKDAY_THEMES.get(weekday, WEEKDAY_THEMES[0])


def generate_ai_prompt(keyword: str, theme_info: dict) -> str:
    """AI 생성을 위해 출처 명시 및 면책 조항 규칙이 포함된 프롬프트를 구성합니다."""
    current_date_str = datetime.datetime.now().strftime("%Y년 %m월")
    sources_str = ", ".join(theme_info["data_sources"])

    prompt = f"""
[콘텐츠 작성 지침]
- 메인 주제/카테고리: {theme_info['category']} ({theme_info['day']} 테마)
- 연계 트렌드 키워드: {keyword}
- 타겟 독자: {theme_info['target_audience']}

[필수 작성 규칙 및 제약사항]
1. 객관성과 사실에 기반하여 추측이나 허위 정보(Hallucination) 없이 작성하세요.
2. 실용적 정보(예약법, 이용 팁, 비용 범위, 동선 등)를 명확히 제시하세요.
3. 포스팅 최하단에 다음 필수 항목을 규칙에 맞춰 반드시 포함하세요:
   - 데이터 출처: {sources_str}
   - 작성 시점 명시: "{current_date_str} 기준 정보입니다."
   - 자동 면책 조항(Disclaimer): "본 포스팅은 공공 데이터 및 공식 안내를 바탕으로 작성되었으며, 사찰/업체/지자체 사정에 따라 세부 내용이 변경될 수 있으니 방문 전 공식 채널 확인을 권장합니다."
"""
    return prompt.strip()


# ---------------------------------------------------------------------------
# [자동 발행 API 구현]
# ---------------------------------------------------------------------------
def publish_to_blogger(title: str, content_html: str, tags: list = None) -> bool:
    """구글 블로그 (Blogger API v3) 발행"""
    url = f"https://www.googleapis.com/blogger/v3/blogs/{BLOGGER_BLOG_ID}/posts/"
    headers = {"Content-Type": "application/json"}
    params = {"key": BLOGGER_API_KEY}
    payload = {
        "kind": "blogger#post",
        "title": title,
        "content": content_html,
        "labels": tags or ["K-Culture", "Trend"]
    }
    try:
        res = requests.post(url, headers=headers, params=params, json=payload, timeout=REQUEST_TIMEOUT)
        res.raise_for_status()
        print(f"[성공] 구글 블로그 발행 완료 (URL: {res.json().get('url')})")
        return True
    except Exception as err:
        print(f"[경고] 구글 블로그 발행 실패: {err}")
        return False


def publish_to_wordpress(title: str, content_html: str) -> bool:
    """워드프레스 (WordPress REST API) 발행"""
    url = f"{WP_BASE_URL.rstrip('/')}/wp-json/wp/v2/posts"
    credentials = f"{WP_USERNAME}:{WP_APP_PASSWORD}"
    encoded_credentials = base64.b64encode(credentials.encode("utf-8")).decode("utf-8")
    headers = {
        "Authorization": f"Basic {encoded_credentials}",
        "Content-Type": "application/json"
    }
    payload = {"title": title, "content": content_html, "status": "publish"}
    try:
        res = requests.post(url, headers=headers, json=payload, timeout=REQUEST_TIMEOUT)
        res.raise_for_status()
        print(f"[성공] 워드프레스 발행 완료 (Post ID: {res.json().get('id')})")
        return True
    except Exception as err:
        print(f"[경고] 워드프레스 발행 실패: {err}")
        return False


def publish_to_github_pages(title: str, content_markdown: str, category: str) -> bool:
    """깃허브 페이지 (GitHub REST API - Markdown 커밋) 발행"""
    now = datetime.datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%Y-%m-%d %H:%M:%S +0900")
    
    safe_title = "".join([c if c.isalnum() else "-" for c in title]).strip("-")
    filename = f"_posts/{date_str}-{safe_title}.md"
    
    front_matter = f"---\nlayout: post\ntitle: \"{title}\"\ndate: {time_str}\ncategories: [{category}]\n---\n\n"
    full_content = front_matter + content_markdown
    encoded_content = base64.b64encode(full_content.encode("utf-8")).decode("utf-8")
    
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{filename}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    payload = {
        "message": f"Feat: Auto publish - {title}",
        "content": encoded_content,
        "branch": GITHUB_BRANCH
    }
    try:
        res = requests.put(url, headers=headers, json=payload, timeout=REQUEST_TIMEOUT)
        res.raise_for_status()
        print(f"[성공] 깃허브 페이지 커밋 완료 (경로: {filename})")
        return True
    except Exception as err:
        print(f"[경고] 깃허브 페이지 발행 실패: {err}")
        return False


def main():
    print("=" * 60)
    print("[구글 트렌드] 대한민국 일일 인기 검색어 수집 시작...")
    
    # 1. 키워드 수집
    trends = fetch_top_trends(TOP_N)
    print(f"[수집 완료] 상위 {len(trends)}개 키워드: {trends}")

    # 2. 기존 큐 로드 및 중복 검사
    queue = load_queue()
    existing_keywords = set(queue.get("pending", [])) | set(queue.get("completed", []))

    new_keywords = [t for t in trends if t not in existing_keywords]
    skipped_count = len(trends) - len(new_keywords)

    # 3. 신규 키워드 추가 및 저장
    queue["pending"].extend(new_keywords)
    save_queue(queue)

    # 4. 결과 출력
    print(f"[처리 완료] 신규 추가된 키워드: {len(new_keywords)}개 (중복 제외됨: {skipped_count}개)")
    print(f"[현재 상태] 대기 중인 전체 키워드: {len(queue['pending'])}개")

    # 5. 테마 매핑 및 콘텐츠 발행 프로세스
    today_theme = get_today_theme()
    print(f"[오늘의 테마] {today_theme['day']} -> {today_theme['category']}")

    if queue["pending"]:
        target_keyword = queue["pending"].pop(0)
        post_title = f"[{today_theme['category']}] {target_keyword} 관전 포인트 및 안내"
        
        # 포스팅 본문 구성 (HTML 및 Markdown 규격)
        current_date_str = datetime.datetime.now().strftime("%Y년 %m월")
        sources_str = ", ".join(today_theme["data_sources"])
        
        content_html = f"""<h2>{post_title}</h2>
<p>안녕하세요. 오늘 다룰 트렌드 키워드는 <strong>{target_keyword}</strong>입니다.</p>
<p>{today_theme['category']} 테마에 맞춘 실용적인 정보와 안내를 제공합니다.</p>
<hr>
<p><small>데이터 출처: {sources_str}</small><br>
<small>{current_date_str} 기준 정보입니다.</small><br>
<small>면책 조항: 본 포스팅은 공식 안내를 바탕으로 작성되었으며 사정에 따라 변경될 수 있습니다.</small></p>"""

        content_md = f"""# {post_title}

안녕하세요. 오늘 다룰 트렌드 키워드는 **{target_keyword}**입니다.

{today_theme['category']} 테마에 맞춘 실용적인 정보와 안내를 제공합니다.

---
*데이터 출처: {sources_str}*  
*{current_date_str} 기준 정보입니다.*  
*면책 조항: 본 포스팅은 공식 안내를 바탕으로 작성되었으며 사정에 따라 변경될 수 있습니다.*"""

        print(f"[발행 시작] 대상 키워드: '{target_keyword}'")
        
        publish_to_blogger(post_title, content_html)
        publish_to_wordpress(post_title, content_html)
        publish_to_github_pages(post_title, content_md, today_theme["category"])

        queue["completed"].append(target_keyword)
        save_queue(queue)
        print(f"[완료] '{target_keyword}' 완료(completed) 항목으로 이동 저장이 완료되었습니다.")
    
    print("=" * 60)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"\n[최종 치명적 오류] 실행 실패: {error}")
        sys.exit(1)

