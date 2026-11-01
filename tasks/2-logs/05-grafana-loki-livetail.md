# 2.5 Grafana, data source Loki e Live Tail

**Fase:** F1 · **Repo:** observabilidade (`provisioning/`) · **Estimativa:** 2 h · **Ref.:** § 4.6, § 5.6, § 6.3, § 18.6

## O que fazer

- [x] Container `grafana` **13.2+** (Drilldown embutido), estado em volume no EBS.
- [x] Tudo provisionado por arquivo em `provisioning/`, para recriar o ambiente sem cliques.
- [x] Data source Loki com `uid: loki` fixo (`url: http://loki:3100`).
- [x] Trocar a senha padrão do admin (trafega em HTTP).
- [x] Testar o Live Tail pelo ALB (WebSocket).
- [x] Provider de dashboards em `provisioning/dashboards/`, lendo os JSONs exportados do Grafana e versionados no repo (a infra é recriada várias vezes e o EBS some no `destroy`). As tasks 4.2 e 4.4 reaproveitam.
- [x] Dashboard "Logs" provisionado, para ler os logs sem o JSON inteiro:
  - Variáveis `service`, `host`, `origin` e `level` (multivalor, com "All").
  - Painel de volume por nível:
    ```logql
    sum by (level) (count_over_time({env="production", service=~"$service", host=~"$host", origin=~"$origin"} | json | drop __error__, __error_details__ | level=~"$level" [$__auto]))
    ```
    O `drop` é necessário porque o RDS manda texto puro: o `| json` marca `__error__` nessas linhas, e uma consulta de métrica falha inteira com esse erro. Linhas sem `level` entram em `level=`.
  - Painel de logs (ordem decrescente, sem quebra de linha), com o JSON completo ao expandir a linha:
    ```logql
    {env="production", service=~"$service", host=~"$host", origin=~"$origin"} | json | level=~"$level" | line_format `{{.host}} {{.level}} {{if or .message .log}}{{.message}}{{.log}}{{else}}{{__line__}}{{end}}`
    ```
    `{{.message}}` vem do JSON do backend (task 1.5) e `{{.log}}` das linhas em texto (nginx, rabbitmq e o backend antes da 1.5); só um dos dois existe em cada linha. RDS e WAF não têm nenhum dos dois e mostram a linha original (`__line__`). A cor por nível depende da 1.5; o link para a trace depende da 1.5 e do derived field da 3.2.
  - O JSON fica em `ansible/roles/observability/files/grafana/provisioning/dashboards/Logs/` e é copiado sem passar pelo Jinja, que quebraria no `{{ }}`.

## Pronto quando

Em **Explore → Loki → Live**, dados chegando em ~1–3 s (containers) e até ~45 s no WAF e até ~2,5 min no RDS (task 2.4):

```logql
{env="production"}
{env="production", origin="container-logs"}
{env="production", origin="waf-logs"} |= "BLOCK"
{env="production"} | json | level="ERROR"
```

O dashboard "Logs" abre com os filtros prontos; o Live Tail do Explore não usa dashboard, então a formatação fica no `line_format` da consulta.

## Resultado no lab (2026-11-01)

Grafana 13.3.0 e Loki 3.7.9 em um ambiente recém-criado: rede, bastion, ALB, WAF e RDS, sem as EC2 de app. O dashboard apareceu na pasta `Logs` sem nenhum clique.

| Teste | Resultado |
|---|---|
| Volume sem o `drop`, com `origin` em "All" | Erro 400 `JSONParserErr` nas linhas do RDS |
| Volume com o `drop`, com `origin` em "All" | Sem erro, com as linhas sem nível em `level=` |
| Logs sem o `__line__` | RDS e WAF só com o host, sem mensagem |
| Logs com o `__line__` | RDS e WAF com a linha original |
| Filtros no navegador | `service` (`app`, `nginx`) com `level` (`ERROR`, `WARN`) e `origin` (`container-logs`) filtraram certo |
| Expandir a linha | Mostra os campos do JSON (`level`, `message`, `trace_id`...), não o texto original |

Live Tail pelo ALB, com `{env="production"}`, do envio até a linha aparecer na tela:

| Origem | Latência |
|---|---|
| Container (linha de teste na porta 3500) | ~1,3 s depois de o push terminar |
| WAF | ~20 s |
| RDS slow query | ~18 s |

**O que não foi medido:**
- **Logs reais de containers:** as linhas de teste imitam os formatos do backend, nginx e rabbitmq, porque o app não foi implantado. A cor por nível funcionou com essas linhas.
- **Error log do RDS no Live Tail:** só o slow query foi cronometrado.
- **Link para a trace:** depende da 3.2.
