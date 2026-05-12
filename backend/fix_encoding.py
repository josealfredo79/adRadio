with open("app/services/radio_service.py", "rb") as f:
    data = f.read()

# Add coding header if not present
if b"coding: " not in data[:100]:
    data = b"# -*- coding: latin-1 -*-\n" + data

with open("app/services/radio_service.py", "wb") as f:
    f.write(data)
