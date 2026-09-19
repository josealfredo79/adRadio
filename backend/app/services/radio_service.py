"""
Radio service — re-exported from radio/ package for backward compatibility.
"""
from app.services.radio import generate_radio_ad
from app.services.radio.audio import get_jingle_path, mix_with_jingle
from app.services.radio.scripts import generate_radio_script
from app.services.radio.tts import LOCUTOR_VOICES, text_to_speech

__all__ = [
    "LOCUTOR_VOICES",
    "generate_radio_ad",
    "generate_radio_script",
    "get_jingle_path",
    "mix_with_jingle",
    "text_to_speech",
]
