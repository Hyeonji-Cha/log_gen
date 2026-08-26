# -*- coding: utf-8 -*-
# 이 파일이 UTF-8 인코딩을 사용한다는 것을 명시한다. 한글 주석과 JSON 문자열을 안전하게 다루기 위한 설정이다.

"""Bronze(JSON 문자열) -> Silver(JSON 문자열) 공통 정제 로직.

도메인별 상세 검증(ecommerce/finance/game/smartfactory)은 다음 단계에서
이 모듈에 규칙을 추가하도록 분리했다.
"""
# 이 모듈은 Flink 자체 실행 코드와 데이터 정제 규칙을 분리하기 위해 만든 공통 변환 모듈이다.
# 현재는 모든 도메인에 공통으로 적용할 수 있는 최소 Silver 정제만 수행한다.
# 이후 도메인별 필수 필드, 타입, enum, 범위 검증 등을 이 파일 또는 하위 모듈에 확장할 수 있다.

from __future__ import annotations
# 타입 힌트를 즉시 평가하지 않고 지연 평가하여 Python 버전 간 타입 힌트 호환성을 높인다.

import json
# 입력 문자열을 JSON 객체로 파싱하고 정제 결과를 다시 JSON 문자열로 직렬화하기 위해 사용한다.

from datetime import datetime, timezone
# Silver 처리 시각을 UTC 기준 ISO-8601 문자열로 기록하기 위해 datetime과 timezone을 사용한다.

from typing import Any, Optional
# Any는 입력 payload가 문자열, bytes 등 다양한 타입일 수 있음을 표현한다.
# Optional[str]은 함수가 정상 처리 시 문자열, 실패 시 None을 반환함을 타입으로 나타낸다.


SILVER_SCHEMA_VERSION = "1.0"
# 현재 Silver 데이터 구조의 버전을 상수로 관리한다.
# 이후 Silver 필드 구조나 정제 규칙이 크게 바뀌면 1.1, 2.0 등으로 변경하여 데이터 계보를 추적할 수 있다.

REJECT_SCHEMA_VERSION = "1.0"
# Reject 데이터 구조의 버전을 별도로 관리하여 Silver 스키마와 독립적으로 변경 이력을 추적한다.


def _parse_payload(payload: Any):
    # Silver와 Reject 처리에서 공통으로 사용할 JSON 기본 검사를 수행한다.
    # 반환값은 파싱된 이벤트와 Reject 사유이며, 정상인 경우 Reject 사유는 None이다.

    if payload is None:
        # 입력 데이터 자체가 없는 경우 파싱할 수 없으므로 Reject 사유를 반환한다.
        return None, "payload_null"

    if isinstance(payload, bytes):
        # bytes 입력은 JSON 파싱 전에 UTF-8 문자열로 변환한다.
        try:
            payload = payload.decode("utf-8")
        except UnicodeDecodeError:
            # UTF-8로 해석할 수 없는 원본은 별도 Reject 대상으로 분류한다.
            return None, "invalid_utf8"

    if not isinstance(payload, str):
        # 문자열이 아닌 입력도 기존 정제 방식과 동일하게 문자열로 변환한 후 파싱한다.
        payload = str(payload)

    try:
        # JSON 문자열을 Python 객체로 변환한다.
        event = json.loads(payload)
    except (json.JSONDecodeError, TypeError, ValueError):
        # JSON 문법이나 입력값이 올바르지 않으면 파싱 실패 사유를 반환한다.
        return None, "invalid_json"

    if not isinstance(event, dict):
        # 유효한 JSON이어도 최상위 구조가 Object가 아니면 이벤트로 처리하지 않는다.
        return None, "no_json_object"

    # 기본 검사를 통과한 JSON Object와 정상 상태를 반환한다.
    return event, None


