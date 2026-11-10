# 3.3 Personalização do Grafana

**Fase:** F3 · **Repo:** observabilidade (`provisioning/`, role `observability` do Ansible) · **Estimativa:** 2 h · **Ref.:** § 18.6 · **Depende de:** 2.5, 4.2, 4.4, 5.1, 5.3

## Exceção ao prazo

Esta task **ficou fora do prazo da parte 3**, mas as dependências já fecharam: Logs (2.5), RED (4.2), Saúde (4.4), Profiles (5.1) e Drilldown (5.3) estão todos implementados neste repo. Com isso, a tela inicial e a lista de plugins em uso puderam ser fechadas.

## Regra

Só personalização **por arquivo** (provisioning, variáveis de ambiente, volumes do compose), versionada no repo. Nada por cliques ou API: a infra é recriada várias vezes e o EBS some no `destroy`.

## O que fazer

- [x] **(já)** Variáveis do container `grafana`:
  ```yaml
  GF_USERS_DEFAULT_LANGUAGE: pt-BR
  GF_USERS_DEFAULT_THEME: dark
  GF_NEWS_NEWS_FEED_ENABLED: "false"
  GF_DASHBOARDS_DEFAULT_HOME_DASHBOARD_PATH: /etc/grafana/provisioning/dashboards/inicio.json
  ```
- [x] **(já)** Pastas por assunto (Logs, Métricas, Saúde) com `foldersFromFilesStructure: true` no provider de `provisioning/dashboards/` (task 2.5). Sem dashboard próprio de Traces (o Explore cobre o sinal), então essa pasta não existe até haver um JSON nela.
- [x] Dashboard "Início" (`inicio.json`, tela padrão ao entrar): painel de texto com atalhos (links do dashboard) para Logs, Explore (Loki), RED, Saúde da observabilidade e os 4 apps Drilldown (Logs, Metrics, Traces, Profiles).
- [x] Apps embutidos sem uso com `GF_PLUGINS_DISABLE_PLUGINS`: nenhum a desligar agora — Drilldown (Logs/Metrics/Traces) e Profiles (`grafana-pyroscope-app`, 5.1) estão todos em uso. Comentário deixado no compose explicando a decisão.
- [x] Mudança de seção no menu (`[navigation.app_sections]`): não necessária, nenhum app precisou mudar de seção.
- [ ] **(já, opcional)** Logo do projeto: volume somente leitura sobrescrevendo `public/img/grafana_icon.svg`, `public/img/fav32.png` e `public/img/apple-touch-icon.png` em `/usr/share/grafana/`. **Não é oficial** (a troca de marca do Grafana é só Enterprise): validar na versão fixada e conferir de novo a cada upgrade. O título da aba continua "Grafana". Não implementado — sem assets de logo no repo.


## Fora do escopo

- Esconder itens nativos do menu (Dashboards, Explore, Alerting, Administração): no OSS só dá para desligar o Explore inteiro, e o Live Tail depende dele.
- Favoritos fixados no menu: ficam nas preferências de cada usuário, só por API.

## Pronto quando

- Depois de um `destroy` + `apply`, o primeiro login já abre o "Início" em português, com as pastas e os atalhos funcionando, sem nenhum clique de configuração.
- Nenhum app desligado aparece no menu.
