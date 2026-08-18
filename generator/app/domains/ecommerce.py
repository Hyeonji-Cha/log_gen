'''
- 도메인 : 이커머스
- 목적   : 상품 조회, 검색, 장바구니, 주문, 결제, ... 관련 업무에 대한 로그 생성
'''
import random # 값을 선택, 생성시 확률적인 정보(선택) 제공하는 도구
from faker import Faker

# 해당 도메인에서 발생 가능한 이벤트 종류 정의
EVENTS  = ["product_view", "search", "add_to_cart", "checkout", "order_created", "payment_completed"]
# 가중치 부여하여 이벤트의 발생 빈도 조절 => 가중치 => 인사이트등 도메인 분석을 하여 설계 => 현재는 가정
WEIGHTS = [34, 20, 17, 9, 11, 9]

def generate(fake:Faker, *, timezone_name:str, environment:str, run_id:str) -> dict:
  # 1. 이벤트 타입 선택
  event_type = random.choices(EVENTS, weights=WEIGHTS, k=1)[0]
   # 2. 사용자 ID (임의 구성 => 실제라면 가입한  ID 혹은 내부 관리용 ID를 활용)
  user_id    = f"usr_{random.randint(100000, 999999)}" # 중복성 고려하여 랜덤 활용(uuid x)
  # 3. 요청 흐름을 구분하는 세션 ID (고유함)
  session_id = uuid.uuid4().hex[:20] # 중복되지 않는 해시값 20자리수 제공
  # 4. product_id 제품 아이디 중복 가능성 있음
  product_id = f"prod_{random.randint(100000,999999)}"
  # 5. 제품의 주문 수량
  quantity = random.choices([1,2,3,4], weights=[70,20,7,3], k=1)[0]

  return {
    # 공용 데이터
    "event_type"  : event_type,

    # 도메인별 커스텀 데이터
    "data": {
      "user_id": user_id,
      "session_id": session_id,
      "product_id" : product_id,
      "category" :random.choices(CATEGORIES),
      "quantity" : quantity,



    }
  }
