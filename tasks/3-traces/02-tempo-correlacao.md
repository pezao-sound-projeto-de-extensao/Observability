# 3.2 Data source Tempo e correlação com o Loki

**Fase:** F2 (F3: link do slow query) · **Repo:** observabilidade (`provisioning/`) · **Estimativa:** 2 h · **Ref.:** § 5.6, § 11, § 18.2

## O que fazer

- [ ] Data source Tempo, `uid: tempo`, `url: http://tempo:3200`.
- [ ] No Loki, derived field (log → trace):
  ```yaml
  derivedFields:
    - name: trace_id
      matcherRegex: '"trace_id":\s*"(\w+)"'
      datasourceUid: tempo
      url: '$${__value.raw}'   # $$ escapa a interpolação do provisioning
  ```
- [ ] No Tempo, `tracesToLogsV2` (trace → logs):
  - `datasourceUid: loki`
  - tags `service.name → service`, `host.name → host`
  - `filterByTraceID: true`, `filterBySpanID: false`
  - `spanStartTimeShift: -1m`, `spanEndTimeShift: 1m`

YAML completo na § 5.6.

### F3: link do slow query do RDS
- [ ] Depois do sqlcommenter (task 1.7), segundo derived field no Loki:
  ```yaml
  - name: trace_id_sql
    matcherRegex: "traceparent='00-(\\w{32})-"
    datasourceUid: tempo
    url: '$${__value.raw}'
  ```

## Pronto quando

O roteiro da § 11 funciona: log `ERROR` → botão do `trace_id` → trace no Tempo → "Logs for this span" volta ao Loki filtrado por `service` e `host`.

F3: uma query em `{origin="rds-logs"}` tem link para a trace que a disparou.

Escopo: só logs do `app` dentro de requisição têm `trace_id`; RDS, WAF, nginx e RabbitMQ correlacionam por horário.
