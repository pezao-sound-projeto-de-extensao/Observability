# Cenário de demonstração (k6)

Task 5.4 (§ 17.2 e § 18). O objetivo é mostrar a stack funcionando ao vivo: gerar tráfego real com o [`demo.js`](demo.js), provocar falhas controladas e seguir a investigação no Grafana.

## Pré-requisitos

- **k6 instalado** na máquina que gera a carga (`winget install k6 --source winget`, `brew install k6` ou `docker run --rm -i grafana/k6`).
- **Backend com a fila.** O `POST /api/auth/esqueci-senha` e a publicação no RabbitMQ entraram na `main` do backend pelo PR #12, em 01/11. A imagem no ECR precisa ser de depois desse merge, senão o ato 2 não tem o que mostrar.
- **Conta de teste** ativa, nunca credenciais reais. No ato 2, o backend envia um e-mail de verdade (SES) quando a fila volta: use um endereço do grupo.
- **Dois IPs diferentes**, os dois no Brasil:
  - O k6 roda de um (por exemplo, o hotspot do celular); o Grafana abre no outro.
  - O WAF tem `BlockNonBrazilTraffic` (403), e o Grafana fica atrás do mesmo WAF. Se o k6 rodasse do IP do Grafana, o ato 3 bloquearia o próprio Grafana justamente quando o Live Tail deveria mostrar o `BLOCK`.
- **Dependências de outras tasks.** Alguns pontos do roteiro só aparecem com outras tasks prontas:

  | No roteiro | Depende de |
  |---|---|
  | Traces, waterfall, service graph | 3.1, 3.2, 4.1 |
  | Painel RED e exemplar no pico do p95 | 4.2 |
  | Botão Profiles (flame graph) | 5.1 |
  | Padrões no Logs Drilldown | 5.3 |
  | Trace que começa no navegador (ato 0) | 5.2 e 3.1 |

## Variáveis

| Variável | Uso |
|---|---|
| `BASE_URL` | `http://<dns-do-alb>/api` (o mesmo `alb_url` do repo infra) |
| `EMAIL`, `SENHA` | Conta de teste para o login (atos 1 e 3) |
| `ATO` | `normal` (padrão), `fila` ou `ataque` |
| `EMAIL_RECUPERACAO` | Ato 2: e-mail de uma conta ativa (padrão: `EMAIL`) |
| `DURACAO` | Sobrescreve a duração do ato (`10m`, `5m` e `1m` por padrão) |

## Roteiro

### Ato 0 — Frontend (antes do k6)

Abrir o frontend pelo DNS do ALB e navegar por algumas telas (itens, clientes, dashboard).

**No Grafana:**
- `{service="frontend"} | logfmt` com `kind="measurement"` (Web Vitals).
- Uma trace que começa em `frontend` (fetch) e termina no `SELECT` do RDS.

O k6 não executa JavaScript, então o Faro só gera dados com um navegador de verdade.

### Ato 1 — Tráfego normal

```bash
k6 run -e BASE_URL=http://<dns-do-alb>/api -e EMAIL=<conta-de-teste> -e SENHA=<senha> demo.js
```

O script faz 1 iteração por segundo com 4 GETs (`/dashboard`, `/itens`, `/clientes`, `/encomendas/kpis`), ou seja, 240 req/min, durante 10 minutos. É taxa fixa, e não VUs com `sleep(1)`: com 4 VUs, 4 GETs por iteração e `sleep(1)`, a carga passaria de 500 req/min e o WAF bloquearia já no ato 1. O token expira em 15 min, e o script faz login de novo quando recebe um 401.

**No Grafana:**
- Live Tail: `{env="production", origin="container-logs"}` com os logs chegando.
- Painel RED estável.
- Service graph `app → mysql`.
- Uma trace qualquer no waterfall e, no span do controller, **Profiles** com o flame graph (Jackson, Hibernate, espera no JDBC).

### Ato 2 — Falha na fila (com o ato 1 rodando)

1. No `app-1` (Swarm da AZ a), parar o RabbitMQ:
   ```bash
   ssh -J ec2-user@<ip-do-bastion> ec2-user@<ip-privado-do-app-1> sudo docker service scale stockflow_rabbitmq=0
   ```
