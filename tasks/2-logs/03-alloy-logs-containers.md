# 2.3 Alloy: logs dos containers e arquivo bruto no S3

**Fase:** F1 · **Repo:** observabilidade · **Estimativa:** 4 h · **Ref.:** § 4.4, § 4.5, § 7

## O que fazer

- [ ] `loki.source.api "fluentbit"` na porta 3500, `use_incoming_timestamp = true` (sem isso, os logs do buffer entram com o horário de chegada).
- [ ] `loki.write "default"` para `http://loki:3100/loki/api/v1/push` com `max_backoff_retries = 0` (não descarta após 10 tentativas).
- [ ] Só 4 labels: `env`, `origin`, `service`, `host`. O resto fica na linha.
- [ ] Arquivo bruto: `otelcol.receiver.loki "raw"` → `otelcol.exporter.awss3` (experimental), bucket `logs-raw`:
  - marshaler `body` (só a linha original);
  - prefixo por origem (`origin=container-logs/`, `origin=waf-logs/`, `origin=rds-logs/`);
  - particionamento padrão por tempo.
- [ ] Uma tabela no Athena por origem (containers e WAF em JSON por linha, RDS em texto).

## Validar

- [ ] O marshaler `body` grava uma linha por registro (Athena consegue ler).
- [ ] Com o Loki parado alguns minutos, `loki_write_dropped_bytes_total` continua 0.

## Risco aceito

O pendente do `loki.write` fica em memória: um restart do Alloy perde esses registros (WAL é experimental, desligado).

## Pronto quando

Logs de `app`, `nginx` e `rabbitmq` chegam ao Loki com as 4 labels e o horário original, e ao `logs-raw` consultáveis no Athena.
