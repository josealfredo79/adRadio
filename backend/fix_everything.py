with open("app/services/radio_service.py", "rb") as f:
    data = f.read()

# 1. Fix missing } in LOCUTOR_VOICES
bad_dict = b'"es": "es-ES-AlvaroNeural",    # Espa\xc3\xb1a (fallback)\n    "defaulGUION_SYSTEM_PROMPT = """Eres un guionista experto en radio AM/FM latinoamericana'
good_dict = b'"es": "es-ES-AlvaroNeural",    # Espa\xc3\xb1a (fallback)\n    "default": "es-MX-JorgeNeural",\n}\n\nGUION_SYSTEM_PROMPT = """Eres un guionista experto en radio AM/FM latinoamericana'
if bad_dict in data:
    data = data.replace(bad_dict, good_dict)
else:
    print("WARNING: Could not find missing } syntax to fix!")

# 2. Fix the corrupted `"""\xa1No te lo pierdas!"` line which causes UnicodeDecodeError
# Since it's invalid syntax anyway, let's just delete the exact literal bytes
bad_str = b'"""\xa1No te lo pierdas!"\n- M\xa1ximo 220 palabras\n- SOLO el texto del locutor\n"""\n'
good_str = b'"""\n'
if bad_str in data:
    data = data.replace(bad_str, good_str)
else:
    print("WARNING: Could not find the exactly corrupted string. Will just replace bytes.")

# 3. Replace any remaining \xa1 bytes globally (e.g. M\xa1ximo -> M\xc3\xa1ximo)
data = data.replace(b"\xa1", b"\xc3\xa1")

# Also fix the duplicate missing quotes
data = data.replace(b'"""\xc3\xa1No te lo pierdas!"\n- M\xc3\xa1ximo 220 palabras\n- SOLO el texto del locutor\n"""', b'"""')

with open("app/services/radio_service.py", "wb") as f:
    f.write(data)
