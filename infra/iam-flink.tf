# Managed Service for Apache Flink ( 관리형 서비스 형태의 Flink ) 의 IAM
data "aws_iam_policy_document" "flink_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["kinesisanalytics.amazonaws.com"]
    }
  }
}
# 2. 해당 Role 정의(생성) -> 기본 flink 정책 반영된 role
resource "aws_iam_role" "flink" {
  name               = "${var.project_name}-flink-role"
  assume_role_policy = data.aws_iam_policy_document.flink_assume.json
}

# 3. 추가로 정책을 반영 (정책 조회 -> 정책 role 연결)
#    브론즈 kinesis 읽기(입력,  inputsteam)
#    실버 kinesis  쓰기 (출력,  outputstream)
#    s3에 flink의 애플리케이션 zip 파일 읽기 -> 실행할수 있음
#    Cloudwatch에 로그 기록
data "aws_iam_policy_document" "flink" {
  statement {
    sid    = "ReadBronzeKinesis" # statement 구분용
    effect = "Allow"
    actions = [
      "kinesis:DescribeStream",
      "kinesis:DescribeStreamSummary",
      "kinesis:GetShardIterator",
      "kinesis:GetRecords",
      "kinesis:ListShards"
    ]
    resources = [
      aws_kinesis_stream.logs.arn
    ]
  }
  statement {
    sid    = "WriteSilverKinesis"
    effect = "Allow"
    actions = [
      "kinesis:DescribeStreamSummary",
      "kinesis:PutRecord",
      "kinesis:PutRecords"
    ]
    resources = [
      aws_kinesis_stream.silver.arn
    ]
  }
  # S3에 저장된 Flink어플리케이션 코드(zip형태로 구성)
  statement {
    sid    = "ReadFlinkCode"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:GetObjectVersion"
    ]
    resources = [
      # 내 버킷의 flink/ 경로에 업로드한 애플리케이션 파일만 읽기
      "${aws_s3_bucket.data.arn}/flink/*"
    ]
  }
  # 로그 읽기
  statement {
    sid    = "DescribeFlinkLog"
    effect = "Allow"
    actions = [
      "logs:DescribeLogGroups",
      "logs:DescribeLogStreams"
    ]
    resources = [
      "*"
    ]
  }
  # 로그 쓰기
  statement {
    sid    = "WriteFlinkLog"
    effect = "Allow"
    actions = [
      "logs:PutLogEvents"
    ]
    resources = [
      aws_cloudwatch_log_stream.flink.arn
    ]
  }
}

# 위에서 만든 기본 role에 아래에서 조회한 정책 부여
resource "aws_iam_role_policy" "flink" {
  name   = "${var.project_name}-flink-policy"
  role   = aws_iam_role.flink.id
  policy = data.aws_iam_policy_document.flink.json
}

# Silver Firehose 서비스가 사용할 IAM Role
resource "aws_iam_role" "firehose_silver" {
  name               = "${var.project_name}-firehose-silver-role"
  assume_role_policy = data.aws_iam_policy_document.firehose_assume.json
}

# Silver Firehose가 Silver Kinesis를 읽고 S3 silver/ 경로에 저장할 권한
data "aws_iam_policy_document" "firehose_silver" {
  statement {
    sid    = "ReadSilverKinesis"
    effect = "Allow"
    actions = [
      "kinesis:DescribeStream",
      "kinesis:GetShardIterator",
      "kinesis:GetRecords",
      "kinesis:ListShards"
    ]
    resources = [
      aws_kinesis_stream.silver.arn
    ]
  }

  statement {
    sid    = "InspectSilverBucket"
    effect = "Allow"
    actions = [
      "s3:GetBucketLocation",
      "s3:ListBucket"
    ]
    resources = [
      aws_s3_bucket.data.arn
    ]
  }

  statement {
    sid    = "WriteSilverObjects"
    effect = "Allow"
    actions = [
      "s3:AbortMultipartUpload",
      "s3:PutObject"
    ]
    resources = [
      "${aws_s3_bucket.data.arn}/silver/*",
      "${aws_s3_bucket.data.arn}/errors/silver/*"
    ]
  }
}

# Silver Firehose Role에 Kinesis 읽기와 S3 쓰기 권한 연결
resource "aws_iam_role_policy" "firehose_silver" {
  name   = "${var.project_name}-firehose-silver-policy"
  role   = aws_iam_role.firehose_silver.id
  policy = data.aws_iam_policy_document.firehose_silver.json
}
