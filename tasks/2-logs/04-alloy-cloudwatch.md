# 2.4 Alloy: RDS e WAF via CloudWatch

**Fase:** F1 · **Repo:** observabilidade · **Estimativa:** 3 h · **Ref.:** § 4.3, § 4.4, § 6.6

## Contexto

Sem Subscription Filter, Kinesis ou Lambda: polling direto na API do CloudWatch. Custo: ~10–15 s de atraso.

## O que fazer

- [ ] Um `otelcol.receiver.awscloudwatch` **por origem**, log groups por nome (bloco `named`):
  - `/aws/rds/instance/app-db/error` e `/slowquery` → `origin="rds-logs"`
  - `aws-waf-logs-main-alb-waf` → `origin="waf-logs"`
- [ ] `poll_interval = "10s"`.
- [ ] Estado em `otelcol.storage.file`, volume no EBS.
- [ ] Promover `env`, `origin`, `service`, `host` com `loki.resource.labels` / `loki.attribute.labels` → `otelcol.exporter.loki` → `loki.write.default`.
- [ ] Enviar também ao arquivo bruto (task 2.3).
- [ ] Conferir no policy simulator: `logs:FilterLogEvents`, `logs:DescribeLogGroups`, `logs:DescribeLogStreams` na `LabRole`.

## Validar no lab (não documentado pelo Alloy)

- [ ] **Retomada:** parar a EC2, gerar logs, religar. Retoma de onde parou? Se não, ajustar `initial_lookback` (teto: 3 dias).
- [ ] **Timestamp:** horário do evento no CloudWatch, não o da leitura.

## Pronto quando

`{origin="waf-logs"} |= "BLOCK"` e `{origin="rds-logs"}` retornam dados, e os dois itens de validação estão documentados.
