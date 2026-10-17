import json
import logging

from job_radar.logs import FormatadorJson


def test_formatador_json_inclui_extras():
    registro = logging.makeLogRecord(
        {"name": "teste", "levelname": "INFO", "msg": "olá %s", "args": ("mundo",), "fonte": "gupy"}
    )
    dados = json.loads(FormatadorJson().format(registro))
    assert dados["msg"] == "olá mundo"
    assert dados["level"] == "INFO"
    assert dados["logger"] == "teste"
    assert dados["fonte"] == "gupy"
    assert "ts" in dados