def _validate_event(event: dict) -> Optional[str]:
    # JSON 문법 검사 이후 이벤트 내부의 공통 필드와 데이터 품질을 검사한다.
    required_fields = ["event_id", "domain", "occurred_at"]

    for field in required_fields:
        # 필수 필드가 없거나 값이 null이면 각각 구분된 Reject 사유를 반환한다.
        if field not in event:
            return f"missing_required_field:{field}"
        if event[field] is None:
            return f"null_required_field:{field}"

    # 공통 필수 필드는 모두 문자열 타입이어야 한다.
    if not isinstance(event["event_id"], str):
        return "wrong_type:event_id"
    if not isinstance(event["domain"], str):
        return "wrong_type:domain"
    if not isinstance(event["occurred_at"], str):
        return "wrong_type:occurred_at"

    try:
        # UTC를 나타내는 Z 접미사를 +00:00으로 바꿔 ISO-8601 형식인지 확인한다.
        datetime.fromisoformat(event["occurred_at"].replace("Z", "+00:00"))
    except (ValueError, TypeError, AttributeError):
        return "invalid_timestamp"

    if "latency_ms" in event:
        # 선택 필드인 latency_ms가 존재하면 null, 숫자 타입, 음수 여부를 검사한다.
        latency = event["latency_ms"]
        if latency is None:
            return "null_latency"
        # bool은 Python에서 int의 하위 타입이므로 유효한 숫자로 처리되지 않도록 명시적으로 제외한다.
        if isinstance(latency, bool) or not isinstance(latency, (int, float)):
            return "wrong_type:latency_ms"
        if latency < 0:
            return "negative_latency"

    # 모든 데이터 품질 검사를 통과한 정상 이벤트다.
    return None


def clean_event_payload(payload: Any) -> Optional[str]:
    # Raw Kinesis에서 전달된 하나의 레코드를 받아 Silver용 JSON 문자열로 정제하는 핵심 함수다.
    # 정상 레코드는 str을 반환하고 잘못된 레코드는 None을 반환한다.

    """Raw Kinesis payload를 Silver용 JSON 문자열로 변환한다.

    현재 1차 Silver 규칙
    1. UTF-8 JSON이어야 한다.
    2. 최상위 구조가 JSON Object(dict)여야 한다.
    3. 최상위 null 필드는 제거한다.
    4. Silver 처리 메타데이터를 추가한다.

    잘못된 레코드는 None을 반환하여 Silver Stream에서 제외한다.
    원본은 이미 S3 Bronze(raw/)에 보존되어 있으므로 유실되지 않는다.
    """
    # 위 docstring은 현재 Silver 계층에서 적용하는 최소 정제 정책을 명확하게 정의한다.
    # 중요한 점은 "잘못된 데이터를 삭제한다"가 아니라 Bronze에는 원본을 보존하고 Silver에서만 제외한다는 것이다.

    if payload is None:
        # 입력 자체가 없으면 JSON으로 처리할 데이터가 없으므로 즉시 실패 처리한다.

        return None
        # None은 main.py의 Flink SQL에서 SQL NULL로 변환되고 WHERE 조건에 의해 Silver Stream에서 제외된다.

    if isinstance(payload, bytes):
        # Kinesis 또는 다른 입력 경로에서 payload가 bytes 형태로 전달된 경우를 처리한다.

        try:
            # bytes 데이터를 UTF-8 문자열로 안전하게 변환해 본다.

            payload = payload.decode("utf-8")
            # 정상적인 UTF-8 bytes라면 Python str 타입으로 변환한다.

        except UnicodeDecodeError:
            # bytes 내용이 UTF-8 규칙에 맞지 않아 디코딩할 수 없는 경우를 잡는다.

            return None
            # UTF-8 JSON이라는 Silver 규칙을 만족하지 않으므로 해당 레코드를 제외한다.

    if not isinstance(payload, str):
        # payload가 bytes도 아니고 str도 아닌 숫자, 객체 등의 타입으로 들어온 경우를 처리한다.

        payload = str(payload)
        # json.loads()가 문자열 입력을 받을 수 있도록 우선 문자열로 변환한다.
        # 단, 문자열 변환 후에도 올바른 JSON이 아니면 아래 json.loads() 단계에서 제거된다.

    try:
        # 문자열 payload를 실제 Python JSON 객체로 파싱한다.

        event = json.loads(payload)
        # 올바른 JSON 문자열이면 dict/list/string/number 등 대응하는 Python 객체로 변환된다.

    except (json.JSONDecodeError, TypeError, ValueError):
        # JSON 문법 오류, 잘못된 타입, 잘못된 값 등 파싱 과정에서 발생 가능한 예외를 처리한다.

        return None
        # 파싱할 수 없는 데이터는 Silver 정제 대상에서 제외한다.

    if not isinstance(event, dict):
        # JSON 자체는 유효하더라도 최상위 구조가 Object인지 확인한다.
        # 예: [] 배열, "abc" 문자열, 123 숫자 등은 유효한 JSON이지만 현재 Silver 이벤트 규칙에는 맞지 않는다.

        return None
        # 최상위 JSON Object가 아닌 레코드는 Silver Stream으로 전달하지 않는다.

    if _validate_event(event) is not None:
        # 내부 필드 검사를 통과하지 못한 이벤트는 Silver Stream에서 제외한다.
        return None

    # 최상위 null 값을 가진 필드를 제거한다.
    # 예: {"user_id": 1, "email": null} -> {"user_id": 1}
    # 현재 단계에서는 중첩 객체 내부의 null까지 재귀적으로 제거하지 않고 최상위 필드만 정리한다.
    cleaned = {key: value for key, value in event.items() if value is not None}
    # event의 key/value를 순회하면서 value가 None이 아닌 항목만 새로운 dict인 cleaned에 담는다.

    # Silver 처리 메타데이터를 원본 비즈니스 필드와 분리하기 위해 "_silver" 객체 아래에 묶는다.
    # 이렇게 하면 ecommerce, finance 등의 기존 필드 이름과 충돌할 가능성을 줄일 수 있다.
    cleaned["_silver"] = {
        # 정제된 이벤트에 Silver 계층 자체의 처리 정보를 추가한다.

        "layer": "silver",
        # 현재 데이터가 Medallion Architecture의 Silver 계층 데이터임을 표시한다.

        "processor": "apache-flink",
        # 이 데이터를 정제한 처리 엔진이 Apache Flink임을 기록한다.

        "schema_version": SILVER_SCHEMA_VERSION,
        # 위에서 정의한 Silver 스키마 버전을 각 레코드에 기록한다.

        "processed_at": datetime.now(timezone.utc).isoformat(),
        # 현재 UTC 시각을 timezone 정보가 포함된 ISO-8601 문자열로 생성한다.
        # 예: 2026-08-20T13:20:15.123456+00:00
    }
    # _silver 메타데이터 객체 생성을 종료한다.

    return json.dumps(
        # Python dict인 cleaned를 다시 Kinesis로 전송 가능한 JSON 문자열로 직렬화한다.

        cleaned,
        # 직렬화할 최종 Silver 이벤트 객체다.

        ensure_ascii=False,
        # 한글 등 비ASCII 문자를 \uXXXX 형태로 강제 이스케이프하지 않고 원문 그대로 저장한다.

        separators=(",", ":"),
        # 기본 JSON의 불필요한 공백을 제거하여 {"a":1,"b":2}처럼 더 작고 간결한 문자열을 만든다.
        # 스트리밍 데이터에서는 레코드 크기를 조금이라도 줄이는 데 도움이 된다.

        default=str,
        # datetime 등 JSON이 기본적으로 직렬화하지 못하는 값이 들어오면 str()로 변환하여 직렬화를 시도한다.
    )
    # 완성된 Silver JSON 문자열을 호출한 main.py의 clean_event UDF에 반환한다.


