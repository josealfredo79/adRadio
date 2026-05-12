with open("app/services/radio_service.py", "rb") as f:
    lines = f.readlines()

with open("app/services/radio_service.py", "wb") as f:
    for i, line in enumerate(lines):
        # We know the duplicated error lines are exactly around line 308-313
        # In bytes they will look like b'- M\xc3\xa1ximo 220 palabras\n' or b'- SOLO el texto del locutor\n'
        # Let's just delete the exact literal bytes `b'"""\xc2\xa1No te lo pierdas!"\n'` or `b'"""\xa1No te lo pierdas!"\n'`
        if b'No te lo pierdas!"\n' in line and line.startswith(b'"""'):
            continue
        if b'- M\xa1ximo 220 palabras' in line and b'pierdas' not in line:
            line = b'- M\xc3\xa1ximo 220 palabras\n'
        if b'- M\xc3\xa1ximo 220 palabras' in line and lines[i-1].startswith(b'"""'):
            continue # duplicate
        if b'- SOLO el texto del locutor' in line and lines[i-2].startswith(b'"""'):
            continue # duplicate
        f.write(line)
