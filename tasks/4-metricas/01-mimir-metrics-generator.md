# 4.1 Mimir, pipeline de métricas e metrics-generator

**Fase:** F3 · **Repo:** observabilidade · **Estimativa:** 5 h · **Ref.:** § 17.1, § 18.1

## O que fazer

### Alloy
- [ ] `otelcol.exporter.prometheus "mimir"` → `prometheus.remote_write "mimir"` (`http://mimir:9009/api/v1/push`, `send_exemplars = true`).

### Mimir
- [ ] `grafana/mimir:3.2.3`, `-target=all`, arquitetura clássica (sem Kafka), volume em `/data`.
- [ ] Config da § 17.1:
  - `multitenancy_enabled: false`;
  - S3 `mimir-metrics` com **prefixos distintos** `blocks`, `ruler`, `alertmanager` (senão recusa a config);
  - ring `inmemory`, `replication_factor: 1` no ingester e no store gateway;
  - `limits.compactor_blocks_retention_period: 15d`;
  - `limits.max_global_exemplars_per_user: 100000` (o padrão 0 descarta exemplars).
- [ ] Validar na AWS que as credenciais do `LabInstanceProfile` são lidas sem chaves.

### Tempo: metrics-generator
- [ ] Ligar, com `remote_write` para `http://mimir:9009/api/v1/push` e `send_exemplars: true`:
  ```yaml
  metrics_generator:
    storage:
      path: /var/tempo/generator/wal
      remote_write:
        - url: http://mimir:9009/api/v1/push
          send_exemplars: true
  overrides:
    defaults:
      metrics_generator:
        processors: [service-graphs, span-metrics]
  ```
  O Drilldown (task 5.3) soma `local-blocks` a essa lista.

## Pronto quando

`jvm_memory_used_bytes` e `http_server_request_duration_seconds_*` consultáveis em `http://mimir:9009/prometheus`, com exemplars.

`traces_spanmetrics_calls_total` e `traces_service_graph_request_total` também no Mimir, sem o ruído de `/api/health`.
