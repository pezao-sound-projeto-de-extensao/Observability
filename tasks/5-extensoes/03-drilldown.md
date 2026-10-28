# 5.3 Apps Drilldown

**Fase:** F3 · **Repo:** observabilidade · **Estimativa:** 1 h · **Ref.:** § 18.6 · **Depende de:** 4.1

## Contexto

Os apps Drilldown (Logs, Metrics, Traces, Profiles) exploram os dados por cliques, sem LogQL/PromQL/TraceQL. Vêm embutidos no Grafana 13.2+ (task 2.5).

## O que fazer

### Loki (Logs Drilldown)
- [ ] Somar ao config:
  ```yaml
  pattern_ingester:
    enabled: true
  limits_config:
    allow_structured_metadata: true # exige schema v13
    volume_enabled: true
    discover_log_levels: true
  ```

### Tempo (Traces Drilldown, TraceQL metrics)
- [ ] Somar ao metrics-generator (task 4.1):
  ```yaml
  metrics_generator:
    processor:
      local_blocks:
        flush_to_storage: true
    traces_storage:
      path: /var/tempo/generator/traces # volume no EBS
  overrides:
    defaults:
      metrics_generator:
        processors: [service-graphs, span-metrics, local-blocks]
  ```
- [ ] Conferir a sintaxe na versão fixada e medir a memória do `tempo` depois de ligar.

Metrics Drilldown não exige nada; Profiles Drilldown depende da task 5.1.

## Pronto quando

- Logs Drilldown mostra padrões agrupados (ex.: `Falha ao reservar estoque <_>`).
- Traces Drilldown mostra a comparação "lentas x normais".
