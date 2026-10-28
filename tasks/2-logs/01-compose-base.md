# 2.1 Docker Compose base via Ansible

**Fase:** F1 · **Repo:** observabilidade · **Estimativa:** 1 h · **Ref.:** § 6.3, § 6.4, § 6.6

## O que fazer

- [ ] Role Ansible que instala Docker + Compose na EC2 (mesmo padrão EC2 + Ansible + Docker do projeto).
- [ ] `docker-compose.yml` com um container por componente. Na F1: `alloy`, `loki`, `grafana`; os outros entram nas tasks 3.1, 4.1 e 5.1.
- [ ] Em todos os serviços:
  - `restart: unless-stopped` (as EC2 param no fim de cada sessão do lab).
  - `mem_limit`: alloy 768m, loki 1g, tempo 1g, mimir 1g, pyroscope 768m, grafana 256m.
  - Volume nomeado para dados, no EBS.
  - **Imagens com versão fixada**.
- [ ] Publicar no host só as portas do `alloy` (3500, 4318, 4040, 9999, 12347, 12345) e a `3000` do `grafana`. Loki, Tempo, Mimir e Pyroscope **não** publicam portas (sem autenticação).
- [ ] Alloy com `--stability.level=experimental` (exigido por `awscloudwatch` e `awss3`; vale para o processo todo).
- [ ] Mudanças de config do Alloy via `/-/reload`, não restart: um restart interrompe logs, traces e métricas ao mesmo tempo.

## Pronto quando

- `docker compose up -d` via Ansible sobe tudo, e os containers voltam sozinhos após reboot.
- `docker stats` mostra os limites de memória.
