#!/usr/bin/env python3
"""Resumen de los registros de producción en Railway (solo lectura).

Railway guarda los registros POR DESPLIEGUE: este script recorre los
despliegues del periodo, junta registros de la app y HTTP, y resume:
  1. Peticiones con error (5xx, 499 = el cliente se cansó de esperar) y lentas.
  2. Servicios externos (httpx): Groq, Anthropic, Voyage, Meta… con sus códigos.
  3. Errores de la app (excepciones) y patrones conocidos.

Uso: prod_logs.py [--since 6h] [--services adRadio,worker] [--slow-ms 10000] [--raw DIR]
"""
import argparse
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
TOKEN = re.compile(r"/c/[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+")
HTTP_LINE = re.compile(r"^(\S+) (GET|POST|PUT|PATCH|DELETE|OPTIONS|HEAD) (\S+) (\d{3}) (\d+)ms")
HTTPX = re.compile(r'HTTP Request: (\w+) https?://([^/\s]+)(\S*) "HTTP/[\d.]+ (\d{3})')
EXC = re.compile(r"^([A-Za-z_][\w.]*(?:Error|Exception|Timeout|Cancelled\w*)): ?(.{0,140})")

# (nombre, regex) — lo que ya nos ha pasado y vale la pena contar.
KNOWN = [
    ("Voyage al límite (429, plan sin tarjeta = 3/min)", re.compile(r"voyage.*response_code=429")),
    ("Proveedor de IA falló y se pasó al siguiente", re.compile(r"\[LLM\] .* falló")),
    ("Conexión a la base de datos cerrada", re.compile(r"connection is closed|ConnectionDoesNotExist")),
    ("Cuota de Neon agotada", re.compile(r"exceeded the quota")),
    ("Meta: fuera de la ventana de 24 h (131047)", re.compile(r"131047")),
    ("Meta: límite de envíos / calidad", re.compile(r"131048|131056|130429")),
    ("Webhook duplicado ignorado", re.compile(r"Duplicate webhook ignored")),
]


def railway(*args: str, timeout: int = 60) -> str:
    try:
        out = subprocess.run(["railway", *args], capture_output=True, text=True, timeout=timeout,
                             stdin=subprocess.DEVNULL)
        return out.stdout
    except subprocess.TimeoutExpired:
        print(f"  (railway {' '.join(args[:3])}… tardó demasiado; se omite)", file=sys.stderr)
        return ""


def parse_since(value: str) -> datetime:
    m = re.fullmatch(r"(\d+)([mhd])", value)
    if not m:
        raise SystemExit("--since como 30m, 6h o 2d")
    n, unit = int(m.group(1)), m.group(2)
    delta = {"m": timedelta(minutes=n), "h": timedelta(hours=n), "d": timedelta(days=n)}[unit]
    return datetime.now(timezone.utc) - delta


def deployments(service: str, since: datetime) -> list[str]:
    """Los despliegues que estuvieron vivos en el periodo (el que ya corría al
    empezar y todos los posteriores)."""
    try:
        rows = json.loads(railway("deployment", "list", "-s", service, "--limit", "30", "--json") or "[]")
    except json.JSONDecodeError:
        return []
    rows = [r for r in rows if r.get("status") in ("SUCCESS", "REMOVED", "CRASHED", "FAILED")]
    rows.sort(key=lambda r: r["createdAt"])
    picked: list[str] = []
    for i, r in enumerate(rows):
        created = datetime.fromisoformat(r["createdAt"].replace("Z", "+00:00"))
        nxt = rows[i + 1]["createdAt"] if i + 1 < len(rows) else None
        ended = datetime.fromisoformat(nxt.replace("Z", "+00:00")) if nxt else datetime.now(timezone.utc)
        if ended >= since and r.get("status") != "FAILED":
            picked.append(r["id"])
        _ = created
    return picked


def norm_path(path: str) -> str:
    path = path.split("?")[0]
    return TOKEN.sub("/c/{token}", UUID.sub("{id}", path))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="6h")
    ap.add_argument("--services", default="adRadio,worker")
    ap.add_argument("--slow-ms", type=int, default=10000)
    ap.add_argument("--raw", help="carpeta donde guardar los registros crudos")
    a = ap.parse_args()
    since = parse_since(a.since)

    http_status: Counter = Counter()
    bad: dict[tuple, list[int]] = defaultdict(list)
    apis: dict[str, Counter] = defaultdict(Counter)
    excs: Counter = Counter()
    known: Counter = Counter()
    examples: dict[str, str] = {}
    lines_read = 0

    for service in [s.strip() for s in a.services.split(",") if s.strip()]:
        ids = deployments(service, since)
        print(f"· {service}: {len(ids)} despliegue(s) en el periodo", file=sys.stderr)
        for dep in ids:
            app_logs = railway("logs", "-s", service, dep, "--since", a.since, "--lines", "5000", timeout=90)
            http_logs = railway("logs", "-s", service, dep, "--http", "--since", a.since, "--lines", "5000",
                                timeout=90) if service == "adRadio" else ""
            if a.raw:
                with open(f"{a.raw}/{service}-{dep[:8]}.log", "w") as fh:
                    fh.write(app_logs + "\n--- http ---\n" + http_logs)
            for line in app_logs.splitlines():
                lines_read += 1
                m = HTTPX.search(line)
                if m:
                    apis[m.group(2)][m.group(4)] += 1
                m = EXC.match(line.strip())
                if m:
                    key = f"{service}: {m.group(1)}"
                    excs[key] += 1
                    examples.setdefault(key, m.group(2))
                for name, rx in KNOWN:
                    if rx.search(line):
                        known[f"{service}: {name}"] += 1
            for line in http_logs.splitlines():
                m = HTTP_LINE.match(line.strip())
                if not m:
                    continue
                _ts, method, path, status, ms = m.groups()
                code, ms = int(status), int(ms)
                http_status[f"{status[0]}xx" if code != 499 else "499"] += 1
                if code >= 500 or code == 499 or ms >= a.slow_ms:
                    bad[(method, norm_path(path), code)].append(ms)

    print(f"\n## Producción — últimas {a.since} ({lines_read} líneas de la app)\n")
    print("### Peticiones")
    print(", ".join(f"{k}: {v}" for k, v in sorted(http_status.items())) or "(sin registros HTTP)")
    if bad:
        print("\nCon error o lentas (499 = el cliente se cansó de esperar):")
        for (method, path, code), times in sorted(bad.items(), key=lambda kv: -len(kv[1]))[:15]:
            print(f"- {len(times)}× {code} {method} {path} — máx {max(times) / 1000:.1f} s")
    print("\n### Servicios externos (código: veces)")
    for host, codes in sorted(apis.items(), key=lambda kv: -sum(kv[1].values())):
        flag = "" if set(codes) <= {"200", "201", "202", "204"} else "  ⚠️"
        print(f"- {host}: " + ", ".join(f"{c}: {n}" for c, n in sorted(codes.items())) + flag)
    if not apis:
        print("(ninguna llamada registrada)")
    print("\n### Patrones conocidos")
    for k, v in known.most_common() or [("(ninguno)", "")]:
        print(f"- {k}{f': {v}' if v != '' else ''}")
    print("\n### Excepciones")
    for k, v in excs.most_common(10) or [("(ninguna)", "")]:
        ex = f" — {examples.get(k, '')}" if k in examples else ""
        print(f"- {k}{f': {v}' if v != '' else ''}{ex}")


if __name__ == "__main__":
    main()
