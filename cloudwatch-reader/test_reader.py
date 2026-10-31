import json
import os
import tempfile
import unittest

import reader

MIN = 60_000


class NotFound(Exception):
    pass


class FakeLogs:
    """Simula o FilterLogEvents: filtra por horário do evento e pagina."""

    class exceptions:
        ResourceNotFoundException = NotFound

    def __init__(self, page_size=2):
        self.events = {}
        self.page_size = page_size
        self.calls = []

    def add(self, group, event_id, ts, message=None):
        self.events.setdefault(group, []).append(
            {"eventId": event_id, "timestamp": ts, "message": message or event_id}
        )

    def filter_log_events(self, logGroupName, startTime, endTime, nextToken=None):
        self.calls.append((logGroupName, startTime, endTime))
        if logGroupName not in self.events:
            raise NotFound()
        hits = [e for e in self.events[logGroupName] if startTime <= e["timestamp"] <= endTime]
        offset = int(nextToken or 0)
        page = {"events": hits[offset : offset + self.page_size]}
        if offset + self.page_size < len(hits):
            page["nextToken"] = str(offset + self.page_size)
        return page


class Sink:
    def __init__(self):
        self.lines = []
        self.fail = False

    def __call__(self, url, labels, events):
        if self.fail:
            raise OSError("alloy fora")
        self.lines += [e["message"] for e in events]


def make_group(name="waf", now_ms=100 * MIN, lookback_s=120, saved=None):
    source = {
        "log_group": name,
        "push_url": "http://alloy",
        "labels": {"origin": name},
        "lookback_seconds": lookback_s,
    }
    return reader.Group(source, now_ms, 0, saved)


