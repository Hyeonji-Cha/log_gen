"""전자상거래 서비스에서 발생할 수 있는 사용자 행동 이벤트를 생성한다."""

import random # 이벤트 속성을 정해진 확률 또는 범위 안에서 무작위로 생성
from faker import Faker
import uuid
from app.common import http_status

# 생성할 수 있는 전자상거래 이벤트와 이벤트별 발생 가중치
# 조회·검색처럼 자주 발생하는 행동은 높게, 결제처럼 드문 행동은 낮게 설정한다.
EVENTS  = ["product_view", "search", "add_to_cart", "checkout", "order_created", "payment_completed"]
WEIGHTS = [34, 20, 17, 9, 11, 9]
CATEGORIES = ['food', 'fashion', 'beauty', 'electronics', 'home', 'sports']

def generate(fake:Faker, *, timezone_name:str, environment:str, run_id:str) -> dict:
  # 1. 가중치에 따라 이벤트 종류 선택
  event_type = random.choices(EVENTS, weights=WEIGHTS, k=1)[0]

  # 2. 테스트용 사용자 ID 생성
  # 실제 서비스에서는 회원 시스템이 발급한 사용자 ID를 사용한다.
  # 중복성을 고려하여 랜덤 활용 (UUID 사용 X)
  user_id    = f"usr_{random.randint(100000, 999999)}"

  # 3. 이벤트가 발생한 사용자 세션을 식별할 ID 생성
  session_id = uuid.uuid4().hex[:20]

  # 4. 이벤트의 대상이 되는 테스트용 상품 ID 생성 -> 중복 ID 생성될 수 있음
  product_id = f"prod_{random.randint(100000,999999)}"

  # 5. 주문 수량 선택: 대부분 1개이며 큰 수량일수록 발생 확률이 낮다.
  quantity = random.choices([1,2,3,4], weights=[70,20,7,3], k=1)[0]

  # 6. 5,000원 이상 300,000원 미만 범위에서 100원 단위의 상품 단가 생성
  unit_price = random.randrange(5000, 300000, 100)

  # 이벤트별 HTTP 메서드, API 경로, 대표 지연 시간(ms) 정의
  routes = {
    # GET: 데이터를 조회하기만 
    "product_view"      : ("GET", f"/api/products/{product_id}", 70),
    "search"            : ("GET", f"/api/search", 95),
    # POST: 서버의 데이터나 상태를 변경
    "add_to_cart"       : ("POST", f"/api/cart/items", 110),
    "checkout"          : ("POST", f"/api/checkout", 240),
    "order_created"     : ("POST", f"/api/orders", 310),
    "payment_completed" : ("POST", f"/api/payments", 420)
  }

  # 선택된 이벤트에 해당하는 요청 정보 추출
  method, path, median_latency = routes[ event_type ]
  # 응답코드 ( 400 이하이면 모두 성공, 그 이상이면 오류)
  status = http_status(method, success=0.9722, client_error=0.222)


# 이벤트 타입별 추가 데이터 구성
  if event_type =='search':
    data.update({
        "keyword": fake.word(),
        "result_count" : random.randint(0,240)
    })

  return {
    # 모든 도메인에서 공통으로 사용하는 이벤트 분류
    "event_type"  : event_type,

    # 전자상거래 이벤트에만 포함되는 상세 정보
    "data": {
      "user_id": user_id,
      "session_id": session_id,
      "product_id" : product_id,
      "category" :random.choices(CATEGORIES),
      "quantity" : quantity,
      "unit_price": unit_price,
      "currency"  : "KRW", # 상품 가격에 사용하는 통화
      "campaign"  : random.choices([None, None, None, "summer_sale", "coupon", "winter_sale"])

    }
  }
