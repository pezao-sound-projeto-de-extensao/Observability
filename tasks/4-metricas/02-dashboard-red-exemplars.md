# 4.2 Dashboard RED, service graph e exemplars

**Fase:** F3 · **Repo:** observabilidade (`provisioning/`) · **Estimativa:** 3 h · **Ref.:** § 17.1, § 18.1

## O que fazer

- [ ] Data source Prometheus `uid: mimir`, `url: http://mimir:9009/prometheus`, com exemplars para os **dois nomes** de label:
  ```yaml
  exemplarTraceIdDestinations:
    - name: trace_id   # OTel Agent
      datasourceUid: tempo
    - name: traceID    # metrics-generator do Tempo
      datasourceUid: tempo
  ```
- [ ] No data source Tempo: `serviceMap.datasourceUid: mimir`.
- [ ] Dashboard em JSON no repo, pelo provider de `provisioning/dashboards/` (criado na task 2.5); a infra é recriada várias vezes e o EBS some no `destroy`.
- [ ] Dashboard RED provisionado:
  ```promql
  sum by (span_name) (rate(traces_spanmetrics_calls_total{span_kind="SPAN_KIND_SERVER"}[5m]))

  sum(rate(traces_spanmetrics_calls_total{status_code="STATUS_CODE_ERROR"}[5m]))
    / sum(rate(traces_spanmetrics_calls_total[5m]))

  histogram_quantile(0.95, sum by (le, span_name) (rate(traces_spanmetrics_latency_bucket{span_kind="SPAN_KIND_SERVER"}[5m])))
  ```
  Com **Exemplars** ligado nos painéis de latência.
- [ ] Painéis de JVM/HikariCP a partir das métricas do agente, filtrando `http_route!="/api/health"`.

## Pronto quando

- Dashboard RED com dados; clique em um exemplar abre a trace.
- Service Graph (Explore → Tempo) mostra `app → mysql` e `app → rabbitmq`.
