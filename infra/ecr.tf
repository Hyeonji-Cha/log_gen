# 로그 생성기가 구동되는 컨테이너의 이미지가 저장되는 저장소
# 1. 저장소 생성
resource "aws_ecr_repository" "generator" {
  name         = local.repository_name
  force_delete = true

  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }
}

# 2. 저장소 저장 비용 관리 정책 결정 -> 오래된 이미지를 언제까지 보관할 것인지
resource "aws_ecr_lifecycle_policy" "generator" {
  repository = aws_ecr_repository.generator.name
  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "keep 20 images"
        selection = {
          tagStatus   = "any"                # 태그 타입 상관 없음
          countType   = "imageCountMoreThan" # 20개 초과되면 액션 시작
          countNumber = 20                   # 20개만 유지
        }
        # 삭제 행동
        action = {
          type = "expire"
        }
      }
    ]
  })
}