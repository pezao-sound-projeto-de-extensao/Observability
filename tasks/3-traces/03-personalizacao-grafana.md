# 3.3 Personalização do Grafana

**Fase:** F3 · **Repo:** observabilidade (`provisioning/`, role `observability` do Ansible) · **Estimativa:** 2 h · **Ref.:** § 18.6 · **Depende de:** 2.5, 4.2, 4.4, 5.1, 5.3

## Exceção ao prazo

Esta task **fica fora do prazo da parte 3**. A tela inicial aponta para dashboards e apps de outras partes (Logs na 2.5, RED na 4.2, Saúde na 4.4, Profiles na 5.1, Drilldown na 5.3), e a lista de plugins a desligar só fecha quando se sabe o que ficou em uso. Os itens marcados com **(já)** podem ser feitos a qualquer momento; o resto só depois das tasks acima.

## Regra

Só personalização **por arquivo** (provisioning, variáveis de ambiente, volumes do compose), versionada no repo. Nada por cliques ou API: a infra é recriada várias vezes e o EBS some no `destroy`.

## O que fazer

- [ ] **(já)** Variáveis do container `grafana`:
  ```yaml
  GF_USERS_DEFAULT_LANGUAGE: pt-BR
  GF_USERS_DEFAULT_THEME: dark
  GF_NEWS_NEWS_FEED_ENABLED: "false"
  GF_DASHBOARDS_DEFAULT_HOME_DASHBOARD_PATH: /etc/grafana/provisioning/dashboards/inicio.json
  ```
- [ ] **(já)** Pastas por assunto (Logs, Traces, Métricas, Saúde) com `foldersFromFilesStructure: true` no provider de `provisioning/dashboards/` (task 2.5).
- [ ] Dashboard "Início" (`inicio.json`, tela padrão ao entrar): painel de texto ou links para o dashboard Logs, Explore (Loki com Live Tail), RED, Saúde da observabilidade e os apps Drilldown em uso.
- [ ] Desligar os apps embutidos sem uso com `GF_PLUGINS_DISABLE_PLUGINS` (IDs conferidos em `/api/plugins` na versão fixada). Ex.: `grafana-pyroscope-app` se a 5.1 não for feita.
- [ ] Se algum app precisar mudar de seção no menu: `[navigation.app_sections]` (`GF_NAVIGATION_APP_SECTIONS_<APP>`).
- [ ] **(já, opcional)** Logo do projeto: volume somente leitura sobrescrevendo `public/img/grafana_icon.svg`, `public/img/fav32.png` e `public/img/apple-touch-icon.png` em `/usr/share/grafana/`. **Não é oficial** (a troca de marca do Grafana é só Enterprise): validar na versão fixada e conferir de novo a cada upgrade. O título da aba continua "Grafana".

## Fora do escopo

- Esconder itens nativos do menu (Dashboards, Explore, Alerting, Administração): no OSS só dá para desligar o Explore inteiro, e o Live Tail depende dele.
- Favoritos fixados no menu: ficam nas preferências de cada usuário, só por API.

## Pronto quando

- Depois de um `destroy` + `apply`, o primeiro login já abre o "Início" em português, com as pastas e os atalhos funcionando, sem nenhum clique de configuração.
- Nenhum app desligado aparece no menu.
