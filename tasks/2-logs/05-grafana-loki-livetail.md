# 2.5 Grafana, data source Loki e Live Tail

**Fase:** F1 · **Repo:** observabilidade (`provisioning/`) · **Estimativa:** 2 h · **Ref.:** § 4.6, § 5.6, § 6.3, § 18.6

## O que fazer

- [ ] Container `grafana` **13.2+** (Drilldown embutido), estado em volume no EBS.
- [ ] Tudo provisionado por arquivo em `provisioning/`, para recriar o ambiente sem cliques.
- [ ] Data source Loki com `uid: loki` fixo (`url: http://loki:3100`).
- [ ] Trocar a senha padrão do admin (trafega em HTTP).
- [ ] Testar o Live Tail pelo ALB (WebSocket).

## Pronto quando

Em **Explore → Loki → Live**, dados chegando em ~1–3 s (containers) e ~10–15 s (RDS/WAF):

```logql
{env="production"}
{env="production", origin="container-logs"}
{env="production", origin="waf-logs"} |= "BLOCK"
{env="production"} | json | level="ERROR"
```
