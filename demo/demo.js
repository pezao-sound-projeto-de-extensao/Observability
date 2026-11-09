import http from 'k6/http';
import { check, fail, sleep } from 'k6';

const BASE = (__ENV.BASE_URL || '').replace(/\/+$/, '');
const ATO = __ENV.ATO || 'normal';
const JSON_HEADERS = { 'Content-Type': 'application/json' };
const ROTAS = ['/dashboard', '/itens', '/clientes', '/encomendas/kpis'];

if (!BASE) fail('defina -e BASE_URL=http://<dns-do-alb>/api');

const CENARIOS = {
  normal: {
    executor: 'constant-arrival-rate',
    exec: 'navegar',
    rate: 1,
    timeUnit: '1s',
    duration: __ENV.DURACAO || '10m',
    preAllocatedVUs: 4,
    maxVUs: 8,
  },
  fila: {
    executor: 'constant-arrival-rate',
    exec: 'recuperarSenha',
    rate: 1,
    timeUnit: '65s',
    duration: __ENV.DURACAO || '5m',
    preAllocatedVUs: 1,
  },
  ataque: {
    executor: 'constant-vus',
    exec: 'atacar',
    vus: 30,
    duration: __ENV.DURACAO || '1m',
  },
};

if (!CENARIOS[ATO]) fail(`ATO inválido: ${ATO} (use normal, fila ou ataque)`);

export const options = {
  scenarios: { [ATO]: CENARIOS[ATO] },
  thresholds: ATO === 'normal' ? { 'checks{ato:normal}': ['rate>0.99'] } : {},
  tags: { ato: ATO },
};

function login() {
  const email = __ENV.EMAIL;
  const senha = __ENV.SENHA;
  if (!email || !senha) fail('defina -e EMAIL=... -e SENHA=... (conta de teste)');
  const res = http.post(`${BASE}/auth/login`, JSON.stringify({ email, senha }),
    { headers: JSON_HEADERS, tags: { name: 'POST /auth/login' } });
  if (res.status !== 200) fail(`login falhou: HTTP ${res.status} ${res.body}`);
  return res.json('accessToken');
}

export function setup() {
  return ATO === 'fila' ? {} : { token: login() };
}

let token;

function get(path) {
  const params = () => ({ headers: { Authorization: `Bearer ${token}` }, tags: { name: `GET ${path}` } });
  let res = http.get(`${BASE}${path}`, params());
  if (res.status === 401 && ATO === 'normal') {
    token = login();
    res = http.get(`${BASE}${path}`, params());
  }
  return res;
}

export function navegar(data) {
  token = token || data.token;
  for (const path of ROTAS) {
    check(get(path), { 'status 200': (r) => r.status === 200 });
  }
}

export function recuperarSenha() {
  const email = __ENV.EMAIL_RECUPERACAO || __ENV.EMAIL;
  if (!email) fail('defina -e EMAIL_RECUPERACAO=<conta de teste ativa>');
  const res = http.post(`${BASE}/auth/esqueci-senha`, JSON.stringify({ email }),
    { headers: JSON_HEADERS, tags: { name: 'POST /auth/esqueci-senha' } });
  console.log(`esqueci-senha: HTTP ${res.status} em ${Math.round(res.timings.duration)} ms`);
}

export function atacar(data) {
  token = token || data.token;
  const res = get(ROTAS[Math.floor(Math.random() * ROTAS.length)]);
  check(res, { 'bloqueado pelo WAF (429)': (r) => r.status === 429 });
  if (res.status === 429) sleep(1);
}
