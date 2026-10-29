locals {
  ingress = {
    3000  = data.aws_security_group.lb.id
    3500  = data.aws_security_group.app.id
    4318  = data.aws_security_group.app.id
    4040  = data.aws_security_group.app.id
    9999  = data.aws_security_group.app.id
    12347 = data.aws_security_group.lb.id
    12345 = data.aws_security_group.lb.id
    22    = data.aws_security_group.bastion.id
  }
}

resource "aws_security_group" "observability" {
  name   = "observability-sg"
  vpc_id = data.aws_vpc.main.id

  dynamic "ingress" {
    for_each = local.ingress
    content {
      from_port       = ingress.key
      to_port         = ingress.key
      protocol        = "tcp"
      security_groups = [ingress.value]
    }
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "observability-sg"
  }
}

resource "aws_instance" "observability" {
  ami                    = var.ami_id
  instance_type          = var.instance_type
  subnet_id              = data.aws_subnet.app_1.id
  private_ip             = var.private_ip
  vpc_security_group_ids = [aws_security_group.observability.id]
  key_name               = var.key_name
  iam_instance_profile   = "LabInstanceProfile"

  associate_public_ip_address = false

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 2
  }

  root_block_device {
    volume_size           = 30
    volume_type           = "gp3"
    encrypted             = true
    delete_on_termination = true
  }

  tags = {
    Name = "observability"
  }
}
