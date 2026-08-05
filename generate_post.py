import os
import datetime
import random
import requests
import time
import json

class KCultureBlogPipeline:
    def __init__(self):
        # 1. GitHub Secrets 환경 변수 연동 (보안 및 401 에러 해결)
        self.pexels_api_key = os.environ.get("PEXELS_API_KEY", "")
        self.llm_api_key = os.environ.get("LLM_API_KEY", "")
        
        # WordPress 인증 정보
        self.wp_url = os.environ.get("WP_URL", "")
        self.wp_user = os.environ.get("WP_USER", "")
        self.wp_pass = os.environ.get("WP_APP_PASS", "")
        
        # Google Blogger 인증 정보
        self.blogger_id = os.environ.get("BLOGGER_ID", "")
        self.google_access_token = os.environ.get("GOOGLE_ACCESS_TOKEN", "")

        self.max_daily_posts = 6
        
        # 요일별 에버그린/블루오션 테마
        self.topics = {
            0: {"theme": "산사 워케이션 실전 가이드", "keywords": ["템플스테이 워케이션", "원격 근무 사찰", "산사 와이파이", "사찰 장기 체류", "명상 워케이션"]},
            1: {"theme": "종가 내림음식 다이닝", "keywords": ["종갓집 예약", "안동 종가음식", "프라이빗 한식당", "내림음식 코스", "종부 레시피"]},
            2: {"theme": "사상체질 맞춤 한방 스파", "keywords": ["체질 맞춤 스파", "한방 족욕", "사상체질 웰니스", "약선 밀키트", "한방차 재료"]},
            3: {"theme": "K-공예 모던 인테리어", "keywords": ["소반 인테리어", "나전칠기 소품", "달항아리 배치", "옻칠 공예 체험", "전통 공방 원데이"]},
            4: {"theme": "숨은 명인 가양주 탐구", "keywords": ["소규모 양조장 투어", "가양주 홈텐딩", "전통주 구독", "이화주 키트", "지역 막걸리 안주"]}
        }

    def get_todays_topic(self):
        today_weekday = datetime.datetime.now().weekday()
        if today_weekday > 4: 
            today_weekday = random.randint(0, 4)
            
        theme_data = self.topics[today_weekday]
        selected_keyword = random.choice(theme_data["keywords"])
        return theme_data["theme"], selected_keyword

    def _fetch_product_icon(self, keyword):
        if not self.pexels_api_key:
            print("[Error] PEXELS_API_KEY가 설정되지 않았습니다.")
            return None
            
        url = f"https://api.pexels.com/v1/search?query={keyword}&per_page=1"
        headers = {"Authorization": self.pexels_api_key}
        
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()
            
            if data.get('photos'):
                photo = data['photos'][0]
                return {
                    "image_url": photo['src']['large'],
                    "attribution": f"<p style='font-size: 0.8em; color: gray;'>Photo by <a href='{photo['photographer_url']}'>{photo['photographer']}</a> on Pexels</p>"
                }
            return None
        except requests.exceptions.RequestException as e:
            print(f"[Error] 이미지 소싱 실패: {e}")
            return None

    def generate_content(self, theme, keyword):
        current_date = datetime.datetime.now().strftime("%Y년 %m월")
        mock_html_content = f"<h2>{theme}: {keyword} 완벽 가이드</h2><p>본문 내용...</p><table><tr><th>구분</th><th>내용</th></tr><tr><td>...</td><td>...</td></tr></table><p>{current_date} 기준 정보입니다. 자세한 사항은 공식 홈페이지 확인을 권장합니다.</p>"
        return mock_html_content

    def apply_ui_ux_widgets(self, content):
        translation_widget = """
        <div id="google_translate_element" style="text-align: right; margin-bottom: 20px;"></div>
        <script type="text/javascript">
            function googleTranslateElementInit() {
                new google.translate.TranslateElement({pageLanguage: 'ko', layout: google.translate.TranslateElement.InlineLayout.SIMPLE}, 'google_translate_element');
            }
        </script>
        <script type="text/javascript" src="//translate.google.com/translate_a/element.js?cb=googleTranslateElementInit"></script>
        """
        table_modal_script = """
        <script>
            document.querySelectorAll('table').forEach(table => {
                table.style.cursor = 'pointer';
                table.title = '클릭하여 확대 보기';
                table.addEventListener('click', function() {
                    const modal = document.createElement('div');
                    modal.style.position = 'fixed'; modal.style.top = '0'; modal.style.left = '0';
                    modal.style.width = '100%'; modal.style.height = '100%';
                    modal.style.backgroundColor = 'rgba(0,0,0,0.8)'; modal.style.zIndex = '9999';
                    modal.style.display = 'flex'; modal.style.justifyContent = 'center'; modal.style.alignItems = 'center';
                    const clonedTable = this.cloneNode(true);
                    clonedTable.style.transform = 'scale(1.5)';
                    clonedTable.style.backgroundColor = 'white';
                    modal.appendChild(clonedTable);
                    modal.addEventListener('click', () => document.body.removeChild(modal));
                    document.body.appendChild(modal);
                });
            });
        </script>
        """
        return translation_widget + content + table_modal_script

    # --- 신규 추가: 플랫폼별 실제 발행 모듈 ---

    def publish_to_github_pages(self, title, content):
        """GitHub Pages용 마크다운 파일 생성 (이후 GitHub Actions 커밋 스텝에서 푸시됨)"""
        date_str = datetime.datetime.now().strftime("%Y-%m-%d")
        safe_title = title.replace(" ", "-").replace("/", "")
        filename = f"_posts/{date_str}-{safe_title}.md"
        
        os.makedirs("_posts", exist_ok=True)
        front_matter = f"---\nlayout: post\ntitle: \"{title}\"\ndate: {date_str}\n---\n\n"
        
        try:
            with open(filename, "w", encoding="utf-8") as f:
                f.write(front_matter + content)
            print(f"✅ GitHub Pages 파일 생성 완료: {filename}")
        except Exception as e:
            print(f"❌ GitHub Pages 파일 생성 실패: {e}")

    def publish_to_wordpress(self, title, content):
        """WordPress REST API를 통한 발행"""
        if not all([self.wp_url, self.wp_user, self.wp_pass]):
            print("⚠️ WordPress 인증 정보 누락. 발행 생략.")
            return

        api_url = f"{self.wp_url}/wp-json/wp/v2/posts"
        data = {"title": title, "content": content, "status": "publish"}
        try:
            response = requests.post(api_url, auth=(self.wp_user, self.wp_pass), json=data)
            response.raise_for_status()
            print(f"✅ WordPress 발행 완료: {response.json().get('link')}")
        except Exception as e:
            print(f"❌ WordPress 발행 실패: {e}")

    def publish_to_blogger(self, title, content):
        """Google Blogger API를 통한 발행"""
        if not all([self.blogger_id, self.google_access_token]):
            print("⚠️ Google Blogger 인증 정보 누락. 발행 생략.")
            return

        api_url = f"https://www.googleapis.com/blogger/v3/blogs/{self.blogger_id}/posts/"
        headers = {
            "Authorization": f"Bearer {self.google_access_token}",
            "Content-Type": "application/json"
        }
        data = {"kind": "blogger#post", "title": title, "content": content}
        
        try:
            response = requests.post(api_url, headers=headers, json=data)
            response.raise_for_status()
            print(f"✅ Google Blogger 발행 완료: {response.json().get('url')}")
        except Exception as e:
            print(f"❌ Google Blogger 발행 실패: {e}")

    # ------------------------------------------

    def run_daily_pipeline(self):
        posts_today = random.randint(3, self.max_daily_posts)
        print(f"🚀 오늘({datetime.datetime.now().strftime('%A')})의 포스팅 목표: {posts_today}개")
        
        for i in range(posts_today):
            theme, keyword = self.get_todays_topic()
            print(f"\n[{i+1}/{posts_today}] 주제 픽업 완료: {theme} - {keyword}")
            
            image_data = self._fetch_product_icon("Korean " + keyword.split()[0])
            raw_content = self.generate_content(theme, keyword)
            
            if image_data:
                image_html = f"<img src='{image_data['image_url']}' alt='{keyword}' style='max-width:100%;'>"
                raw_content = image_html + image_data['attribution'] + raw_content
                
            final_html = self.apply_ui_ux_widgets(raw_content)
            post_title = f"{theme}: {keyword} 완벽 가이드"
            
            # 3사 플랫폼 동시 발행 실행
            self.publish_to_github_pages(post_title, final_html)
            self.publish_to_wordpress(post_title, final_html)
            self.publish_to_blogger(post_title, final_html)
            
            time.sleep(2) # API Rate Limit 방지

if __name__ == "__main__":
    pipeline = KCultureBlogPipeline()
    pipeline.run_daily_pipeline()