2. Em **outro terminal**, do mesmo IP do k6:
   ```bash
   k6 run -e BASE_URL=http://<dns-do-alb>/api -e ATO=fila -e EMAIL_RECUPERACAO=<conta-de-teste> demo.js
   ```
   É um `POST /auth/esqueci-senha` a cada 65 s, durante 5 minutos. O backend ignora pedidos do mesmo usuário com menos de 1 minuto de intervalo, por isso 65 s.

   Cada swarm tem o próprio RabbitMQ, e só o da AZ a está parado. Só as requisições atendidas por `app-1-a` falham, cerca de metade. O k6 mostra o status e o tempo de cada pedido no console.

**No Grafana:**
- `ERROR` no Live Tail → clique no `trace_id` → span de publish no RabbitMQ com erro ou lento.
- Exemplar no pico do p95, que leva direto à trace.
- Aresta `app → rabbitmq` com erro no service graph e taxa de erro subindo no RED.
- Um padrão novo de erro no Logs Drilldown.

**Depois:**
```bash
ssh -J ec2-user@<ip-do-bastion> ec2-user@<ip-privado-do-app-1> sudo docker service scale stockflow_rabbitmq=1
```

### Ato 3 — Ataque bloqueado (sempre por último)

Interromper o ato 1 e rodar:
```bash
k6 run -e BASE_URL=http://<dns-do-alb>/api -e EMAIL=<conta-de-teste> -e SENHA=<senha> -e ATO=ataque demo.js
```

São 30 VUs sem pausa durante 1 minuto. O IP passa de 500 req/min, e o WAF responde 429. O check `bloqueado pelo WAF (429)` sobe de 0% para quase 100% quando o bloqueio começa.

**No Grafana:** `{origin="waf-logs"} |= "BLOCK"` no Live Tail, até ~45 s depois (atraso do CloudWatch mais o polling do leitor, § 4.5). Mostra o pipeline WAF → CloudWatch → leitor → Alloy → Loki.

O ato 3 vem por último porque o IP do k6 fica bloqueado até a taxa cair abaixo do limite (janela de 1 min no `RateLimitPerIpAggressive`, de 5 min no `RateLimitPerIpModerate`).

## O que validar no ensaio

### Como o esqueci-senha responde com a fila parada

Pelo código da `development`:
- `RecuperacaoSenhaService.solicitar` é `@Transactional`.
- O `PublicadorDeMensagens` só publica no `afterCommit`.
- O token de recuperação é gravado no banco antes da publicação.

Hipóteses a confirmar no lab:
- **Status.** Uma exceção no `afterCommit` sobe para quem chamou depois do commit. Sem `@ExceptionHandler` genérico, a resposta tende a ser **500**, e não 202, mesmo com o token já gravado.
- **Tempo.** Com o serviço em 0 réplicas, o IP virtual do Swarm continua existindo. A conexão AMQP pode ficar pendurada até o timeout de conexão (60 s no cliente do RabbitMQ), em vez de falhar na hora. Isso deixaria a requisição lenta, o que é bom para o exemplar do p95. Mas se passar do idle timeout do ALB (60 s por padrão), o cliente recebe **504**.
- **Consumidores.** Os listeners do app no `app-1` devem registrar erros de reconexão continuamente enquanto a fila estiver parada. São `ERROR`s no Live Tail, mesmo sem tráfego no ato 2.

Anotar o que realmente aconteceu e ajustar a fala do ato 2.

### Checklist

- [ ] Login da conta de teste funciona pelo ALB.
- [ ] Ato 1 roda 10 min sem 429 e com o check `status 200` acima de 99%.
- [ ] Ato 2: anotar status e tempo de resposta e conferir a trace com o span do RabbitMQ.
- [ ] RabbitMQ volta com `scale=1` e o e-mail pendente é enviado.
- [ ] Ato 3: 429 no k6 e `BLOCK` no Live Tail.
- [ ] Roteiro ensaiado de ponta a ponta no lab, com os dois IPs.
