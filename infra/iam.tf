# -----------------------------------------------------------------------------
# ECS Task Execution Role
# -----------------------------------------------------------------------------
# Fargate가 컨테이너를 시작하려면 ECR에서 이미지를 내려받고,
# 컨테이너의 stdout/stderr 로그를 CloudWatch Logs로 전송할 수 있어야 한다.
# 이 작업은 애플리케이션 코드가 아니라 ECS/Fargate 실행 환경이 수행하므로
# 전용 Execution Role을 만들어 필요한 권한을 부여한다.

# 1. ECS Task 서비스가 Execution Role을 맡을 수 있도록 신뢰 정책 정의
# 신뢰 정책은 Role의 실제 작업 권한이 아니라 "누가 이 Role을 사용할 수 있는가"를 정한다.
data "aws_iam_policy_document" "ecs_tasks_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"] # ECS가 Role을 맡아 임시 인증 정보를 발급받도록 허용

    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"] # 이 Role을 사용할 주체는 ECS Task 서비스
    }
  }
}

# 2. 위 신뢰 정책을 적용해 ECS Task Execution Role 생성
resource "aws_iam_role" "ecs_execution" {
  name               = "${var.project_name}-ecs-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
}

# 3. AWS 관리형 정책을 Execution Role에 연결
# AmazonECSTaskExecutionRolePolicy에는 ECR 이미지 pull과
# CloudWatch Logs의 로그 스트림 생성·로그 기록에 필요한 기본 권한이 포함된다.
resource "aws_iam_role_policy_attachment" "ecs_execution" {
  role       = aws_iam_role.ecs_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# -----------------------------------------------------------------------------
# Firehose Role - Bronze 데이터 파이프라인
# -----------------------------------------------------------------------------
# Firehose는 Kinesis Data Streams에서 로그를 읽어 일정량 모은 뒤 S3에 저장한다.
# 이를 위해 Firehose 서비스가 사용할 Role과 Kinesis 읽기·S3 쓰기 권한이 필요하다.

# 1. Firehose 서비스가 Role을 맡을 수 있도록 신뢰 정책 정의
data "aws_iam_policy_document" "firehose_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["firehose.amazonaws.com"]
    }
  }
}
# 2. 위 신뢰 정책을 적용해 Firehose 전용 IAM Role 생성
resource "aws_iam_role" "firehose" {
  # AWS 계정 내에서 식별할 Role 이름
  name = "${var.project_name}-firehose-role"

  # Firehose 서비스가 이 Role을 AssumeRole할 수 있도록 신뢰 정책 적용
  assume_role_policy = data.aws_iam_policy_document.firehose_assume.json
}

# 3. Firehose Role에 부여할 실제 작업 권한 정의
# 입력 소스인 Kinesis Data Streams에서 레코드를 읽는 권한과
# 목적지인 S3 Bucket에 객체를 저장하는 권한을 각각의 statement로 정의한다.
data "aws_iam_policy_document" "firehose_s3" {
  # Kinesis Stream의 정보와 shard를 조회하고 레코드를 읽을 수 있도록 허용
  statement {
    effect = "Allow"
    actions = [
      "kinesis:DescribeStream",
      "kinesis:GetShardIterator",
      "kinesis:GetRecords",
      "kinesis:ListShards"
    ]
    resources = [
      aws_kinesis_stream.logs.arn
    ]
  }

  # S3 Bucket의 위치·목록을 조회하고 수집한 로그 파일을 저장할 수 있도록 허용
  statement {
    effect = "Allow"
    actions = [
      "s3:AbortMultipartUpload",
      "s3:GetBucketLocation",
      "s3:ListBucket",
      "s3:PutObject"
    ]
    resources = [
      aws_s3_bucket.data.arn,
      "${aws_s3_bucket.data.arn}/*"
    ]
  }
}

# 4. 위에서 정의한 권한 정책을 Firehose Role에 인라인 정책으로 연결
# 신뢰 정책은 "Firehose가 Role을 맡을 수 있음"을 정하고,
# 이 인라인 정책은 "Role을 맡은 Firehose가 Kinesis와 S3에서 무엇을 할 수 있는지"를 정한다.
resource "aws_iam_role_policy" "firehose" {
  name   = "${var.project_name}-firehose-s3-policy"
  role   = aws_iam_role.firehose.id
  policy = data.aws_iam_policy_document.firehose_s3.json
}

# -----------------------------------------------------------------------------
# ECS Task Role - Kinesis 데이터 전송
# -----------------------------------------------------------------------------
# Execution Role이 ECR pull과 CloudWatch 로그 전송처럼 컨테이너 실행을 지원한다면,
# Task Role은 실행된 Python 애플리케이션이 AWS API를 호출할 때 사용한다.
# 로그 제너레이터가 생성한 이벤트를 Kinesis로 전송할 수 있도록 별도 Role을 구성한다.

# 1. 기존 ECS Task 신뢰 정책을 적용해 애플리케이션용 Task Role 생성
resource "aws_iam_role" "ecs_task_kinesis" {
  name               = "${var.project_name}-ecs-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json 
}

# 2. 로그 제너레이터가 Kinesis Stream에 단건·다건 레코드를 쓸 수 있도록 권한 정의
data "aws_iam_policy_document" "ecs_task_kinesis" {
  statement {
    effect = "Allow" #3. 허용한다

    actions = [
      "kinesis:PutRecords", #2. kinesis에 데이터를 쓰는 작업을
      "kinesis:PutRecord"
    ]

    resources = [
      aws_kinesis_stream.logs.arn #1. 프로젝트의 logs stream에만
    ]
  }
}

# 3. Kinesis 쓰기 권한을 ECS Task Role에 인라인 정책으로 연결
resource "aws_iam_role_policy" "ecs_task_kinesis" {
  name   = "${var.project_name}-kinesis-write"
  role   = aws_iam_role.ecs_task_kinesis.id
  policy = data.aws_iam_policy_document.ecs_task_kinesis.json
}
