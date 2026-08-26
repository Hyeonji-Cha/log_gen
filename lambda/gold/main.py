"""Silver Kinesis 이벤트를 도메인별로 집계해 Gold Kinesis로 보내는 Lambda 함수.

처리 흐름:
Silver Kinesis 배치 수신 → Base64/JSON 디코딩 → 도메인별 지표 집계
→ Gold JSON 생성 → Gold Kinesis 전송 → 실패한 입력 레코드만 재시도 요청
"""

from __future__ import annotations

import base64
import json
import os
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

import boto3


# Terraform이 Lambda 환경 변수로 전달하는 Gold 출력 스트림 이름이다.
# 필수값이므로 설정되지 않으면 Lambda 초기화 단계에서 즉시 오류가 발생한다.
GOLD_STREAM_NAME = os.environ["GOLD_STREAM_NAME"]

# 명시적으로 전달한 리전을 우선 사용하고, 없으면 Lambda 기본 리전 또는 서울 리전을 사용한다.
AWS_REGION = os.environ.get("AWS_REGION_NAME") or os.environ.get(
    "AWS_REGION", "ap-northeast-2"
)

# Gold 레코드 구조가 변경될 때 데이터 버전을 구분하기 위한 값이다.
GOLD_SCHEMA_VERSION = "1.0"

# main.py가 처음 로드될 때 Kinesis 클라이언트를 한 번 생성한다.
# 같은 Lambda 실행 환경에서 handler가 다시 호출되면 이 객체를 그대로 사용한다.
kinesis = boto3.client("kinesis", region_name=AWS_REGION)


def _decode_kinesis_record(record: dict[str, Any]) -> dict[str, Any]:
    """Kinesis 레코드의 Base64 데이터를 Silver JSON 객체로 복원한다."""

    # Lambda에 전달되는 Kinesis 데이터는 Base64로 인코딩되어 있다.
    encoded = record["kinesis"]["data"]

    # Base64 → UTF-8 문자열 → Python 객체 순서로 변환한다.
    payload = base64.b64decode(encoded).decode("utf-8")

    value = json.loads(payload)

    # Gold 집계는 key/value 형태의 이벤트만 처리하므로 JSON Object만 허용한다.
    if not isinstance(value, dict):
        raise ValueError("Silver payload must be a JSON object.")

    return value


def _to_latency(value: Any) -> float | None:
    """latency 값을 집계 가능한 0 이상의 실수로 변환한다."""

    # bool은 Python에서 int로 취급되므로 지연 시간 값에서 명시적으로 제외한다.
    if isinstance(value, bool):
        return None

    # 숫자는 그대로 변환하고 숫자 문자열은 공백 제거 후 변환을 시도한다.
    if isinstance(value, (int, float)):
        result = float(value)

    elif isinstance(value, str):
        try:
            result = float(value.strip())
        except ValueError:
            return None

    else:
        return None

    # 음수 또는 변환할 수 없는 값은 평균·최솟값·최댓값 계산에서 제외한다.
    if result < 0:
        return None

    return result


def _is_success(event: dict[str, Any]) -> bool:
    """HTTP 상태 코드가 400 미만이면 성공 이벤트로 판단한다."""

    # Silver 이벤트의 응답 정보는 response 중첩 객체에 들어 있다.
    response = event.get("response")

    if not isinstance(response, dict):
        return False

    try:
        status_code = int(response.get("status_code"))
    except (TypeError, ValueError):
        # 상태 코드가 없거나 숫자로 변환할 수 없으면 오류 이벤트로 집계한다.
        return False

    return status_code < 400


