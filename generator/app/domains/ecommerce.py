"""전자상거래 서비스에서 발생할 수 있는 사용자 행동 이벤트를 생성한다."""

# 이벤트 속성을 정해진 확률 또는 범위 안에서 무작위로 생성
import random
# 이벤트·세션 등 고유 식별자 생성
import uuid

# 이름·IP 등 현실적인 가짜 데이터 생성
from faker import Faker

# 공통 HTTP 상태·지연시간·기본 로그 생성 함수 가져오기
from app.common import http_status, latency_ms, make_base_event

# 생성할 수 있는 전자상거래 이벤트와 이벤트별 발생 가중치
# 조회·검색처럼 자주 발생하는 행동은 높게, 결제처럼 드문 행동은 낮게 설정한다.
EVENTS = ["product_view", "search", "add_to_cart", "checkout", "order_created", "payment_completed"]
WEIGHTS = [34, 20, 17, 9, 11, 9]
CATEGORIES = ["food", "fashion", "beauty", "electronics", "home", "sports"]


def generate(fake: Faker, *, timezone_name: str, environment: str, run_id: str) -> dict:
    # 1. 가중치에 따라 이벤트 종류 선택
    event_type = random.choices(EVENTS, weights=WEIGHTS, k=1)[0]

    # 2. 테스트용 사용자 ID 생성
    # 실제 서비스에서는 회원 시스템이 발급한 사용자 ID를 사용한다.
    user_id = f"usr_{random.randint(100000, 999999)}"

    # 3. 이벤트가 발생한 사용자 세션을 식별할 ID 생성
    session_id = uuid.uuid4().hex[:20]

    # 4. 이벤트의 대상이 되는 테스트용 상품 ID 생성
    product_id = f"prod_{random.randint(100000, 999999)}"

    # 5. 주문 수량 선택: 대부분 1개이며 큰 수량일수록 발생 확률이 낮다.
    quantity = random.choices([1, 2, 3, 4], weights=[70, 20, 7, 3], k=1)[0]

    # 6. 5,000원 이상 300,000원 미만 범위에서 100원 단위의 상품 단가 생성
    unit_price = random.randrange(5000, 300000, 100)

    # 이벤트별 HTTP 메서드, API 경로, 대표 지연 시간(ms) 정의
    routes = {
        # GET: 서버의 데이터를 조회하는 요청
        "product_view": ("GET", f"/api/products/{product_id}", 70),
        "search": ("GET", "/api/search", 95),
        # POST: 서버의 데이터나 상태를 변경하는 요청
        "add_to_cart": ("POST", "/api/cart/items", 110),
        "checkout": ("POST", "/api/checkout", 240),
        "order_created": ("POST", "/api/orders", 310),
        "payment_completed": ("POST", "/api/payments", 420),
    }

    # 선택된 이벤트에 해당하는 요청 정보 추출
    method, path, median_latency = routes[event_type]
    # 전자상거래 API의 성공·클라이언트 오류 비율을 반영해 상태코드 생성
    status = http_status(method, success=0.972, client_error=0.022)

    # 모든 전자상거래 이벤트에 공통으로 포함할 상세 데이터 구성
    data = {
        "user_id": user_id,
        "session_id": session_id,
        "product_id": product_id,
        "category": random.choice(CATEGORIES),
        "quantity": quantity,
        "unit_price": unit_price,
        "currency": "KRW",
        "campaign": random.choice([None, None, None, "summer_sale", "coupon", "winter_sale"]),
    }

    # 검색 이벤트에는 검색어와 조회된 상품 수 추가
    if event_type == "search":
        data.update({
            "keyword": fake.word(),
            "result_count": random.randint(0, 240),
        })

    # 공통 로그 스키마와 전자상거래 데이터를 합쳐 최종 이벤트 반환
    return make_base_event(
        fake=fake,
        domain="ecommerce",
        event_type=event_type,
        service_name="commerce-api",
        method=method,
        path=path,
        status_code=status,
        latency=latency_ms(median_latency),
        timezone_name=timezone_name,
        environment=environment,
        run_id=run_id,
        data=data,
    )
