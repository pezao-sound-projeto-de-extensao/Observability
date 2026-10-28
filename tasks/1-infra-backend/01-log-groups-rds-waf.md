# 1.1 Log groups do RDS/WAF, export do RDS e logging do WAF

**Fase:** F1 · **Repo:** infra (`DevOps/prod/terraform`) · **Estimativa:** 1 h · **Ref.:** § 4.3, § 14, § 16

## Contexto

A PoC criou esses recursos e foi destruída; hoje o repo não tem nenhum deles. O Alloy lê esses log groups por polling (task 2.4).

## O que fazer

- [ ] Log groups, criados **antes** do RDS (`depends_on`), senão o RDS cria sozinho e exige `terraform import`:
  - `/aws/rds/instance/app-db/error`
  - `/aws/rds/instance/app-db/slowquery`
  - `aws-waf-logs-main-alb-waf` (prefixo `aws-waf-logs-` obrigatório)
  - `retention_in_days = 3` em todos
- [ ] Parameter group do RDS: `slow_query_log=1`, `long_query_time=1`, `log_output=FILE`.
- [ ] Instância RDS: `enabled_cloudwatch_logs_exports = ["error", "slowquery"]`.
- [ ] `aws_wafv2_web_acl_logging_configuration` do WAF do `main-alb` para o log group.
- [ ] **Não** recriar o Kinesis nem os subscription filters da PoC (código de referência na § 16).
- [ ] F3, para a demo do sqlcommenter: permitir baixar `long_query_time` para `0.2` temporariamente (variável).

## Pronto quando

- `terraform apply` sem recursos tainted.
- Logs do WAF chegam ao log group.
- Um `SELECT SLEEP(2)` aparece em `/slowquery`.
