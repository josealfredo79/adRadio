import codecs

with codecs.open("app/services/radio_service.py", "r", encoding="latin-1") as f:
    content = f.read()

bad_str = '"defaulGUION_SYSTEM_PROMPT = """Eres un guionista experto'
good_str = '"default": "es-MX-JorgeNeural",\n}\n\nGUION_SYSTEM_PROMPT = """Eres un guionista experto'

content = content.replace(bad_str, good_str)

with codecs.open("app/services/radio_service.py", "w", encoding="utf-8") as f:
    f.write(content)
