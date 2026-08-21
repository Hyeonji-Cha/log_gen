# Kinesis Data Streams의 로그를 Firehose가 모아서 S3 Bronze 영역에 저장한다.
resource "aws_kinesis_firehose_delivery_stream" "logs" {
  # AWS 콘솔에서 식별할 Firehose Delivery Stream 이름
  name = local.firehose_name
  # 최종 목적지로 일반 S3보다 세부 설정이 많은 Extended S3 방식 사용
  destination = "extended_s3"

  # Firehose가 데이터를 읽어올 입력 소스로 Kinesis Data Stream 지정
  kinesis_source_configuration {
    # 로그 제너레이터가 이벤트를 전송하는 Kinesis Stream
    kinesis_stream_arn = aws_kinesis_stream.logs.arn
    # Firehose가 Kinesis를 읽을 때 사용할 IAM Role
    role_arn = aws_iam_role.firehose.arn
  }

  # Kinesis에서 읽은 레코드를 모아서 저장할 S3 설정
  extended_s3_configuration {
    # Bronze 데이터를 저장할 S3 Bucket
    bucket_arn = aws_s3_bucket.data.arn
    # Firehose가 S3에 객체를 저장할 때 사용할 IAM Role
    role_arn = aws_iam_role.firehose.arn

    # 지정한 크기 또는 시간이 먼저 충족되면 버퍼의 레코드를 S3 객체로 저장
    # 현재 기본값: 1MiB 또는 60초
    buffering_size     = var.firehose_buffer_size
    buffering_interval = var.firehose_buffer_interval

    # 버퍼에 모은 JSONL 레코드를 GZIP으로 압축해 S3 저장 용량을 줄임
    # 압축을 해제하면 원래의 JSONL 내용으로 확인할 수 있다.
    # compression_format = "UNCOMPRESSED"
    compression_format = "GZIP"

    # 아래 S3 경로의 연·월·일·시를 한국 시간 기준으로 생성
    custom_time_zone = "Asia/Seoul"

    # 정상 데이터를 시간 단위 파티션 경로에 저장
    # 예: bronze/year=2026/month=08/day=20/hour=15/
    # Athena, Glue, Spark가 필요한 시간 경로만 읽을 수 있어 조회 범위와 비용을 줄일 수 있다.
    prefix = "bronze/year=!{timestamp:yyyy}/month=!{timestamp:MM}/day=!{timestamp:dd}/hour=!{timestamp:HH}/"

    # S3 전달에 실패한 데이터를 오류 유형과 발생 시간별 경로에 분리해 저장
    # !{firehose:error-output-type}에는 Firehose가 판단한 오류 유형이 들어간다.
    # [실버수정]
    error_output_prefix = "errors/bronze/!{firehose:error-output-type}/year=!{timestamp:yyyy}/month=!{timestamp:MM}/day=!{timestamp:dd}/hour=!{timestamp:HH}/"
  }

  # Kinesis 읽기와 S3 쓰기 권한이 먼저 생성된 후 Firehose를 생성
  depends_on = [
    aws_iam_role_policy.firehose
  ]
}
