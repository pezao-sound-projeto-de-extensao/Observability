# 3.1 Alloy OTLP e Tempo

**Fase:** F2 · **Repo:** observabilidade · **Estimativa:** 4 h · **Ref.:** § 5.5, § 6.5

## O que fazer

### Alloy
- [ ] `otelcol.receiver.otlp` em `0.0.0.0:4318` (HTTP).
- [ ] `otelcol.processor.filter "healthcheck"`: descartar `attributes["url.path"] == "/api/health"`.
- [ ] `otelcol.processor.batch` → `otelcol.exporter.otlphttp "tempo"` (`http://tempo:4318`, `tls.insecure = true`).
- [ ] Saída `metrics` do receiver vai para o batch e depois para o Mimir (task 4.1). Até lá, pode ficar sem destino.

Config completa na § 5.5 (testada localmente em 2026-10-26).

### Tempo
- [ ] Monolítico (sem Kafka), porta 3200 só na rede interna.
- [ ] Storage em `tempo-traces`, credenciais do `LabInstanceProfile`.
- [ ] Retenção: `compactor.compaction.block_retention: 168h`.
- [ ] WAL em volume no EBS.

## Pronto quando

- Uma requisição a `/api/itens` vira trace com controller → service → repository → SQL.
- Nenhuma trace de `/api/health`.
