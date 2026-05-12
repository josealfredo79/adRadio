with open("app/services/radio_service.py", "rb") as f:
    data = f.read()

bad_str = b'    "defaulGUION_SYSTEM_PROMPT = """Eres un guionista experto en radio AM/FM latinoamericana de los a\xc3\xb1os 80-90.\n'
good_str = b'    "default": "es-MX-JorgeNeural",\n}\n\nGUION_SYSTEM_PROMPT = """Eres un guionista experto en radio AM/FM latinoamericana de los a\xc3\xb1os 80-90.\n'

if bad_str in data:
    data = data.replace(bad_str, good_str)
else:
    print("Could not find bad string!")

data = data.replace(b'\xa1', b'\xc2\xa1') # fix the latin-1 inverted exclamation mark

with open("app/services/radio_service.py", "wb") as f:
    f.write(data)
