# 5.4 Cenário de demonstração com k6

**Fase:** F3 · **Repo:** observabilidade (`demo/`) · **Estimativa:** 2 h · **Ref.:** § 17.2, § 18

## O que fazer

- [ ] `demo.js` (base na § 17.2): login no `setup`, 4 VUs, GETs em `/dashboard`, `/itens`, `/clientes`, `/encomendas/kpis`, `sleep(1)`.
- [ ] Credenciais por `-e EMAIL=... -e SENHA=...`, de **conta de teste**.
- [ ] Roteiro escrito:

| Ato | Ação | Mostrar |
|---|---|---|
| 0. Frontend | Navegar no frontend antes do k6 | Trace de `frontend` até o `SELECT` (Faro) |
| 1. Normal | `k6 run demo.js` | Live Tail, RED estável, service graph, waterfall, flame graph do span (Profiles) |
| 2. Falha na fila | `docker service scale stockflow_rabbitmq=0` no `app-1` + `POST /api/auth/esqueci-senha` | `ERROR` → `trace_id` → span do RabbitMQ; exemplar no pico do p95; padrão novo no Logs Drilldown. Depois `=1` |
| 3. Ataque | `k6 run --vus 30 --duration 1m` | 429 no k6; `{origin="waf-logs"} \|= "BLOCK"` ~10–15 s depois |

## Restrições do WAF

- k6 de um **IP no Brasil** e **diferente do IP que abre o Grafana** (senão o ato 3 bloqueia o Grafana).
- Tráfego normal abaixo de ~400 req/min (4 VUs ≈ 240).
- Ato 3 sempre por último.

## Validar antes

- [ ] Como o `esqueci-senha` responde com a fila parada: a publicação é `afterCommit`, então o erro pode aparecer só no span/log, sem mudar o status HTTP.

## Pronto quando

Roteiro ensaiado de ponta a ponta no lab.
