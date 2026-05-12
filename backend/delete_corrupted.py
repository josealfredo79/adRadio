with open("app/services/radio_service.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

new_lines = []
for i, line in enumerate(lines):
    if i in (309, 310, 311): # lines 310, 311, 312 in 1-based indexing
        continue
    new_lines.append(line)

with open("app/services/radio_service.py", "w", encoding="utf-8") as f:
    f.writelines(new_lines)
