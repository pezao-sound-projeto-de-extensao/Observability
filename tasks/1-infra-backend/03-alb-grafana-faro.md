# 1.3 ALB: listener do Grafana e regra do Faro

**Fase:** F1 (Grafana), F3 (Faro) · **Repo:** observabilidade · **Estimativa:** 1 h · **Ref.:** § 6.3, § 18.5

## O que fazer

### F1: Grafana
- [ ] `data "aws_lb"` para o `main-alb`.
- [ ] Target group `instance`, porta 3000, para a EC2 de observabilidade. Health check em `/api/health` (nativo do Grafana).
- [ ] Listener HTTP `:3000` → esse target group.
- [ ] No SG do ALB, `:3000` **só para os IPs da equipe**.

### F3: Faro
- [ ] Target group `faro-tg`, tipo `instance`, porta `12347`. Health check em `/-/ready` na porta `12345`.
- [ ] Regra no listener `:80`: caminho `/collect` → `faro-tg`. O ALB não reescreve caminhos, então o SDK usa o caminho padrão.

## Atenção

- Listener HTTP: o login do Grafana trafega sem criptografia (sem domínio/ACM no lab). Alternativa: port forward pelo SSM Session Manager.
- O WAF do ALB vale para `:3000` e `/collect`: as requisições entram no rate limit por IP (relevante na demo, task 5.4).

## Pronto quando

- Grafana abre em `http://<dns-do-alb>:3000` de um IP da equipe e não abre de outro.
- `faro-tg` saudável depois da task 5.2.
