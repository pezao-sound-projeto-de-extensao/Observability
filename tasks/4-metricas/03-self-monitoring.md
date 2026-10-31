# 4.3 Self-monitoring da stack

**Fase:** F3 · **Repo:** observabilidade · **Estimativa:** 2 h · **Ref.:** § 18.3

## Contexto

Sem isso, o pipeline pode parar em silêncio. Esta task coleta as métricas; os alertas e o dashboard ficam na task 4.4.

## O que fazer

- [ ] `prometheus.exporter.self "alloy"`.
- [ ] `prometheus.exporter.unix "host"` com `/proc`, `/sys` e `/` do host montados read-only no container (`/host/proc`, `/host/sys`, `/host/root`).
- [ ] `prometheus.scrape "stack"` com os dois exporters + `loki:3100`, `tempo:3200`, `mimir:9009`, `grafana:3000` (e `pyroscope:4040` depois da task 5.1) → `prometheus.remote_write.mimir`.
- [ ] `prometheus.receive_http "fluentbit"` na porta 9999 → Mimir (métricas enviadas pela task 1.4).

## Pronto quando

No Mimir: `loki_write_dropped_bytes_total` e `loki_write_dropped_entries_total` (a contagem usada nas medições da 2.4), `node_filesystem_avail_bytes`, `process_resident_memory_bytes` por job e as métricas do Fluent Bit por `host`.
