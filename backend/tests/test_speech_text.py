from app.services.speech_text import speakable


def test_voice_does_not_read_emojis_links_or_marks():
    assert speakable("¡Hola! 😊 Escribe *quiero una cita* 🚀 https://iaradio.online/c/x 👍🏽 🇲🇽 ❤️") == "¡Hola! Escribe quiero una cita"
    assert speakable("Abrimos de 9 a 6.") == "Abrimos de 9 a 6."
    assert speakable(None) == ""
