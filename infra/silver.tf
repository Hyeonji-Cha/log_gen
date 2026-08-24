# Silver 파이프라인 구성: Flink의 정제 데이터를 Silver Kinesis로 받고,
# Silver 전용 Firehose가 데이터를 모아 S3의 silver/ 경로에 GZIP으로 적재한다.
resource "aws_kinesis_stream" "silver" {
  name             = local.silver_kinesis_stream_name
  shard_count      = var.silver_kinesis_shard_count
  retention_period = var.silver_kinesis_retention_hour

  # 구성방식
  stream_mode_details {
    # 프로비저닝 모드로 구성 -> 샤드수 직접 지정
    # 부족하면 성능저하, 과하면 비용 과대 -> 측정데이터가 없으면 온디맨드로 감
    stream_mode = "PROVISIONED"
  }
  tags = {
    DataLayer = "silver"
  }
}

resource "aws_kinesis_firehose_delivery_stream" "silver" {

  name = local.silver_firehose_name

  destination = "extended_s3"

  kinesis_source_configuration {

    kinesis_stream_arn = aws_kinesis_stream.silver.arn

    role_arn = aws_iam_role.firehose_silver.arn
  }


  extended_s3_configuration {

    bucket_arn = aws_s3_bucket.data.arn

    role_arn = aws_iam_role.firehose_silver.arn

    buffering_size     = var.firehose_buffer_size
    buffering_interval = var.firehose_buffer_interval

    compression_format = "GZIP"

    custom_time_zone = "Asia/Seoul"

    prefix = "silver/year=!{timestamp:yyyy}/month=!{timestamp:MM}/day=!{timestamp:dd}/hour=!{timestamp:HH}/"


    error_output_prefix = "errors/silver/!{firehose:error-output-type}/year=!{timestamp:yyyy}/month=!{timestamp:MM}/day=!{timestamp:dd}/hour=!{timestamp:HH}/"
  }
  depends_on = [
    aws_iam_role_policy.firehose_silver
  ]
}
