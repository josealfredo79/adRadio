with open("app/services/radio_service.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if line.startswith('    "defaulGUION_SYSTEM_PROMPT'):
        lines[i] = '    "default": "es-MX-JorgeNeural",\n}\n\nGUION_SYSTEM_PROMPT = """Eres un guionista experto en radio AM/FM latinoamericana de los años 80-90.\n'
        break

with open("app/services/radio_service.py", "w", encoding="utf-8") as f:
    f.writelines(lines)
