locals {
  buckets = { for b in ["loki-logs", "logs-raw", "tempo-traces", "mimir-metrics", "pyroscope-profiles"] :
  b => "${b}-${data.aws_caller_identity.current.account_id}" }
}

resource "terraform_data" "buckets" {
  for_each = local.buckets
  input    = each.value

  provisioner "local-exec" {
    command = "aws s3api create-bucket --bucket ${self.input}"
  }

  provisioner "local-exec" {
    when    = destroy
    command = "aws s3 rb s3://${self.input} --force"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "logs_raw" {
  bucket = terraform_data.buckets["logs-raw"].output

  rule {
    id     = "expira-30-dias"
    status = "Enabled"
    filter {}

    expiration {
      days = 30
    }
  }
}

resource "aws_vpc_endpoint" "s3" {
  vpc_id            = data.aws_vpc.main.id
  service_name      = "com.amazonaws.${var.aws_region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [data.aws_route_table.private.id]

  tags = {
    Name = "s3-gateway"
  }
}
