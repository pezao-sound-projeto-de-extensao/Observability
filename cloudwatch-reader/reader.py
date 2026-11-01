"""Lê log groups do CloudWatch e envia os eventos ao Alloy pela API de push do Loki.

Cada ciclo relê uma janela recente (lookback) e descarta pelo eventId o que já foi enviado,
porque um evento pode chegar ao CloudWatch bem depois do próprio horário (task 2.4).
"""

import json
import logging
import os
import signal
import sys
import threading
import time
import urllib.request

log = logging.getLogger("cloudwatch-reader")


class Group:
    """Progresso de um log group: até onde já foi lido e o que já foi enviado."""

    def __init__(self, source, now_ms, initial_lookback_ms, saved=None):
        self.name = source["log_group"]
        self.push_url = source["push_url"]
        self.labels = source["labels"]
        self.lookback_ms = source["lookback_seconds"] * 1000
        saved = saved or {}
        self.watermark = saved.get("watermark", now_ms - initial_lookback_ms)
        self.seen = saved.get("seen", {})

    def state(self):
        return {"watermark": self.watermark, "seen": self.seen}


def push(url, labels, events):
    """Envia em ordem de horário. Levanta exceção se o Alloy não aceitar."""
    values = [[str(e["timestamp"] * 1_000_000), e["message"]] for e in events]
    body = json.dumps({"streams": [{"stream": labels, "values": values}]}).encode()
    request = urllib.request.Request(url, body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=30):
        pass


def read_window(client, group, end_ms, send):
    """Lê [watermark - lookback, end_ms], envia o que é novo e só então avança o watermark."""
    start_ms = group.watermark - group.lookback_ms
    args = {"logGroupName": group.name, "startTime": start_ms, "endTime": end_ms}
    sent = 0
    try:
        while True:
            page = client.filter_log_events(**args)
            new = [e for e in page["events"] if e["eventId"] not in group.seen]
            if new:
                new.sort(key=lambda e: e["timestamp"])
                send(group.push_url, group.labels, new)
                group.seen.update((e["eventId"], e["timestamp"]) for e in new)
                sent += len(new)
            if "nextToken" not in page:
                break
            args["nextToken"] = page["nextToken"]
    except client.exceptions.ResourceNotFoundException:
        log.warning("log group %s não existe", group.name)

    group.watermark = end_ms
    oldest_needed = end_ms - group.lookback_ms
    group.seen = {i: ts for i, ts in group.seen.items() if ts >= oldest_needed}
    return sent


def cycle(client, groups, max_window_ms, now_ms, send):
    """Avança todos os grupos juntos, no máximo max_window_ms por ciclo.

    Os dois log groups do RDS caem no mesmo stream do Loki, que recusa o que tiver mais de 1 h
    em relação ao log mais novo. Por isso, depois de uma parada, um não pode passar na frente do outro.

    Um grupo com falha não avança e não impede os outros: o próximo ciclo relê a janela dele,
    e o eventId evita reenvio. Retorna True se ainda há atraso a recuperar e nada falhou.
    """
    behind = False
    failed = False
    for group in groups:
        end_ms = min(now_ms, group.watermark + max_window_ms)
        try:
            sent = read_window(client, group, end_ms, send)
        except Exception:
            log.exception("falha ao ler %s", group.name)
            failed = True
            continue
        if sent:
            log.info("%s: %d eventos enviados", group.name, sent)
        behind = behind or end_ms < now_ms
    return behind and not failed


def load_state(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def save_state(path, groups):
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({g.name: g.state() for g in groups}, f)
    os.replace(tmp, path)


def now():
    return int(time.time() * 1000)


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)

    import boto3
    from botocore.config import Config

    with open(os.environ.get("READER_CONFIG", "/etc/cloudwatch-reader/config.json"), encoding="utf-8") as f:
        config = json.load(f)

    # adaptive: o FilterLogEvents tem cota baixa por conta, e o throttling espera em vez de falhar
    client = boto3.client(
        "logs",
        region_name=config["region"],
        config=Config(retries={"mode": "adaptive", "max_attempts": 10}),
    )
    state_path = config["state_file"]
    saved = load_state(state_path)
    groups = [
        Group(s, now(), config["initial_lookback_seconds"] * 1000, saved.get(s["log_group"]))
        for s in config["sources"]
    ]

    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())

    max_window_ms = config["max_window_seconds"] * 1000
    while not stop.is_set():
        behind = False
        try:
            behind = cycle(client, groups, max_window_ms, now(), push)
            save_state(state_path, groups)
        except OSError:
            log.exception("falha ao salvar o estado")
        if not behind:
            stop.wait(config["poll_interval_seconds"])


if __name__ == "__main__":
    main()
