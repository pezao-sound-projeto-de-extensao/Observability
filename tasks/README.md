# Tasks: Observabilidade própria na AWS

Quebra do documento [`README.md`](../README.md) em 5 partes. A parte 1 junta tudo que mexe na AWS e na aplicação (Terraform, Fluent Bit, backend). As partes 2 a 5 são **fatias verticais por sinal**: cada uma leva o pipeline completo daquele sinal, do Alloy ao Grafana, para quem pegar a parte entregar algo visível no fim. As referências "§ X" apontam para seções do documento.

Cada task indica a **fase** do roadmap (§ 14): F1 logs, F2 tracing, F3 complementos, F4 evolução.

| Parte | Escopo | Estimativa |
|---|---|---|
| [1-infra-backend](1-infra-backend/) | Terraform (repo infra e repo observabilidade), Fluent Bit nos nós app, logs JSON e OTel Agent no backend | ~16 h |
| [2-logs](2-logs/) | Compose, Loki, Alloy (containers e CloudWatch), Grafana com Live Tail | ~14 h |
| [3-traces](3-traces/) | Alloy OTLP, Tempo, correlação log ↔ trace, personalização do Grafana | ~6 h + 2 h (3.3, fora do prazo) |
| [4-metricas](4-metricas/) | Mimir, metrics-generator, dashboard RED, exemplars, self-monitoring, alertas | ~12 h |
| [5-extensoes](5-extensoes/) | Pyroscope, Faro (frontend), Drilldown, demo k6, evolução | ~12 h |

**Total:** ~62 h + ~20% de folga para bloqueios do Learner Lab ≈ 74 h. A 3.3 depende de tasks de outras partes e é exceção ao prazo da parte 3.

## Tasks

**1-infra-backend**
- [1.1 Log groups do RDS/WAF, export do RDS e logging do WAF](1-infra-backend/01-log-groups-rds-waf.md) · F1
- [1.2 EC2 de observabilidade, security group e buckets S3](1-infra-backend/02-ec2-observabilidade-buckets.md) · F1
- [1.3 ALB: listener do Grafana e regra do Faro](1-infra-backend/03-alb-grafana-faro.md) · F1, F3
- [1.4 Fluent Bit: deploy e métricas](1-infra-backend/04-fluent-bit.md) · F1, F3
- [1.5 Logs estruturados em JSON](1-infra-backend/05-structured-logging.md) · F2
- [1.6 OTel Java Agent (traces e métricas)](1-infra-backend/06-otel-java-agent.md) · F2
- [1.7 Extensões do agente: sqlcommenter e Pyroscope](1-infra-backend/07-sqlcommenter-pyroscope.md) · F3
- [1.8 Spans de negócio](1-infra-backend/08-spans-negocio.md) · F4
- [1.9 Reavaliar access logs do ALB](1-infra-backend/09-alb-access-logs.md) · F4

**2-logs**
- [2.1 Docker Compose base via Ansible](2-logs/01-compose-base.md) · F1
- [2.2 Loki](2-logs/02-loki.md) · F1
- [2.3 Alloy: logs dos containers e arquivo bruto no S3](2-logs/03-alloy-logs-containers.md) · F1
- [2.4 Leitor do CloudWatch: RDS e WAF](2-logs/04-cloudwatch-reader.md) · F1
- [2.5 Grafana, data source Loki e Live Tail](2-logs/05-grafana-loki-livetail.md) · F1

**3-traces**
- [3.1 Alloy OTLP e Tempo](3-traces/01-alloy-otlp-tempo.md) · F2
- [3.2 Data source Tempo e correlação com o Loki](3-traces/02-tempo-correlacao.md) · F2, F3
- [3.3 Personalização do Grafana](3-traces/03-personalizacao-grafana.md) · F3 · **fora do prazo** (depende de 2.5, 4.2, 4.4, 5.1, 5.3)

**4-metricas**
- [4.1 Mimir, pipeline de métricas e metrics-generator](4-metricas/01-mimir-metrics-generator.md) · F3
- [4.2 Dashboard RED, service graph e exemplars](4-metricas/02-dashboard-red-exemplars.md) · F3
- [4.3 Self-monitoring da stack](4-metricas/03-self-monitoring.md) · F3
- [4.4 Alertas e dashboard de saúde](4-metricas/04-alertas-saude.md) · F3, F4

**5-extensoes**
- [5.1 Profiling contínuo com Pyroscope](5-extensoes/01-pyroscope.md) · F3
- [5.2 Frontend com Grafana Faro](5-extensoes/02-faro-frontend.md) · F3
- [5.3 Apps Drilldown](5-extensoes/03-drilldown.md) · F3
- [5.4 Cenário de demonstração com k6](5-extensoes/04-demo-k6.md) · F3
- [5.5 Capacidade, retenção e sampling](5-extensoes/05-capacidade-retencao.md) · F4

## Ordem de execução

```text
1.1, 1.2 ─> 1.3, 1.4 ─> 2.1 ─> 2.2 ─> 2.3 ─> 2.4 ─> 2.5           (logs no ar)
1.5, 1.6 ─────────────────────────────> 3.1 ─> 3.2                (traces no ar)
                                         └──> 4.1 ─> 4.2, 4.3 ─> 4.4
1.7 ─> 5.1;  1.3 ─> 5.2;  4.1 ─> 5.3;  tudo ─> 5.4
2.5, 4.2, 4.4, 5.1, 5.3 ─> 3.3                                      (fora do prazo)
```

A parte 1 é pré-requisito das outras (EC2, IP fixo, portas). As partes 3, 4 e 5 podem andar em paralelo depois que a 2 subir o Compose e o Grafana.

Contrato entre as partes: o **IP privado fixo** da EC2 (`otel_endpoint_ip`, task 1.2) e os **UIDs fixos** dos data sources (`loki`, `tempo`, `mimir`, `pyroscope`). A ordem de apply é infra → observabilidade (§ 15).
