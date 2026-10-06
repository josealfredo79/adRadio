"""Tests for app.services.meta_templates (create/list WhatsApp templates)."""
from unittest.mock import AsyncMock, patch

import pytest

from app.services.meta_client import MetaApiError
from app.services.meta_templates import (
    TemplateValidationError,
    build_components,
    create_template,
    list_templates,
    normalize_name,
)


class TestNormalizeName:
    def test_lowercases_and_replaces_spaces(self):
        assert normalize_name("  Recordatorio Cita ") == "recordatorio_cita"

    @pytest.mark.parametrize("bad", ["", "promo-octubre", "oferta!", "año_nuevo"])
    def test_rejects_characters_meta_refuses(self, bad):
        with pytest.raises(TemplateValidationError):
            normalize_name(bad)


class TestBuildComponents:
    def test_body_with_examples_and_footer(self):
        components = build_components("Hola {{1}}, tu cita es el {{2}}.", ["Ana", "lunes 10 am"], "Responde STOP para salir")
        assert components == [
            {"type": "BODY", "text": "Hola {{1}}, tu cita es el {{2}}.", "example": {"body_text": [["Ana", "lunes 10 am"]]}},
            {"type": "FOOTER", "text": "Responde STOP para salir"},
        ]

    def test_body_without_variables_has_no_example(self):
        assert build_components("Ya abrimos 🎉", [], None) == [{"type": "BODY", "text": "Ya abrimos 🎉"}]

    def test_repeated_variable_needs_one_example(self):
        components = build_components("Hola {{1}}, {{1}} gracias.", ["Ana"], None)
        assert components[0]["example"] == {"body_text": [["Ana"]]}

    @pytest.mark.parametrize("body,examples", [
        ("", []),
        ("Hola {{2}} ya llegó", ["x"]),           # skips {{1}}
        ("Hola {{1}} ya llegó", []),               # missing example
        ("Hola {{1}} ya llegó", ["  "]),           # blank example
        ("{{1}} ya llegó tu pedido", ["Ana"]),     # starts with a variable
        ("Tu pedido llegó {{1}}", ["Ana"]),        # ends with a variable
        ("x" * 1025, []),
    ])
    def test_rejects_what_meta_would_reject(self, body, examples):
        with pytest.raises(TemplateValidationError):
            build_components(body, examples, None)

    def test_rejects_long_footer(self):
        with pytest.raises(TemplateValidationError):
            build_components("Hola", [], "x" * 61)


class TestCreateTemplate:
    @pytest.mark.asyncio
    async def test_posts_to_the_waba(self):
        with patch("app.services.meta_templates.graph_request", new=AsyncMock(
            return_value={"id": "tpl-1", "status": "PENDING", "category": "UTILITY"},
        )) as mock_gr:
            result = await create_template(
                "waba-1", "tok", name="aviso", category="UTILITY", language="es_MX",
                components=[{"type": "BODY", "text": "Hola"}],
            )
        assert result.ok is True
        assert result.data["id"] == "tpl-1"
        assert mock_gr.call_args.args[0] == "waba-1/message_templates"
        kwargs = mock_gr.call_args.kwargs
        assert kwargs["method"] == "POST"
        assert kwargs["token"] == "tok"
        assert kwargs["body"] == {
            "name": "aviso", "category": "UTILITY", "language": "es_MX",
            "components": [{"type": "BODY", "text": "Hola"}],
        }

    @pytest.mark.asyncio
    async def test_uses_metas_readable_message(self):
        err = MetaApiError("Invalid parameter", status=400, code=100, details={
            "message": "Invalid parameter",
            "error_user_msg": "Ya existe una plantilla con ese nombre en este idioma.",
        })
        with patch("app.services.meta_templates.graph_request", new=AsyncMock(side_effect=err)):
            result = await create_template("waba-1", "tok", name="aviso", category="UTILITY", language="es_MX", components=[])
        assert result.ok is False
        assert result.code == "meta_error"
        assert result.message == "Ya existe una plantilla con ese nombre en este idioma."

    @pytest.mark.asyncio
    async def test_meta_down(self):
        with patch("app.services.meta_templates.graph_request", new=AsyncMock(side_effect=MetaApiError("x", status=503))):
            result = await create_template("waba-1", "tok", name="aviso", category="UTILITY", language="es_MX", components=[])
        assert result.code == "meta_unavailable"


class TestListTemplates:
    @pytest.mark.asyncio
    async def test_maps_body_and_rejection(self):
        with patch("app.services.meta_templates.graph_request", new=AsyncMock(return_value={"data": [
            {"id": "1", "name": "aviso", "language": "es_MX", "category": "UTILITY", "status": "APPROVED",
             "rejected_reason": "NONE",
             "components": [{"type": "HEADER", "text": "x"}, {"type": "BODY", "text": "Hola {{1}}"}]},
            {"id": "2", "name": "promo", "language": "es_MX", "category": "MARKETING", "status": "REJECTED",
             "rejected_reason": "INVALID_FORMAT", "components": []},
        ]})) as mock_gr:
            templates, error = await list_templates("waba-1", "tok")
        assert error is None
        assert mock_gr.call_args.args[0] == "waba-1/message_templates"
        assert [(t.name, t.status, t.body, t.rejected_reason) for t in templates] == [
            ("aviso", "APPROVED", "Hola {{1}}", None),
            ("promo", "REJECTED", "", "INVALID_FORMAT"),
        ]

    @pytest.mark.asyncio
    async def test_error(self):
        with patch("app.services.meta_templates.graph_request", new=AsyncMock(side_effect=MetaApiError("bad", status=400))):
            templates, error = await list_templates("waba-1", "tok")
        assert templates is None
        assert error.code == "meta_error"