def reject_event_payload(payload: Any) -> Optional[str]:
    # Raw Kinesis payload를 검사하여 오염된 데이터만 Reject용 JSON 문자열로 변환한다.
    # 정상 데이터는 None을 반환하여 Reject Stream에서 제외한다.

    event, reject_reason = _parse_payload(payload)
    # JSON 파싱 가능 여부와 최상위 구조를 먼저 검사한다.

    if reject_reason is None:
        # JSON 기본 검사를 통과한 경우에만 내부 데이터 품질 검사를 수행한다.
        reject_reason = _validate_event(event)

    if reject_reason is None:
        # 모든 검사를 통과한 정상 데이터는 Reject 대상으로 만들지 않는다.
        return None

    if isinstance(payload, bytes):
        # 원본이 bytes이면 가능한 경우 UTF-8 문자열로 복원하여 저장한다.
        try:
            original_payload = payload.decode("utf-8")
        except UnicodeDecodeError:
            # UTF-8 복원이 불가능하면 bytes 표현식을 사용하여 원본 정보를 보존한다.
            original_payload = repr(payload)
    else:
        # bytes가 아닌 입력은 전달받은 원본 값을 그대로 보존한다.
        original_payload = payload

    rejected = {
        # Reject 처리 메타데이터와 오염된 원본 payload를 하나의 객체로 구성한다.
        "_reject": {
            "layer": "rejected",
            "processor": "apache-flink",
            "schema_version": REJECT_SCHEMA_VERSION,
            "reason": reject_reason,
            "processed_at": datetime.now(timezone.utc).isoformat(),
        },
        "original_payload": original_payload,
    }

    return json.dumps(
        # Reject 객체를 Kinesis로 전송할 수 있는 JSON 문자열로 직렬화한다.
        rejected,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    )
