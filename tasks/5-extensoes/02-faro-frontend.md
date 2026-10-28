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

## Segurança

O `/collect` é o único endpoint de ingestão **público**. Mitigações: rate limit e limite de payload no receiver, WAF no ALB. Risco aceito: ruído nos dados do frontend.

## Pronto quando

- Navegando no frontend, aparece uma trace que começa em `frontend` e termina no `SELECT` do RDS, e a aresta `frontend → app` no service graph.
- `{service="frontend"} | logfmt | kind="exception"` e `kind="measurement"` com dados.
