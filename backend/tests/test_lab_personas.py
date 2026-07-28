"""Tests for app.services.lab.personas — structural sanity, no LLM calls."""
from app.services.lab.personas import PERSONAS


class TestPersonas:
    def test_six_personas_defined(self):
        assert len(PERSONAS) == 6

    def test_all_keys_unique(self):
        keys = [p.key for p in PERSONAS]
        assert len(keys) == len(set(keys))

    def test_all_fields_non_empty(self):
        for p in PERSONAS:
            assert p.key.strip()
            assert p.label.strip()
            assert p.goal.strip()
            assert p.system_prompt.strip()
            assert p.max_turns > 0

    def test_keys_are_snake_case_identifiers(self):
        for p in PERSONAS:
            assert p.key.replace("_", "").isalnum()
            assert p.key == p.key.lower()

    def test_expected_persona_keys_present(self):
        keys = {p.key for p in PERSONAS}
        assert keys == {
            "comprador_decidido",
            "pregunton_precios",
            "cliente_enojado",
            "pregunta_lo_que_no_sabes",
            "exige_humano",
            "informal_typos",
        }
