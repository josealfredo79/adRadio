with open("app/services/radio_service.py", "rb") as f:
    data = f.read()

# remove my coding header
if data.startswith(b"# -*- coding: latin-1 -*-\n"):
    data = data[len(b"# -*- coding: latin-1 -*-\n"):]

# replace common latin-1 bytes that broke utf-8 parsing
data = data.replace(b"\xa1", b"\xc2\xa1")
data = data.replace(b"\xbf", b"\xc2\xbf")
data = data.replace(b"\xf1", b"\xc3\xb1")
data = data.replace(b"\xd1", b"\xc3\x91")
data = data.replace(b"\xe1", b"\xc3\xa1")
data = data.replace(b"\xe9", b"\xc3\xa9")
data = data.replace(b"\xed", b"\xc3\xad")
data = data.replace(b"\xf3", b"\xc3\xb3")
data = data.replace(b"\xfa", b"\xc3\xba")
data = data.replace(b"\x97", b"\xe2\x80\x94") # en-dash sometimes copied from word

with open("app/services/radio_service.py", "wb") as f:
    f.write(data)
