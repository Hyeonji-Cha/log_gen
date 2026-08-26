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
    # 데이터를 모아둔상태(버퍼링)에서 기록 -> 포멧
    # [GLUE] Firehose가 JSON을 Parquet로 변환 처리함, S3에 자체 압축 옵션은 UNCOMPRESSED로 표기
    compression_format = "UNCOMPRESSED"
    # 데이터 레코드 압축
    #compression_format = "GZIP" # GZIP으로 압축

    # S3 버킷 및 S3 오류 출력 접두사 시간대
    custom_time_zone = "Asia/Seoul"

    # [GLUE] 컨버전에 대한 구성 설정 (JSON => Glue Schema(사전에 정의된 테이블/스키마 <- 데이터구조/타입) => parquet)
    data_format_conversion_configuration {
      # 구성 정보 사용
      enabled = true
      # 입력원 flink 통해서 나온 JSON임
      input_format_configuration {
        # ser_de (serializer/deserializer)
        deserializer {
          open_x_json_ser_de {
            case_insensitive                         = true
            convert_dots_in_json_keys_to_underscores = false
          }
        }
      }
      # JONS->parquet 변환시 참고할 스키마 (glue-silver.tf에 설정)
      schema_configuration {
        # 데이터베이스 명
        database_name = aws_glue_catalog_database.silver.name
        # 테이블 명
        table_name = aws_glue_catalog_table.silver.name
        # role 리소스명
        role_arn = aws_iam_role.firehose_silver.arn
        # 리전명
        region = var.aws_region
        # 버전
        version_id = "LATEST"
      }
      # 출력 SNAPPY 압축을 통한 Parquet임
      output_format_configuration {
        serializer {
          parquet_ser_de {
            compression = "SNAPPY"
          }
        }
      }
    }

    prefix = "silver/year=!{timestamp:yyyy}/month=!{timestamp:MM}/day=!{timestamp:dd}/hour=!{timestamp:HH}/"


    error_output_prefix = "errors/silver/!{firehose:error-output-type}/year=!{timestamp:yyyy}/month=!{timestamp:MM}/day=!{timestamp:dd}/hour=!{timestamp:HH}/"
  }
  depends_on = [
    aws_iam_role_policy.firehose_silver,
    aws_glue_catalog_table.silver
  ]
}
