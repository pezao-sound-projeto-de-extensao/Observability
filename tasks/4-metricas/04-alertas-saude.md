# 4.4 Alertas e dashboard de saúde

**Fase:** F3 (pipeline), F4 (alertas de negócio) · **Repo:** observabilidade (`provisioning/alerting/`) · **Estimativa:** 2 h · **Ref.:** § 18.3, § 14

## O que fazer

### F3: saúde do pipeline
- [ ] Contact point por webhook (Discord ou Telegram), sem SNS.
- [ ] Alertas:

  | Alerta | Consulta |
  |---|---|
  | Pipeline de logs parado (um por host) | `absent_over_time({service="app", host="app-1"}[5m])` |
  | Alloy não entrega | `rate(fluentbit_output_retries_total[5m]) > 0` por 5 min |
  | Descarte no Alloy | `increase(loki_write_dropped_bytes_total[5m]) > 0` |
  | Disco da EC2 | `node_filesystem_avail_bytes{mountpoint="/host/root"} / node_filesystem_size_bytes < 0.15` |
  | Memória perto do limite | `process_resident_memory_bytes{job=~"loki\|tempo\|mimir"}` > 85% do `mem_limit` |

- [ ] Conferir os nomes reais das métricas do Fluent Bit 3.2 (task 1.4).
- [ ] Dashboard "Saúde da observabilidade": ingestão de Loki/Tempo/Mimir, retries e buffer do Fluent Bit por host, memória e disco da EC2.

### F4: alertas de aplicação
- [ ] Combinar com o time quais eventos alertar (taxa de `level="ERROR"`, picos de `BLOCK` no WAF, erros no RDS) e provisionar no mesmo contact point.

## Atenção

Os alertas disparam quando o lab é parado: silenciar no fim de cada sessão.

## Pronto quando

Parar o Loki por 5 min dispara alerta no webhook.
