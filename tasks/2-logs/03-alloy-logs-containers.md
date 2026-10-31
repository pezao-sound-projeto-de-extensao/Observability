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

- [x] O marshaler `body` grava uma linha por registro (Athena consegue ler).
- [x] Com o Loki parado alguns minutos, `loki_write_dropped_bytes_total` continua 0.

**Resultado no lab (2026-10-30, Alloy v1.21.3, Fluent Bit 3.2 com logs de teste):**
- O marshaler `body` grava uma linha por registro, e o Athena leu as três tabelas (`athena/logs-raw.sql`).
- **Exceção:** um registro de slow query do RDS tem várias linhas, então ocupa várias linhas em `logs_raw_rds`.
- Com o Loki parado por ~3 min, `loki_write_dropped_bytes_total` ficou em 0 e os 5 logs chegaram depois.
- Com a EC2 de observabilidade parada, os logs ficaram no buffer do Fluent Bit e chegaram com o horário original.
- **Falta:** validar com os logs reais do backend, que não foi implantado neste teste.

## Risco aceito

O pendente do `loki.write` fica em memória: um restart do Alloy perde esses registros (WAL é experimental, desligado).

## Pronto quando

Logs de `app`, `nginx` e `rabbitmq` chegam ao Loki com as 4 labels e o horário original, e ao `logs-raw` consultáveis no Athena.
