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

def generate(fake:Faker, *, timezone_name:str, envrionment:str, run_id:str) -> dict:
  # 1. 이벤트 타입 선택
  event_type = random.choices(EVENTS, weights=WEIGHTS, k=1)[0]
  return {
    "event_type"  : event_type
  }