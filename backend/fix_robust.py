import codecs

with open("app/services/radio_service.py", "rb") as f:
    raw_data = f.read()

# Decode ignoring errors, turning bad bytes into 
text = raw_data.decode("utf-8", errors="replace")

# 1. Fix the dictionary
bad_dict = '"es": "es-ES-AlvaroNeural",    # Espa\ufffda (fallback)\n    "defaulGUION_SYSTEM_PROMPT = """Eres un guionista experto en radio AM/FM latinoamericana'
bad_dict_2 = '"es": "es-ES-AlvaroNeural",    # España (fallback)\n    "defaulGUION_SYSTEM_PROMPT = """Eres un guionista experto en radio AM/FM latinoamericana'

good_dict = '"es": "es-ES-AlvaroNeural",    # España (fallback)\n    "default": "es-MX-JorgeNeural",\n}\n\nGUION_SYSTEM_PROMPT = """Eres un guionista experto en radio AM/FM latinoamericana'

text = text.replace(bad_dict, good_dict).replace(bad_dict_2, good_dict)

# 2. Fix the corrupted string at line 310
# We'll just replace the lines by splitting the text
lines = text.split('\n')
new_lines = []
for i, line in enumerate(lines):
    if 'No te lo pierdas!"' in line and line.startswith('"""'):
        continue # Drop the corrupted string line
    if '- M\ufffdximo 220 palabras' in line:
        line = '- Máximo 220 palabras'
    if '- Temporadas v\ufffdlidas:' in line:
        line = '- Temporadas válidas:'
    new_lines.append(line)

text = '\n'.join(new_lines)

with codecs.open("app/services/radio_service.py", "w", encoding="utf-8") as f:
    f.write(text)
