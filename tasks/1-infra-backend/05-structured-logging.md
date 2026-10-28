# 1.5 Logs estruturados em JSON

**Fase:** F2 (pode entrar já na F1) · **Repo:** backend · **Estimativa:** 2 h · **Ref.:** § 4.2, § 5.6

## O que fazer

- [ ] Em `application-prod.properties`:
  ```properties
  logging.structured.format.console=logstash
  ```
  O structured logging nativo do Spring Boot 4 já inclui o MDC: `trace_id` e `span_id` (preenchidos pelo OTel Agent, task 1.6) e `usuario`.
- [ ] Conferir que nada depende do formato texto antigo.

## Regra

`trace_id`, `span_id`, `usuario`, `level` ficam **na linha** do log. Nunca virar label (explode a cardinalidade do Loki).

## Pronto quando

Um log de erro dentro de uma requisição chega ao Loki assim:

```json
{"@timestamp":"...","level":"ERROR","logger_name":"...","message":"...","trace_id":"4bf92f...","span_id":"00f067...","container_name":"/stockflow_app.2...","env":"production","host":"app-1","origin":"container-logs","service":"app"}
```
