# Silver Layer에서 사용되는 Kinesis(입력)
# Flink에서 전송된 데이터를 획득 -> firehose(출력)로 전송
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
