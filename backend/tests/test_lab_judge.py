"""Tests for app.services.lab.judge — mocked Claude calls, no real API."""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.lab.judge import _parse_judge_json, evaluate_transcript
from app.services.lab.personas import PERSONAS


def _claude_response(payload: dict | str):
    text = payload if isinstance(payload, str) else json.dumps(payload)
    resp = MagicMock()
    resp.content = [MagicMock(text=text)]
    return resp


VALID_PAYLOAD = {
    "score": 78,
    "summary": "El bot respondió bien pero inventó un precio.",
    "findings": [
        {
            "type": "alucinacion",
            "severity": "alta",
            "evidence": "El bot dijo 'el envío cuesta $50' pero eso no está en el contexto.",
            "suggestion": "Agregar la política de envíos a la base de conocimiento.",
        }
    ],
}


class TestParseJudgeJson:
    def test_parses_clean_json(self):
        result = _parse_judge_json(json.dumps(VALID_PAYLOAD))
        assert result["score"] == 78
        assert len(result["findings"]) == 1
        assert result["findings"][0]["type"] == "alucinacion"

    def test_strips_json_code_fence(self):
        text = "```json\n" + json.dumps(VALID_PAYLOAD) + "\n```"
        result = _parse_judge_json(text)
        assert result["score"] == 78

    def test_strips_bare_code_fence(self):
        text = "```\n" + json.dumps(VALID_PAYLOAD) + "\n```"
        result = _parse_judge_json(text)
        assert result["score"] == 78

    def test_clamps_score_above_100(self):
        result = _parse_judge_json(json.dumps({**VALID_PAYLOAD, "score": 150}))
        assert result["score"] == 100

    def test_clamps_score_below_0(self):
        result = _parse_judge_json(json.dumps({**VALID_PAYLOAD, "score": -20}))
        assert result["score"] == 0

    def test_invalid_finding_type_becomes_otro(self):
        payload = {**VALID_PAYLOAD, "findings": [{**VALID_PAYLOAD["findings"][0], "type": "cosa_rara"}]}
        result = _parse_judge_json(json.dumps(payload))
        assert result["findings"][0]["type"] == "otro"

    def test_invalid_severity_defaults_to_media(self):
        payload = {**VALID_PAYLOAD, "findings": [{**VALID_PAYLOAD["findings"][0], "severity": "urgentisimo"}]}
        result = _parse_judge_json(json.dumps(payload))
        assert result["findings"][0]["severity"] == "media"

    def test_empty_findings_ok(self):
        result = _parse_judge_json(json.dumps({"score": 95, "summary": "Todo bien", "findings": []}))
        assert result["findings"] == []

    def test_malformed_json_raises(self):
        with pytest.raises(json.JSONDecodeError):
            _parse_judge_json("not json at all {{{")


class TestEvaluateTranscript:
    @pytest.mark.asyncio
    async def test_empty_transcript_returns_zero_no_llm_call(self, mock_db, test_user):
        client = MagicMock()
        client.messages.create = AsyncMock()
        with patch("app.services.lab.judge._get_client", return_value=client):
            result = await evaluate_transcript(PERSONAS[0], [], test_user, mock_db)
        assert result["score"] == 0
        client.messages.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_successful_evaluation(self, mock_db, test_user):
        mock_db.execute.return_value = MagicMock(all=lambda: [("Horario: 9am-6pm",)])
        client = MagicMock()
        client.messages.create = AsyncMock(return_value=_claude_response(VALID_PAYLOAD))
        transcript = [
            {"role": "user", "content": "¿cuánto cuesta el envío?"},
            {"role": "assistant", "content": "el envío cuesta $50"},
        ]
        with patch("app.services.lab.judge._get_client", return_value=client):
            result = await evaluate_transcript(PERSONAS[0], transcript, test_user, mock_db)
        assert result["score"] == 78
        assert result["findings"][0]["type"] == "alucinacion"

    @pytest.mark.asyncio
    async def test_api_failure_returns_diagnostic_finding_not_raise(self, mock_db, test_user):
        mock_db.execute.return_value = MagicMock(all=lambda: [])
        client = MagicMock()
        client.messages.create = AsyncMock(side_effect=Exception("anthropic down"))
        transcript = [{"role": "user", "content": "hola"}, {"role": "assistant", "content": "hola!"}]
        with patch("app.services.lab.judge._get_client", return_value=client):
            result = await evaluate_transcript(PERSONAS[0], transcript, test_user, mock_db)
        assert result["score"] == 0
        assert len(result["findings"]) == 1
        assert "anthropic down" in result["findings"][0]["evidence"]

    @pytest.mark.asyncio
    async def test_malformed_judge_response_returns_diagnostic_finding(self, mock_db, test_user):
        mock_db.execute.return_value = MagicMock(all=lambda: [])
        client = MagicMock()
        client.messages.create = AsyncMock(return_value=_claude_response("esto no es json"))
        transcript = [{"role": "user", "content": "hola"}, {"role": "assistant", "content": "hola!"}]
        with patch("app.services.lab.judge._get_client", return_value=client):
            result = await evaluate_transcript(PERSONAS[0], transcript, test_user, mock_db)
        assert result["score"] == 0
        assert result["findings"]
