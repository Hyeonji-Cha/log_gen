from __future__ import annotations

import base64
import json
import os
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

import boto3


GOLD_STREAM_NAME = os.environ["GOLD_STREAM_NAME"]

AWS_REGION = os.environ.get("AWS_REGION_NAME") or os.environ.get(
    "AWS_REGION", "ap-northeast-2"
)

GOLD_SCHEMA_VERSION = "1.0"

kinesis = boto3.client("kinesis", region_name=AWS_REGION)


def _decode_kinesis_record(record: dict[str, Any]) -> dict[str, Any]:
    encoded = record["kinesis"]["data"]

    payload = base64.b64decode(encoded).decode("utf-8")

    value = json.loads(payload)

    if not isinstance(value, dict):
        raise ValueError("Silver payload must be a JSON object.")

    return value


def _to_latency(value: Any) -> float | None:
    if isinstance(value, bool):
        return None

    if isinstance(value, (int, float)):
        result = float(value)

    elif isinstance(value, str):
        try:
            result = float(value.strip())
        except ValueError:
            return None

    else:
        return None

    if result < 0:
        return None

    return result


def _is_success(event: dict[str, Any]) -> bool:
    response = event.get("response")

    if not isinstance(response, dict):
        return False

    try:
        status_code = int(response.get("status_code"))
    except (TypeError, ValueError):
        return False

    return status_code < 400


def _aggregate(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "event_count": 0,
            "success_count": 0,
            "error_count": 0,
            "latencies": [],
        }
    )

    for event in records:
        domain = str(event.get("domain") or "unknown").strip().lower()

        group = groups[domain]

        group["event_count"] += 1

        if _is_success(event):
            group["success_count"] += 1
        else:
            group["error_count"] += 1

        response = event.get("response")

        if isinstance(response, dict):
            latency = _to_latency(response.get("latency_ms"))

            if latency is not None:
                group["latencies"].append(latency)

    processed_at = datetime.now(timezone.utc).isoformat()

    output: list[dict[str, Any]] = []

    for domain, group in sorted(groups.items()):
        latencies = group["latencies"]

        avg_latency = (
            round(sum(latencies) / len(latencies), 2)
            if latencies
            else 0.0
        )

        min_latency = int(min(latencies)) if latencies else 0
        max_latency = int(max(latencies)) if latencies else 0

        if group["error_count"] == 0:
            result = "success"
        elif group["success_count"] == 0:
            result = "error"
        else:
            result = "mixed"

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
    if not records:
        return

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

    response = kinesis.put_records(
        StreamName=GOLD_STREAM_NAME,
        Records=request_records,
    )

    if response.get("FailedRecordCount", 0):
        raise RuntimeError(
            f"Failed to write "
            f"{response['FailedRecordCount']} Gold record(s) to Kinesis."
        )


def lambda_handler(
    event: dict[str, Any],
    context: Any,
) -> dict[str, Any]:
    silver_events: list[dict[str, Any]] = []

    batch_failures: list[dict[str, str]] = []

    for record in event.get("Records", []):
        try:
            silver_events.append(
                _decode_kinesis_record(record)
            )

        except Exception as exc:
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

    gold_records = _aggregate(silver_events)

    _put_gold_records(gold_records)

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

    return {
        "batchItemFailures": batch_failures
    }