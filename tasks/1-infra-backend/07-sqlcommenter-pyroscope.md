# 1.7 Extensões do agente: sqlcommenter e Pyroscope

**Fase:** F3 · **Repo:** backend (imagem) + `docker-compose.yml.j2` do `app` · **Estimativa:** 3 h · **Ref.:** § 18.2, § 18.4

## sqlcommenter: `trace_id` no slow query do RDS

- [ ] `OTEL_INSTRUMENTATION_JDBC_EXPERIMENTAL_SQLCOMMENTER_ENABLED: "true"`.
- [ ] Validar que o SQL sai com `/*traceparent='00-<trace_id>-<span_id>-01'*/` e que o comentário chega ao slow query log do RDS.
- [ ] Medir o impacto sob carga (k6 antes/depois). Esperado pequeno com `useServerPrepStmts=false` (padrão do Connector/J).

## Pyroscope: profiling contínuo com span profiles

- [ ] Adicionar `pyroscope-otel-javaagent-extension.jar` em `/otel/` na imagem.
- [ ] Variáveis:
  ```yaml
  OTEL_JAVAAGENT_EXTENSIONS: /otel/pyroscope-otel-javaagent-extension.jar
  OTEL_PYROSCOPE_START_PROFILING: "true"
  OTEL_PYROSCOPE_ADD_PROFILE_URL: "false"
  OTEL_PYROSCOPE_ADD_PROFILE_BASELINE_URL: "false"
  PYROSCOPE_APPLICATION_NAME: app
  PYROSCOPE_SERVER_ADDRESS: "http://{{ otel_endpoint_ip }}:4040" # Alloy, não o Pyroscope
  PYROSCOPE_LABELS: "host={{ inventory_hostname }}"
  PYROSCOPE_FORMAT: jfr
  PYROSCOPE_PROFILER_EVENT: itimer # sem privilégio de perf_event
  PYROSCOPE_PROFILER_ALLOC: 512k
  PYROSCOPE_PROFILER_LOCK: 10ms
  PYROSCOPE_UPLOAD_INTERVAL: 15s
  ```
- [ ] Testar com Spring Boot 4 e a versão fixada do agente; medir overhead de CPU com k6.

## Atenção

Os dois são experimentais ou dependem de extensão: fixar versões do agente e da extensão.

## Pronto quando

- Uma query lenta no RDS tem o `traceparent` no texto.
- Profiles chegam ao Pyroscope (task 5.1) com `service_name=app`.
