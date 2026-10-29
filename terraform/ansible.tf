resource "local_file" "ansible_inventory" {
  filename        = "${path.module}/../ansible/inventories/production/hosts.ini"
  file_permission = "0644"

  content = templatefile("${path.module}/scripts/hosts.ini.tftpl", {
    bastion_public_ip = data.aws_instance.bastion.public_ip
    private_ip        = aws_instance.observability.private_ip
    private_key_path  = var.private_key_path
  })
}

resource "local_file" "ansible_vars" {
  filename        = "${path.module}/../ansible/inventories/production/group_vars/observability.yml"
  file_permission = "0644"

  content = yamlencode({
    aws_region = var.aws_region
    buckets    = { for k, b in terraform_data.buckets : k => b.output }
  })
}

output "grafana_url" {
  value = "http://${data.aws_lb.main.dns_name}:3000"
}

output "otel_endpoint_ip" {
  value = aws_instance.observability.private_ip
}