def _aggregate(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Silver 이벤트 배치를 domain별 Gold 지표 한 건으로 집계한다."""

    # 각 도메인별 전체·성공·오류 건수와 유효한 latency 목록을 누적한다.
    groups: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "event_count": 0,
            "success_count": 0,
            "error_count": 0,
            "latencies": [],
        }
    )

    for event in records:
        # domain이 없으면 unknown 그룹으로 묶고 대소문자 차이를 제거한다.
        domain = str(event.get("domain") or "unknown").strip().lower()

        group = groups[domain]

        group["event_count"] += 1

        if _is_success(event):
            group["success_count"] += 1
        else:
            group["error_count"] += 1

        # response.latency_ms가 유효할 때만 latency 통계에 포함한다.
        response = event.get("response")

        if isinstance(response, dict):
            latency = _to_latency(response.get("latency_ms"))

            if latency is not None:
                group["latencies"].append(latency)

    # 같은 Lambda 배치에서 생성한 Gold 레코드는 동일한 UTC 처리 시각을 사용한다.
    processed_at = datetime.now(timezone.utc).isoformat()

    output: list[dict[str, Any]] = []

    for domain, group in sorted(groups.items()):
        latencies = group["latencies"]

        # 유효 latency가 없으면 통계값을 0으로 기록해 Gold 스키마를 일정하게 유지한다.
        avg_latency = (
            round(sum(latencies) / len(latencies), 2)
            if latencies
            else 0.0
        )

        min_latency = int(min(latencies)) if latencies else 0
        max_latency = int(max(latencies)) if latencies else 0

        # 도메인별 배치 결과를 전체 성공, 전체 오류, 혼합 상태로 요약한다.
        if group["error_count"] == 0:
            result = "success"
        elif group["success_count"] == 0:
            result = "error"
        else:
            result = "mixed"

        # 도메인 하나당 Gold 레코드 하나를 만든다.
        output.append(
            {
                "processed_at": processed_at,
                "domain": domain,
                "event_count": group["event_count"],
                "success_count": group["success_count"],
                "error_count": group["error_count"],
                "avg_latency_ms": avg_latency,
                "min_latency_ms": min_latency,
                "max_latency_ms": max_latency,
                "result": result,
                "gold_schema_version": GOLD_SCHEMA_VERSION,
            }
        )

    return output


def _put_gold_records(records: list[dict[str, Any]]) -> None:
    """집계된 Gold 레코드를 Kinesis PutRecords API로 한 번에 전송한다."""

    if not records:
        # 정상적으로 디코딩된 Silver 이벤트가 없으면 전송 요청을 만들지 않는다.
        return

    # Kinesis Data는 UTF-8 bytes여야 하며 domain을 Partition Key로 사용한다.
    # 같은 domain 데이터가 같은 shard로 향하도록 하여 후속 처리를 일관되게 만든다.
    request_records = [
        {
            "Data": (
                json.dumps(
                    record,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                + "\n"
            ).encode("utf-8"),
            "PartitionKey": record["domain"],
        }
        for record in records
    ]

    # 여러 도메인의 Gold 레코드를 개별 호출하지 않고 한 번의 배치 API로 전송한다.
    response = kinesis.put_records(
        StreamName=GOLD_STREAM_NAME,
        Records=request_records,
    )

    # PutRecords는 일부 레코드만 실패할 수 있으므로 HTTP 성공 여부와 별도로 실패 건수를 확인한다.
    if response.get("FailedRecordCount", 0):
        raise RuntimeError(
            f"Failed to write "
            f"{response['FailedRecordCount']} Gold record(s) to Kinesis."
        )


def lambda_handler(
    event: dict[str, Any],
    context: Any,
) -> dict[str, Any]:
    """Silver Kinesis 배치를 처리하는 AWS Lambda 진입점이다."""

    # 정상적으로 디코딩된 이벤트만 Gold 집계 대상으로 모은다.
    silver_events: list[dict[str, Any]] = []

    # 디코딩 실패 레코드의 sequence number를 모아 Lambda 부분 배치 실패 응답에 사용한다.
    batch_failures: list[dict[str, str]] = []

    for record in event.get("Records", []):
        try:
            silver_events.append(
                _decode_kinesis_record(record)
            )

        except Exception as exc:
            # 개별 레코드 실패가 전체 배치를 중단시키지 않도록 실패 항목만 따로 기록한다.
            sequence_number = (
                record.get("kinesis", {})
                .get("sequenceNumber")
            )

            if sequence_number:
                batch_failures.append(
                    {
                        "itemIdentifier": sequence_number
                    }
                )

            print(
                f"[WARN] Failed to decode Silver record: {exc}"
            )

    # 정상 Silver 이벤트를 도메인별 지표로 축약한다.
    gold_records = _aggregate(silver_events)

    # 집계 결과를 Gold Kinesis로 전송한다. 전송 실패는 예외로 처리해 Lambda 재시도를 유도한다.
    _put_gold_records(gold_records)

    # CloudWatch에서 한 번의 Lambda 실행 결과를 쉽게 확인할 수 있도록 요약 로그를 남긴다.
    print(
        json.dumps(
            {
                "silver_record_count": len(silver_events),
                "gold_record_count": len(gold_records),
                "failed_record_count": len(batch_failures),
            },
            separators=(",", ":"),
        )
    )

    # Event Source Mapping이 실패한 입력 레코드만 다시 전달하도록 AWS 규격에 맞춰 반환한다.
    return {
        "batchItemFailures": batch_failures
    }
