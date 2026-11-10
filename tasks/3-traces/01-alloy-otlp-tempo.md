# 3.1 Alloy OTLP e Tempo

**Fase:** F2 · **Repo:** observabilidade · **Estimativa:** 4 h · **Ref.:** § 5.5, § 6.5

## O que fazer

### Alloy
- [x] `otelcol.receiver.otlp` em `0.0.0.0:4318` (HTTP).
- [x] `otelcol.processor.filter "healthcheck"`: descartar `attributes["url.path"] == "/api/health"`.
- [x] `otelcol.processor.batch` → `otelcol.exporter.otlphttp "tempo"` (`http://tempo:4318`, `tls.insecure = true`).
- [x] Saída `metrics` do receiver vai para o batch e depois para o Mimir (task 4.1), já ligada (`otelcol.exporter.prometheus` → `prometheus.remote_write`).

Config completa na § 5.5 (testada localmente em 2026-10-26).

### Tempo
- [x] Monolítico (sem Kafka), porta 3200 só na rede interna (sem publicação no compose).
- [x] Storage em `tempo-traces`, credenciais do `LabInstanceProfile`.
- [x] Retenção: `compactor.compaction.block_retention: 168h`.
- [x] WAL em volume no EBS (`tempo-data`, disco da EC2).

## Pronto quando

- Uma requisição a `/api/itens` vira trace com controller → service → repository → SQL. Depende do OTel Java Agent (task 1.6) estar enviando ao Alloy; pipeline deste lado pronto.
- Nenhuma trace de `/api/health`.
