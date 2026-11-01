# 5.2 Frontend com Grafana Faro

**Fase:** F3 · **Repo:** frontend + observabilidade · **Estimativa:** 6 h · **Ref.:** § 18.5 · **Depende de:** 1.3 (regra `/collect` no ALB)

## Contexto

Sem isso, a trace começa no backend e erros de JavaScript e lentidão percebida ficam invisíveis. Com o Faro, a trace começa no clique e vai até o RDS.

```text
Navegador ──> ALB :80 /collect ──> Alloy :12347 ──┬──> Loki  (logs, exceptions, Web Vitals)
                                                  └──> Tempo (spans do navegador)
```

## O que fazer

### Frontend
- [ ] Instalar `@grafana/faro-web-sdk` e `@grafana/faro-web-tracing`.
- [ ] No bootstrap:
  ```javascript
  import { initializeFaro, getWebInstrumentations } from '@grafana/faro-web-sdk';
  import { TracingInstrumentation } from '@grafana/faro-web-tracing';

  initializeFaro({
    url: '/collect', // mesma origem, pelo main-alb: sem CORS
    app: { name: 'frontend', version: '1.0.0', environment: 'production' },
    instrumentations: [...getWebInstrumentations(), new TracingInstrumentation()],
  });
  ```
  Mesma origem que `/api`: o `traceparent` é propagado sem `propagateTraceHeaderCorsUrls`.

### Alloy
- [ ] `faro.receiver "frontend"` na porta 12347, `max_allowed_payload_size = "1MiB"`, `rate_limiting { rate = 50, burst_size = 100 }`.
- [ ] Logs → `loki.process "faro"` com labels estáticas `env=production, origin=frontend, service=frontend` → `loki.write.default`.
- [ ] Traces → `otelcol.processor.batch.default` (mesmo caminho dos backends).
- [ ] `/-/ready` na 12345 responde (health check do `faro-tg`).

### Grafana
- [ ] Derived field extra no Loki para as linhas logfmt do Faro:
  ```yaml
  - name: trace_id_faro
    matcherRegex: 'trace_id=(\w+)'
    datasourceUid: tempo
    url: '$${__value.raw}'
  ```

### Logs do container do front (nginx do `web`)
O Faro cobre o navegador; os logs do servidor do front (nginx que serve o `dist`, em `web-1`/`web-2`) hoje **não são coletados**: o serviço `web` não tem `logging` no compose, e o Fluent Bit só roda nos nós app (`node.role == manager`).
- [ ] Repo infra (`DevOps`), `docker-compose.yml.j2`: Fluent Bit com `deploy: mode: global` (em vez de `*back`), para rodar também nos nós web; `logging` fluentd com `tag: web` no serviço `web`. Usar `service="web"` no Loki, não `frontend` (já é do Faro).
- [ ] `deploy.yml`: renderizar `fluent-bit.conf.j2` em `/opt/app/fluent-bit/` nos nós web **antes** do `stack deploy`. O `otel_endpoint_ip` só existe em `group_vars/app.yml`: passar com `hostvars[groups['app'][0]].otel_endpoint_ip`.
- [ ] Host no padrão EC2 + AZ, igual aos nós app: `web-1-a`, `web-2-b` (`{{ inventory_hostname }}-{{ az }}`).
- [ ] Repo observabilidade, `terraform/compute.tf`: liberar 3500 (logs) e 9999 (métricas do Fluent Bit) também para o `web-sg` (`data "aws_security_group" "web"`). Hoje o mapa `ingress` aceita um SG por porta: trocar o valor por lista.
- [ ] Alloy, `loki.process "level"`: incluir `web` no `INFO` padrão e classificar o formato texto do nginx (`combined`): status 5xx → `ERROR`, 4xx → `WARN` (ex.: `|~ "HTTP/[0-9.]+.{1,2} 5[0-9][0-9] "`, o `.{1,2}` absorve o `\"` do JSON do Fluent Bit); `[error]` → `ERROR`, `[warn]` → `WARN` no log de erro do nginx.
- [ ] O `/health` do front já tem `access_log off` no `Dockerfile`: o health check do ALB não polui.

## Segurança

O `/collect` é o único endpoint de ingestão **público**. Mitigações: rate limit e limite de payload no receiver, WAF no ALB. Risco aceito: ruído nos dados do frontend.

## Pronto quando

- Navegando no frontend, aparece uma trace que começa em `frontend` e termina no `SELECT` do RDS, e a aresta `frontend → app` no service graph.
- `{service="frontend"} | logfmt | kind="exception"` e `kind="measurement"` com dados.
- `{service="web"}` com `host` `web-1-a` e `web-2-b`, e nível preenchido (sem `unknown`) no dashboard "Logs".
