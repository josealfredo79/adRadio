"""Texto que se le pasa a la voz (TTS) del agente: sin emojis, links ni
marcas de formato. La voz de Edge lee los emojis por su nombre ("cohete",
"cara sonriente") — visto 2026-10-07 con un 🚀 al final de una respuesta."""
import re

_URL = re.compile(r"https?://\S+")
# Emojis y pictogramas, banderas, flechas/símbolos misceláneos, selectores de
# variación, uniones (ZWJ) y teclas (#️⃣).
_EMOJI = re.compile(
    "["
    "\U0001F000-\U0001FAFF"
    "\U0001F1E6-\U0001F1FF"
    "←-⇿"
    "⌀-⏿"
    "①-⓿"
    "■-◿"
    "☀-➿"
    "⤀-⥿"
    "⬀-⯿"
    "〰〽㊗㊙"
    "︎️‍⃣"
    "]+"
)
_MARKS = re.compile(r"[*_~`#>|]+")


def speakable(text: str | None) -> str:
    text = _URL.sub("", text or "")
    text = _EMOJI.sub(" ", text)
    text = _MARKS.sub("", text)
    return " ".join(text.split())
