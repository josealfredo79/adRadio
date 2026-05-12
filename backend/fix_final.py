with open("app/services/radio_service.py", "rb") as f:
    data = f.read()

bad_str = b'    "es": "es-ES-AlvaroNeural",    # Espa\xc3\xb1a (fallback)\n    "defaulGUION_SYSTEM_PROMPT = """Eres un guionista experto en radio AM/FM latinoamericana'
good_str = b'    "es": "es-ES-AlvaroNeural",    # Espa\xc3\xb1a (fallback)\n    "default": "es-MX-JorgeNeural",\n}\n\nGUION_SYSTEM_PROMPT = """Eres un guionista experto en radio AM/FM latinoamericana'

if bad_str in data:
    data = data.replace(bad_str, good_str)
    print("Found and replaced bad string.")
else:
    print("Could not find exact byte string. File might have different bytes.")

with open("app/services/radio_service.py", "wb") as f:
    f.write(data)
