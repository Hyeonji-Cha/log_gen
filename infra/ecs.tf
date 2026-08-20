# ECS 리소스를 논리적으로 묶어 관리하는 클러스터
# Fargate를 사용하므로 EC2 컨테이너 인스턴스를 직접 등록하거나 관리하지 않는다.
resource "aws_ecs_cluster" "this" {
  name = local.cluster_name
}

# Fargate에서 실행할 로그 생성기 태스크의 명세
# 사용할 이미지, CPU·메모리, 실행 권한, 환경 변수, 로그 전송 방법을 정의한다.
resource "aws_ecs_task_definition" "generator" {
  # 같은 태스크 정의의 개정 이력을 묶는 이름
  # 설정이 변경되면 같은 family 아래에 1, 2, 3과 같이 새 revision이 생성된다.
  family = local.task_family

  # 이 태스크 정의가 Fargate 실행 방식과 호환되어야 함을 지정한다.
  requires_compatibilities = ["FARGATE"]

  # 태스크마다 전용 ENI와 사설 IP를 할당하는 네트워크 모드
  # 실제 서브넷과 보안 그룹은 태스크를 실행할 때 별도로 지정한다.
  network_mode = "awsvpc"

  # 태스크 전체에 할당할 Fargate CPU와 메모리
  # ECS API가 문자열을 요구하므로 숫자형 variable을 문자열로 변환한다.
  cpu    = tostring(var.task_cpu)
  memory = tostring(var.task_memory)

  # ECS 에이전트가 ECR에서 이미지를 가져오고 CloudWatch Logs로 로그를 전송할 때 사용하는 역할
  # 애플리케이션 코드가 AWS API를 호출할 권한은 task_role_arn으로 별도 지정해야 한다.
  execution_role_arn = aws_iam_role.ecs_execution.arn

  # 컨테이너를 실행할 운영체제와 CPU 아키텍처
  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  # ECS가 요구하는 JSON 형식으로 컨테이너 설정을 생성한다.
  container_definitions = jsonencode([
    {
      name      = "log-generator"
      image     = "${aws_ecr_repository.generator.repository_url}:${var.image_tag}"
      essential = true

      environment = [

        #[브론즈 추가]
        # 생성한 이벤트를 Kinesis로 전송할지 결정하는 설정
        { name = "KINESIS_ENABLE", value = "ecommerce"},
        # 이벤트를 전송할 Kinesis Data Stream 이름
        { name = "KINESIS_STREAM_NAME", value = aws_kinesis_stream.logs.name },
        
        # 생성할 로그의 업무 도메인 선택
        { name = "DOMAIN", value = "ecommerce" },
        # 로그 생성기를 실행할 총 시간(초)
        { name = "DURATION_SECONDS", value = "300" },
        # 생성할 최대 이벤트 수로, 0이면 개수 제한을 사용하지 않음
        { name = "MAX_EVENTS", value = "0" },
        # 초당 생성할 기본 이벤트 수(RPS)
        { name = "BASE_RPS", value = "2.0" },
        # 이벤트 생성 속도 배율로, 1.0이면 기본 속도로 실행
        { name = "TIME_SCALE", value = "1.0" },
        # 전체 이벤트 중 의도적으로 오염시킬 데이터의 비율
        { name = "CORRUPTION_RATE", value = "0.03" },
        # 오염된 이벤트에 오염 유형과 여부를 표시할지 결정
        { name = "INCLUDE_CORRUPTION_LABEL", value = "false" },
        # 생성된 로그의 출력 대상으로 stdout, file, both 중 선택
        { name = "OUTPUT_MODE", value = "stdout" },
        # 파일 출력 모드를 사용할 때 로그를 저장할 컨테이너 내부 경로
        { name = "LOG_FILE", value = "/tmp/generated-logs.jsonl" },
        # 로그 발생 시각 계산에 사용할 시간대
        { name = "TIMEZONE", value = "Asia/Seoul" },
        # Faker가 가짜 데이터를 생성할 때 사용할 지역 설정
        { name = "FAKER_LOCALE", value = "ko_KR" },
        # 로그를 생성한 실행 환경을 구분하는 값
        { name = "ENVIRONMENT", value = "simulation" },
        # 동일한 실행에서 생성된 이벤트를 묶어 식별할 실행 ID
        { name = "RUN_ID", value = "manual" }
      ]

      logConfiguration = {
        # 컨테이너의 stdout/stderr를 CloudWatch Logs로 전송한다.
        logDriver = "awslogs"

        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.generator.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "generator"
        }
      }
    }
  ])
}
