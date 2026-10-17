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


def test_variavel_vazia_conta_como_ausente(monkeypatch):
    from job_radar.config import Settings

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setenv("FERNET_KEY", "  ")
    settings = Settings()
    assert settings.telegram_bot_token is None
    assert settings.fernet_key is None
