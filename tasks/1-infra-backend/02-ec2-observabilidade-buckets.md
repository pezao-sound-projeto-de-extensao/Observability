# 1.2 EC2 de observabilidade, security group e buckets S3

**Fase:** F1 · **Repo:** observabilidade (novo) · **Estimativa:** 3 h · **Ref.:** § 6.3, § 6.4, § 4.4, § 15

## Contexto

Toda a stack roda em uma única EC2 com Docker Compose. O repo de observabilidade encontra os recursos do repo infra por **data source por nome** (`data "aws_subnet"`, `data "aws_lb"`), sem `terraform_remote_state`.

## O que fazer

- [ ] Criar o repo de observabilidade (Terraform + Ansible).
- [ ] EC2 `t3.large` (a `t3.medium` não comporta ~4,75 GB de limites; `t3.xlarge` é negada no lab):
  - Subnet **privada**, sem IP público.
  - `private_ip` fixo, combinado com o repo infra (vira `otel_endpoint_ip`).
  - `LabInstanceProfile` (o lab não permite criar roles).
  - IMDSv2 com **hop limit 2** (containers alcançam o metadata).
  - EBS gp3 30 GB.
- [ ] Security group com todas as portas de uma vez:

  | Porta | Origem | Uso |
  |---|---|---|
  | 3000 | SG do ALB | Grafana |
  | 3500 | SG das EC2 de app | Logs do Fluent Bit → Alloy |
  | 4318 | SG das EC2 de app | OTLP (traces e métricas) |
  | 4040 | SG das EC2 de app | Profiles (Pyroscope) |
  | 9999 | SG das EC2 de app | Métricas do Fluent Bit |
  | 12347 | SG do ALB | Faro `/collect` |
  | 12345 | SG do ALB | Health check do Faro |
  | 22 | Bastion | Ansible |

- [ ] Buckets S3: `loki-logs`, `logs-raw` (lifecycle de expiração em 30 dias), `tempo-traces`, `mimir-metrics`, `pyroscope-profiles`.
- [ ] Recomendado: VPC gateway endpoint de S3 (gratuito), para o tráfego ao S3 não passar pelo NAT (§ 4.5).

## Pronto quando

- EC2 sobe e é acessível pelo bastion.
- De dentro de um container na EC2, `aws s3 ls s3://loki-logs` funciona sem chaves.
- O IP privado se mantém após stop/start.
