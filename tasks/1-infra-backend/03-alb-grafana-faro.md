# 1.3 ALB: listener do Grafana e regra do Faro

**Fase:** F1 (Grafana), F3 (Faro) · **Repo:** observabilidade · **Estimativa:** 1 h · **Ref.:** § 6.3, § 18.5

## O que fazer

### F1: Grafana
- [ ] `data "aws_lb"` para o `main-alb`.
- [ ] Target group `instance`, porta 3000, para a EC2 de observabilidade. Health check em `/grafana/api/health` (nativo do Grafana).
- [ ] Regra no listener `:80`: caminho `/grafana` → esse target group. Não usar listener próprio na `:3000`: a rede da faculdade bloqueia portas fora do padrão.
- [ ] Grafana com `GF_SERVER_ROOT_URL=http://<dns-do-alb>/grafana/` e `GF_SERVER_SERVE_FROM_SUB_PATH=true` (o Live Tail confere a origem pelo `root_url`).

### F3: Faro
- [ ] Target group `faro-tg`, tipo `instance`, porta `12347`. Health check em `/-/ready` na porta `12345`.
- [ ] Regra no listener `:80`: caminho `/collect` → `faro-tg`. O ALB não reescreve caminhos, então o SDK usa o caminho padrão.

## Atenção

- Listener HTTP: o login do Grafana trafega sem criptografia (sem domínio/ACM no lab). Alternativa: port forward pelo SSM Session Manager.
- O WAF do ALB vale para `/grafana` e `/collect`: as requisições entram no rate limit por IP (relevante na demo, task 5.4).

## Pronto quando

- Grafana abre em `http://<dns-do-alb>/grafana/`, inclusive da rede da faculdade.
- `faro-tg` saudável depois da task 5.2.
