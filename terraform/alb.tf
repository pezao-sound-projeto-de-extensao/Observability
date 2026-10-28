resource "aws_lb_target_group" "grafana" {
  name        = "grafana-tg"
  port        = 3000
  protocol    = "HTTP"
  vpc_id      = data.aws_vpc.main.id
  target_type = "instance"

  health_check {
    path     = "/api/health"
    port     = "traffic-port"
    protocol = "HTTP"
    matcher  = "200"
  }
}

resource "aws_lb_target_group_attachment" "grafana" {
  target_group_arn = aws_lb_target_group.grafana.arn
  target_id        = aws_instance.observability.id
  port             = 3000
}

resource "aws_lb_listener" "grafana" {
  load_balancer_arn = data.aws_lb.main.arn
  port              = 3000
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.grafana.arn
  }
}

resource "aws_lb_target_group" "faro" {
  name        = "faro-tg"
  port        = 12347
  protocol    = "HTTP"
  vpc_id      = data.aws_vpc.main.id
  target_type = "instance"

  health_check {
    path     = "/-/ready"
    port     = "12345"
    protocol = "HTTP"
    matcher  = "200"
  }
}

resource "aws_lb_target_group_attachment" "faro" {
  target_group_arn = aws_lb_target_group.faro.arn
  target_id        = aws_instance.observability.id
  port             = 12347
}

resource "aws_lb_listener_rule" "faro" {
  listener_arn = data.aws_lb_listener.http.arn
  priority     = 50

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.faro.arn
  }

  condition {
    path_pattern {
      values = ["/collect", "/collect/*"]
    }
  }
}
