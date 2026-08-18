# 공통 로그 필드, HTTP 상태코드, 지연시간 등을 생성하는 공용 함수 모음

# 타입 힌트 평가를 지연해 최신 타입 문법을 안정적으로 사용
from __future__ import annotations

# 로그 지연시간 계산에 로그 함수 사용
import math
# 이벤트 종류·값·상태 등을 확률적으로 생성
import random
# 이벤트·세션·거래 등 고유 식별자 생성
import uuid
# 현재 시간과 UTC 시간 생성
from datetime import datetime, timezone
# 값의 타입이 다양한 딕셔너리 타입 힌트에 사용
from typing import Any
# Asia/Seoul 같은 IANA 시간대 적용
from zoneinfo import ZoneInfo

# 이름·IP 등 현실적인 가짜 데이터 생성
from faker import Faker


# 실제 서비스처럼 보이도록 사용할 User-Agent 후보 목록
# https://useragents.io/
# https://gist.github.com/pzb/b4b6f57144aea7827ae4
USER_AGENTS = [
    "Mozilla/5.0 Chrome/151.0 Windows/10",
    "Mozilla/5.0 Safari/605.1 iPhone",
    "Mozilla/5.0 Chrome/151.0 Android/15",
    "WhitelabelApp/4.8.1 iOS",
    "WhitelabelApp/4.8.1 Android",
]


# 지정한 시간대의 현재 시간을 ISO 8601 문자열로 반환
def iso_now(tz_name: str) -> str:
    # 지정 시간대의 현재 시각을 밀리초 단위 ISO 문자열로 반환
    return datetime.now(ZoneInfo(tz_name)).isoformat(timespec="milliseconds")


# 로그정규분포를 이용해 현실적인 응답 지연시간을 생성
# 0.45: 로그정규분포에서 값들이 중앙값 주변에 얼마나 퍼질지 결정
# 실제 API처럼 대부분은 빠르고 가끔 느린 요청이 발생하는 긴 꼬리(long-tail)를 만들 수 있음
# 최소 2ms ~ 최대 10,000ms(10초) 범위로 제한
def latency_ms(median: float, sigma: float = 0.45, minimum: int = 2, maximum: int = 10000) -> int:
    # 중앙값 주변에 긴 꼬리를 가진 로그정규분포 지연시간 생성
    value = random.lognormvariate(math.log(max(median, 1)), sigma)
    # 지연시간이 최소·최대 범위를 벗어나지 않도록 제한
    return int(max(minimum, min(value, maximum)))


# 성공·클라이언트 오류·서버 오류 비율에 따라 HTTP 상태코드 생성
# http_status(method, success=0.972, client_error=0.022)
def http_status(method: str, success: float = 0.965, client_error: float = 0.027) -> int:
    # 0~1 난수를 뽑아 성공/오류 구간을 결정
    r = random.random()
    if r < success:
        # HTTP 메서드 비교를 위해 대문자로 표준화
        method = method.upper()
        if method == "GET":
            return 200
        if method == "POST":
            return random.choices([200, 201, 202, 204], weights=[48, 32, 15, 5], k=1)[0]
        if method in {"PUT", "PATCH"}:
            return random.choices([200, 204], weights=[80, 20], k=1)[0]
        if method == "DELETE":
            return random.choices([200, 204], weights=[25, 75], k=1)[0]
        return 200
    if r < success + client_error:
        return random.choices([400, 401, 403, 404, 409, 429], weights=[18, 14, 12, 24, 14, 18], k=1)[0]
    return random.choices([500, 502, 503, 504], weights=[45, 18, 27, 10], k=1)[0]


# 모든 도메인이 공통으로 사용하는 기본 로그 구조 생성
def make_base_event(
    *,
    fake: Faker,
    domain: str,
    event_type: str,
    service_name: str,
    method: str,
    path: str,
    status_code: int,
    latency: int,
    timezone_name: str,
    environment: str,
    run_id: str,
    data: dict[str, Any],
) -> dict[str, Any]:
    # 쓰기 요청은 더 큰 요청 본문을 갖도록 요청 바이트 크기 생성
    request_bytes = random.randint(120, 4800) if method in {"POST", "PUT", "PATCH"} else random.randint(0, 800)
    # 응답 크기를 임의의 바이트 값으로 생성
    response_bytes = random.randint(180, 18000)

    # 공통 스키마를 가진 로그 이벤트 딕셔너리 반환
    return {
        "schema_version": "1.0",
        "record_type": "application_log",
        "event_id": str(uuid.uuid4()),
        # 나의 사용자 요청(Request)이 시작되어 여러 서버와 서비스를 거쳐 완료될 때까지, 그 전체 요청 흐름을 하나로 묶어 추적하기 위해 부여하는 고유한 식별자
        "trace_id": uuid.uuid4().hex,
        # 생성 실행 식별자, manual
        "run_id": run_id,
        # 어떤 사건(Event)이나 행동이 발생한 시각(일시)'을 나타내는 ISO 8601 형식의 문자열, 예: 2023-08-15T14:30:00.123+09:00
        # timezone_name => Asia/Seoul
        "occurred_at": iso_now(timezone_name),
        # 협정 세계시(UTC) 기준으로 생성된 시각(일시)'을 나타내는 ISO 8601 형식의 문자열, 예: 2023-08-15T05:30:00.123Z
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "domain": domain,
        "event_type": event_type,
        "service": {
            # commerce-api, finance-api, game-api, factory-ingestion-api
            "name": service_name,
            "environment": environment,
            # sim- : 시뮬레이션(Simulation)의 약자
            "instance_id": f"sim-{random.randint(1, 24):02d}",
        },
        "client": {
            "ip": fake.ipv4_public(),
            "user_agent": random.choice(USER_AGENTS),
            "device_id": uuid.uuid4().hex[:16],
        },
        "request": {
            "method": method,
            "path": path,
            "request_bytes": request_bytes,
        },
        "response": {
            "status_code": status_code,
            "latency_ms": latency,
            "response_bytes": response_bytes,
        },
        "data": data,
    }