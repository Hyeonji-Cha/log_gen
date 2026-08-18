# 로그 생성기용 네트워크의 기본 범위가 되는 VPC
resource "aws_vpc" "this" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = {
    Name = "${var.project_name}-vpc"
  }
}

# VPC가 인터넷과 통신할 수 있도록 연결하는 Internet Gateway(IGW)
# 실제 트래픽은 아래의 퍼블릭 라우트 테이블에 등록된 경로를 통해 IGW로 전달된다.
resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id

  tags = {
    Name = "${var.project_name}-igw"
  }
}

# 입력된 CIDR 수만큼 서로 다른 가용 영역에 퍼블릭 서브넷 생성
# count.index를 사용해 같은 위치의 AZ와 CIDR을 하나씩 짝지어 적용한다.(count를 사용하면 자동으로 index적용됨)
resource "aws_subnet" "public" {
  count = length(var.public_subnet_cidrs)

  vpc_id            = aws_vpc.this.id
  availability_zone = local.availability_zones[count.index]
  cidr_block        = var.public_subnet_cidrs[count.index]

  # 이 서브넷에서 생성되는 네트워크 인터페이스에 퍼블릭 IPv4 주소를 자동 할당한다.
  # Fargate 태스크가 NAT Gateway 없이 IGW를 통해 외부 서비스와 통신할 때 필요하다.
  map_public_ip_on_launch = true

  tags = {
    Name = "${var.project_name}-public-${count.index + 1}"
    Type = "loggen-public"
  }
}

# 모든 퍼블릭 서브넷이 공통으로 사용할 라우트 테이블
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id

  tags = {
    Name = "${var.project_name}-public-rt"
  }
}

# 목적지가 VPC 외부(0.0.0.0/0)인 IPv4 트래픽을 IGW로 전달하는 기본 경로
resource "aws_route" "internet" {
  route_table_id         = aws_route_table.public.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.this.id
}

# 각 퍼블릭 서브넷을 위의 퍼블릭 라우트 테이블에 연결
# association 하나는 서브넷 하나만 연결하므로 서브넷 개수만큼 반복 생성한다.
# 예: count.index가 0이면 public[0], 1이면 public[1]을 같은 라우트 테이블에 연결한다.
resource "aws_route_table_association" "public" {
  count = length(aws_subnet.public)

  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}
