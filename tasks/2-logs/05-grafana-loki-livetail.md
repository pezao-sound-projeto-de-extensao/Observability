# 2.5 Grafana, data source Loki e Live Tail

**Fase:** F1 · **Repo:** observabilidade (`provisioning/`) · **Estimativa:** 2 h · **Ref.:** § 4.6, § 5.6, § 6.3, § 18.6

## O que fazer

- [ ] Container `grafana` **13.2+** (Drilldown embutido), estado em volume no EBS.
- [ ] Tudo provisionado por arquivo em `provisioning/`, para recriar o ambiente sem cliques.
- [ ] Data source Loki com `uid: loki` fixo (`url: http://loki:3100`).
- [ ] Trocar a senha padrão do admin (trafega em HTTP).
- [ ] Testar o Live Tail pelo ALB (WebSocket).
- [ ] Provider de dashboards em `provisioning/dashboards/`, lendo os JSONs exportados do Grafana e versionados no repo (a infra é recriada várias vezes e o EBS some no `destroy`). As tasks 4.2 e 4.4 reaproveitam.
- [ ] Dashboard "Logs" provisionado, para ler os logs sem o JSON inteiro:
  - Variáveis `service`, `host`, `origin` e `level` (multivalor, com "All").
  - Painel de volume por nível:
    ```logql
    sum by (level) (count_over_time({env="production", service=~"$service", host=~"$host", origin=~"$origin"} | json | level=~"$level" [$__auto]))
    ```
  - Painel de logs (ordem decrescente, sem quebra de linha), com o JSON completo ao expandir a linha:
    ```logql
    {env="production", service=~"$service", host=~"$host", origin=~"$origin"} | json | level=~"$level" | line_format "{{.host}} {{.level}} {{.message}}{{.log}}"
    ```
    `{{.message}}` vem do JSON do backend (task 1.5) e `{{.log}}` das linhas em texto (nginx, rabbitmq e o backend antes da 1.5); só um dos dois existe em cada linha. A cor por nível e o link para a trace dependem da 1.5.

## Pronto quando

Em **Explore → Loki → Live**, dados chegando em ~1–3 s (containers) e até ~45 s no WAF e até ~2,5 min no RDS (task 2.4):

```logql
{env="production"}
{env="production", origin="container-logs"}
{env="production", origin="waf-logs"} |= "BLOCK"
{env="production"} | json | level="ERROR"
{env="production", origin="container-logs"} | json | line_format "{{.host}} {{.level}} {{.message}}{{.log}}"
```

O dashboard "Logs" abre com os filtros prontos; o Live Tail do Explore não usa dashboard, então a formatação fica no `line_format` da consulta.