class ReaderTest(unittest.TestCase):
    def setUp(self):
        self.logs = FakeLogs()
        self.sink = Sink()

    def run_cycle(self, groups, now_ms, max_window_ms=15 * MIN):
        return reader.cycle(self.logs, groups, max_window_ms, now_ms, self.sink)

    def test_evento_atrasado_e_lido_no_ciclo_seguinte(self):
        group = make_group()
        self.run_cycle([group], 100 * MIN)
        # Horário anterior ao fim do ciclo passado, mas só chegou ao CloudWatch agora
        self.logs.add("waf", "late", 100 * MIN - 30_000)
        self.run_cycle([group], 100 * MIN + 15_000)
        self.assertEqual(self.sink.lines, ["late"])

    def test_evento_isolado_apos_janela_vazia_nao_se_perde(self):
        group = make_group()
        for t in range(1, 4):
            self.run_cycle([group], 100 * MIN + t * 15_000)
        self.logs.add("waf", "isolado", 100 * MIN + 44_000)
        self.run_cycle([group], 100 * MIN + 60_000)
        self.assertEqual(self.sink.lines, ["isolado"])

    def test_nao_reenvia_o_que_ja_foi_enviado(self):
        group = make_group()
        self.logs.add("waf", "a", 100 * MIN + 1_000)
        self.run_cycle([group], 100 * MIN + 15_000)
        self.run_cycle([group], 100 * MIN + 30_000)
        self.assertEqual(self.sink.lines, ["a"])

    def test_atraso_maior_que_o_lookback_nao_e_lido(self):
        group = make_group(lookback_s=120)
        self.run_cycle([group], 100 * MIN)
        self.logs.add("waf", "tarde-demais", 100 * MIN - 3 * MIN)
        self.run_cycle([group], 100 * MIN + 15_000)
        self.assertEqual(self.sink.lines, [])

    def test_le_todas_as_paginas(self):
        group = make_group()
        for i in range(5):
            self.logs.add("waf", f"e{i}", 100 * MIN + 1_000 + i)
        self.run_cycle([group], 100 * MIN + 15_000)
        self.assertEqual(sorted(self.sink.lines), [f"e{i}" for i in range(5)])

    def test_falha_no_envio_nao_avanca_nem_duplica(self):
        group = make_group()
        self.logs.add("waf", "a", 100 * MIN + 1_000)
        self.logs.add("waf", "b", 100 * MIN + 2_000)
        self.logs.add("waf", "c", 100 * MIN + 3_000)
        self.sink.fail = True
        self.run_cycle([group], 100 * MIN + 15_000)
        self.assertEqual(group.watermark, 100 * MIN)
        self.sink.fail = False
        self.run_cycle([group], 100 * MIN + 30_000)
        self.assertEqual(sorted(self.sink.lines), ["a", "b", "c"])

    def test_falha_na_segunda_pagina_nao_reenvia_a_primeira(self):
        group = make_group()
        for name, ms in (("a", 1_000), ("b", 2_000), ("c", 3_000)):
            self.logs.add("waf", name, 100 * MIN + ms)
        original = self.sink.__call__
        calls = []

        def fail_second(url, labels, events):
            calls.append(events)
            if len(calls) == 2:
                raise OSError("alloy fora")
            original(url, labels, events)

        reader.cycle(self.logs, [group], 15 * MIN, 100 * MIN + 15_000, fail_second)
        self.assertEqual(self.sink.lines, ["a", "b"])
        self.run_cycle([group], 100 * MIN + 30_000)
        self.assertEqual(sorted(self.sink.lines), ["a", "b", "c"])

    def test_falha_em_um_grupo_nao_impede_os_outros(self):
        groups = [make_group("quebrado"), make_group("waf")]
        self.logs.add("quebrado", "x", 100 * MIN + 1_000)
        self.logs.add("waf", "a", 100 * MIN + 1_000)
        original = self.sink.__call__

        def fail_first(url, labels, events):
            if labels["origin"] == "quebrado":
                raise OSError("sem permissão")
            original(url, labels, events)

        behind = reader.cycle(self.logs, groups, 15 * MIN, 100 * MIN + 15_000, fail_first)
        self.assertFalse(behind)
        self.assertEqual(self.sink.lines, ["a"])
        self.assertEqual(groups[0].watermark, 100 * MIN)
        self.assertEqual(groups[1].watermark, 100 * MIN + 15_000)

    def test_retoma_do_estado_salvo_sem_reenviar(self):
        group = make_group()
        self.logs.add("waf", "antes", 100 * MIN + 1_000)
        self.run_cycle([group], 100 * MIN + 15_000)
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "state.json")
            reader.save_state(path, [group])
            restored = make_group(saved=reader.load_state(path)["waf"])
        self.logs.add("waf", "durante-parada", 100 * MIN + 5 * MIN)
        self.run_cycle([restored], 100 * MIN + 10 * MIN)
        self.assertEqual(self.sink.lines, ["antes", "durante-parada"])

    def test_sem_estado_comeca_no_lookback_inicial(self):
        self.assertEqual(reader.load_state(os.path.join(tempfile.gettempdir(), "nao-existe.json")), {})
        source = {"log_group": "waf", "push_url": "", "labels": {}, "lookback_seconds": 120}
        self.assertEqual(reader.Group(source, 100 * MIN, 60 * MIN).watermark, 40 * MIN)

    def test_grupos_avancam_juntos_ao_recuperar_atraso(self):
        now_ms = 100 * MIN
        groups = [
            make_group("error", saved={"watermark": now_ms - 40 * MIN}),
            make_group("slow", saved={"watermark": now_ms - 40 * MIN}),
        ]
        self.assertTrue(self.run_cycle(groups, now_ms))
        self.assertEqual([g.watermark for g in groups], [now_ms - 25 * MIN] * 2)
        self.assertTrue(self.run_cycle(groups, now_ms))
        self.assertFalse(self.run_cycle(groups, now_ms))
        self.assertEqual([g.watermark for g in groups], [now_ms] * 2)

    def test_log_group_inexistente_nao_trava_os_outros(self):
        groups = [make_group("ausente"), make_group("waf")]
        self.logs.add("waf", "a", 100 * MIN + 1_000)
        self.run_cycle(groups, 100 * MIN + 15_000)
        self.assertEqual(self.sink.lines, ["a"])

    def test_seen_descarta_o_que_saiu_da_janela(self):
        group = make_group(lookback_s=120)
        self.logs.add("waf", "a", 100 * MIN + 1_000)
        self.run_cycle([group], 100 * MIN + 15_000)
        self.assertIn("a", group.seen)
        self.run_cycle([group], 100 * MIN + 10 * MIN)
        self.assertNotIn("a", group.seen)

    def test_push_usa_o_horario_do_evento_em_nanossegundos(self):
        captured = {}

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

        def fake_urlopen(request, timeout):
            captured.update(json.loads(request.data))
            return Response()

        original = reader.urllib.request.urlopen
        reader.urllib.request.urlopen = fake_urlopen
        try:
            reader.push("http://alloy", {"origin": "waf"}, [{"timestamp": 1500, "message": "x"}])
        finally:
            reader.urllib.request.urlopen = original
        self.assertEqual(
            captured,
            {"streams": [{"stream": {"origin": "waf"}, "values": [["1500000000", "x"]]}]},
        )


if __name__ == "__main__":
    unittest.main()
