# 1.6 OTel Java Agent (traces e métricas)

**Fase:** F2 · **Repo:** backend (imagem) + `docker-compose.yml.j2` do `app` · **Estimativa:** 4 h · **Ref.:** § 5.2, § 5.3, § 17.1

## Contexto

O agente instrumenta sem código: Spring MVC, JDBC/JPA, SQL, RestTemplate/WebClient/Feign, propagação de contexto e erros. Ele também exporta métricas de JVM, HTTP e HikariCP a cada 60 s pelo mesmo OTLP.

## O que fazer

- [ ] Adicionar `opentelemetry-javaagent.jar` (versão mais recente, fixada) em `/otel/` na imagem.
- [ ] No `docker-compose.yml.j2`:
  ```yaml
  environment:
    JAVA_TOOL_OPTIONS: "-javaagent:/otel/opentelemetry-javaagent.jar"
    OTEL_SERVICE_NAME: app
    OTEL_EXPORTER_OTLP_ENDPOINT: "http://{{ otel_endpoint_ip }}:4318"
    OTEL_RESOURCE_ATTRIBUTES: "host.name={{ inventory_hostname }},cloud.availability_zone={{ az }},service.instance.id={{ inventory_hostname }}-{% raw %}{{.Task.Slot}}{% endraw %}"
  ```
- [ ] Os valores **precisam bater** com as labels do Loki (`service.name=app` ↔ `service="app"`, `host.name=app-1` ↔ `host="app-1"`), senão a correlação trace → logs não acha nada.
- [ ] Manter sampling 100% (padrão `always_on`).

## Risco

Compatibilidade com Spring Boot 4 / Spring Framework 7: testar localmente antes do deploy.

## Pronto quando

- A aplicação sobe normalmente com o agente.
- Os logs passam a ter `trace_id`/`span_id` (task 1.5).
- Spans e métricas chegam ao Alloy (task 3.1) com `host.name` `app-1`/`app-2`, não o ID do container.
