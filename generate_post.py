import datetime
import random
import requests
import time

class KCultureBlogPipeline:
    def __init__(self, pexels_api_key, llm_api_key):
        self.pexels_api_key = pexels_api_key
        self.llm_api_key = llm_api_key
        self.max_daily_posts = 6
        
        # [결정사항 반영] 요일별 에버그린/블루오션 테마 및 랜덤 서브 키워드 뱅크
        self.topics = {
            0: {"theme": "산사 워케이션 실전 가이드", "keywords": ["템플스테이 워케이션", "원격 근무 사찰", "산사 와이파이", "사찰 장기 체류", "명상 워케이션"]}, # 월요일
            1: {"theme": "종가 내림음식 다이닝", "keywords": ["종갓집 예약", "안동 종가음식", "프라이빗 한식당", "내림음식 코스", "종부 레시피"]}, # 화요일
            2: {"theme": "사상체질 맞춤 한방 스파", "keywords": ["체질 맞춤 스파", "한방 족욕", "사상체질 웰니스", "약선 밀키트", "한방차 재료"]}, # 수요일
            3: {"theme": "K-공예 모던 인테리어", "keywords": ["소반 인테리어", "나전칠기 소품", "달항아리 배치", "옻칠 공예 체험", "전통 공방 원데이"]}, # 목요일
            4: {"theme": "숨은 명인 가양주 탐구", "keywords": ["소규모 양조장 투어", "가양주 홈텐딩", "전통주 구독", "이화주 키트", "지역 막걸리 안주"]}  # 금요일
        }

    def get_todays_topic(self):
        """오늘 요일에 맞는 테마와 랜덤 서브 키워드 반환 (주말은 5개 중 랜덤)"""
        today_weekday = datetime.datetime.now().weekday()
        
        if today_weekday > 4: # 토(5), 일(6)
            today_weekday = random.randint(0, 4)
            
        theme_data = self.topics[today_weekday]
        selected_keyword = random.choice(theme_data["keywords"])
        
        return theme_data["theme"], selected_keyword

    def _fetch_product_icon(self, keyword):
        """
        [수정/완성] Pexels API를 활용한 무료 스톡 이미지 및 저작권 출처 텍스트 확보
        기존에 끊어졌던 url 부분부터 완성된 로직입니다.
        """
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
        except Exception as e:
            print(f"[Error] 이미지 소싱 실패: {e}")
            return None

    def generate_content(self, theme, keyword):
        """LLM 프롬프트를 통한 콘텐츠 생성 (객관성, 출처, 최신화 강제)"""
        current_date = datetime.datetime.now().strftime("%Y년 %m월")
        
        prompt = f"""
        당신은 한국 문화 전문 블로거입니다. 다음 주제와 키워드를 바탕으로 SEO에 최적화된 블로그 포스팅을 작성하세요.
        - 메인 테마: {theme}
        - 타겟 키워드: {keyword}
        
        [필수 준수 규칙]
        1. 단순 정보가 아닌 경험, 실용성, 지속성을 강조하여 작성할 것.
        2. 가격, 시간, 예약 정보 등은 변동 가능성이 있으므로 반드시 '{current_date} 기준'임을 명시할 것.
        3. 하단에 "본 정보는 참고용이며, 자세한 사항은 공식 홈페이지(예: 한국관광공사 등) 확인을 권장합니다."라는 면책 조항(Disclaimer)을 추가할 것.
        4. 추측이나 확인되지 않은 사실은 절대 작성하지 말 것.
        5. 본문에 마크다운 표(Table)를 1개 이상 포함하여 비교/요약 정보를 제공할 것.
        """
        # 실제 환경에서는 self.llm_api_key를 사용하여 LLM(예: Gemini API) 호출 로직이 들어갑니다.
        # 여기서는 반환값을 Mock-up 처리합니다.
        mock_html_content = f"<h2>{theme}: {keyword} 완벽 가이드</h2><p>본문 내용...</p><table><tr><th>구분</th><th>내용</th></tr><tr><td>...</td><td>...</td></tr></table><p>{current_date} 기준 정보입니다.</p>"
        return mock_html_content

    def apply_ui_ux_widgets(self, content):
        """[UX 개선] 다국어 번역 위젯 및 본문 표(Table) 1.5배 확대 모달 스크립트 주입"""
        
        # 1. 구글 다국어 번역 위젯 (헤더용)
        translation_widget = """
        <div id="google_translate_element" style="text-align: right; margin-bottom: 20px;"></div>
        <script type="text/javascript">
            function googleTranslateElementInit() {
                new google.translate.TranslateElement({pageLanguage: 'ko', layout: google.translate.TranslateElement.InlineLayout.SIMPLE}, 'google_translate_element');
            }
        </script>
        <script type="text/javascript" src="//translate.google.com/translate_a/element.js?cb=googleTranslateElementInit"></script>
        """
        
        # 2. Table 모달 확대 스크립트 주입
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

    def run_daily_pipeline(self):
        """하루 최대 6회 발행을 수행하는 파이프라인 실행기"""
        posts_today = random.randint(3, self.max_daily_posts) # 3~6회 유동적 발행
        print(f"🚀 오늘({datetime.datetime.now().strftime('%A')})의 포스팅 목표: {posts_today}개")
        
        for i in range(posts_today):
            theme, keyword = self.get_todays_topic()
            print(f"[{i+1}/{posts_today}] 주제 픽업 완료: {theme} - {keyword}")
            
            # 1. 이미지 소싱 (영문 번역 키워드 사용 권장)
            image_data = self._fetch_product_icon("Korean " + keyword.split()[0])
            
            # 2. 본문 생성
            raw_content = self.generate_content(theme, keyword)
            
            # 3. 이미지 조립
            if image_data:
                image_html = f"<img src='{image_data['image_url']}' alt='{keyword}' style='max-width:100%;'>"
                raw_content = image_html + image_data['attribution'] + raw_content
                
            # 4. UX 위젯 적용
            final_html = self.apply_ui_ux_widgets(raw_content)
            
            # 5. 퍼블리싱 (Mock)
            print(f"✅ 포스팅 완료. (길이: {len(final_html)} bytes)\n")
            time.sleep(2) # API Rate Limit 방지 딜레이

if __name__ == "__main__":
    # API 키 세팅 후 실행
    PEXELS_API_KEY = "YOUR_PEXELS_API_KEY"
    LLM_API_KEY = "YOUR_LLM_API_KEY"
    
    pipeline = KCultureBlogPipeline(PEXELS_API_KEY, LLM_API_KEY)
    pipeline.run_daily_pipeline()
