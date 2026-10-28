resource "aws_s3_bucket" "buckets" {
  for_each = toset(["loki-logs", "logs-raw", "tempo-traces", "mimir-metrics", "pyroscope-profiles"])

  bucket        = "${each.key}-${data.aws_caller_identity.current.account_id}"
  force_destroy = true

  tags = {
    Name = each.key
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "logs_raw" {
  bucket = aws_s3_bucket.buckets["logs-raw"].id

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
