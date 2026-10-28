data "aws_caller_identity" "current" {}

data "aws_vpc" "main" {
  tags = {
    Name = "StockFlow-vpc"
  }
}

data "aws_subnet" "app_1" {
  vpc_id = data.aws_vpc.main.id
  tags = {
    Name = "app_subnet-StockFlow-vpc-${var.aws_region}a"
  }
}

data "aws_route_table" "private" {
  vpc_id = data.aws_vpc.main.id
  tags = {
    Name = "private-route-table"
  }
}

data "aws_security_group" "lb" {
  vpc_id = data.aws_vpc.main.id
  name   = "lb-sg"
}

data "aws_security_group" "app" {
  vpc_id = data.aws_vpc.main.id
  name   = "app-sg"
}

data "aws_security_group" "bastion" {
  vpc_id = data.aws_vpc.main.id
  name   = "bastion-sg"
}

data "aws_instance" "bastion" {
  filter {
    name   = "tag:Name"
    values = ["bastion"]
  }
  filter {
    name   = "instance-state-name"
    values = ["running"]
  }
}

data "aws_lb" "main" {
  name = "main-alb"
}

data "aws_lb_listener" "http" {
  load_balancer_arn = data.aws_lb.main.arn
  port              = 80
}
