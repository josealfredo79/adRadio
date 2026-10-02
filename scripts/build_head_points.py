"""Genera frontend/src/assets/models/head-points.bin para la cabeza de puntos
de la landing (frontend/src/components/PointFace3D.tsx).

Fuente: "Infinite, 3D Head Scan" de Lee Perry-Smith (Infinite Realities,
www.ir-ltd.net), basado en un trabajo de www.triplegangers.com, licencia
Creative Commons Attribution 3.0. Se descarga del ejemplo de three.js.

Formato (little endian):
  uint32 n · int16[n·3] posición (milésimas) · int8[n·3] normal (·127) ·
  uint8[n] brillo · uint8[n] rol (0 piel, 1 labio de arriba, 2 labio de abajo)

Uso: python3 scripts/build_head_points.py   (necesita numpy)
"""

import json
import os
import struct
import urllib.request

import numpy as np

URL = "https://raw.githubusercontent.com/mrdoob/three.js/dev/examples/models/gltf/LeePerrySmith/LeePerrySmith.glb"
OUT = os.path.join(os.path.dirname(__file__), "..", "frontend", "src", "assets", "models", "head-points.bin")

# El escaneo tiene la cara un poco corrida: este x es el centro de la cara.
FACE_CENTER_X = -0.09
# Boca (unidades del modelo, x ya centrado): comisuras en ±MOUTH_HALF.
MOUTH_HALF = 0.4


def load_glb(data: bytes):
    json_len = struct.unpack("<I", data[12:16])[0]
    gltf = json.loads(data[20 : 20 + json_len])
    off = 20 + json_len
    bin_len = struct.unpack("<I", data[off : off + 4])[0]
    blob = data[off + 8 : off + 8 + bin_len]

    def accessor(i):
        a = gltf["accessors"][i]
        view = gltf["bufferViews"][a["bufferView"]]
        comps = {"SCALAR": 1, "VEC2": 2, "VEC3": 3}[a["type"]]
        dtype = {5126: np.float32, 5123: np.uint16, 5125: np.uint32}[a["componentType"]]
        start = view.get("byteOffset", 0) + a.get("byteOffset", 0)
        arr = np.frombuffer(blob, dtype, a["count"] * comps, start)
        return arr.reshape(-1, comps) if comps > 1 else arr

    prim = gltf["meshes"][0]["primitives"][0]
    pos = accessor(prim["attributes"]["POSITION"]).astype(np.float64)
    nrm = accessor(prim["attributes"]["NORMAL"]).astype(np.float64)
    idx = accessor(prim["indices"]).reshape(-1, 3)
    return pos, nrm, idx


def lip_line(x):
    """Línea donde se juntan los labios (un poco más alta al centro)."""
    return 0.405 + 0.03 * (1 - (x / MOUTH_HALF) ** 2)


def upper_lip(x):
    """Borde de arriba del labio superior, con el arco de Cupido."""
    u = np.abs(x) / MOUTH_HALF
    return lip_line(x) + 0.12 * (1 - u**1.6) - 0.03 * np.exp(-(x**2) / (2 * 0.045**2)) + 0.012


def lower_lip(x):
    """Borde de abajo del labio inferior."""
    u = np.abs(x) / MOUTH_HALF
    return lip_line(x) - 0.15 * np.clip(1 - u**2, 0, 1) ** 0.8


def main():
    with urllib.request.urlopen(URL) as res:
        pos, nrm, idx = load_glb(res.read())
    pos[:, 0] -= FACE_CENTER_X
    nrm /= np.linalg.norm(nrm, axis=1, keepdims=True)

    # Brillo de la piel: más bajo donde la malla es más densa (ojos, orejas,
    # nariz) para que no se encandilen, y desvanecido hacia los hombros.
    a, b, c = pos[idx[:, 0]], pos[idx[:, 1]], pos[idx[:, 2]]
    tri_area = np.linalg.norm(np.cross(b - a, c - a), axis=1) / 2
    vert_area = np.zeros(len(pos))
    for k in range(3):
        np.add.at(vert_area, idx[:, k], tri_area / 3)
    keep = pos[:, 1] > -2.3
    median = np.median(vert_area[keep & (pos[:, 2] > 1)])
    bright = np.clip(vert_area / median, 0.3, 1) ** 0.6
    bright *= np.clip((pos[:, 1] + 2.3) / 1.3, 0, 1) * np.clip((3.0 - np.abs(pos[:, 0])) / 1.0, 0, 1)
    keep &= bright > 0.02
    skin_pos, skin_nrm, skin_bright = pos[keep], nrm[keep], bright[keep]

    # Labios: el escaneo casi no tiene vértices ahí, así que se dibujan
    # curvas densas pegadas a la superficie (z y normal del vértice más
    # cercano de la cara). Cada labio lleva su rol para que el de abajo baje
    # con la mandíbula y el de arriba suba un poco.
    front = pos[:, 2] > 1.5
    fpos, fnrm = pos[front], nrm[front]

    def on_surface(xs, ys):
        pts, nrms = [], []
        for x, y in zip(xs, ys):
            d = (fpos[:, 0] - x) ** 2 + (fpos[:, 1] - y) ** 2
            near = np.argsort(d)[:4]
            w = 1 / (np.sqrt(d[near]) + 1e-3)
            z = (fpos[near, 2] * w).sum() / w.sum() + 0.015
            n = (fnrm[near] * w[:, None]).sum(0)
            pts.append((x, y, z))
            nrms.append(n / np.linalg.norm(n))
        return np.array(pts), np.array(nrms)

    lips_pos, lips_nrm, lips_bright, lips_role = [], [], [], []

    def add_curve(n, y_of, role, brightness, x_half=MOUTH_HALF):
        xs = np.linspace(-x_half, x_half, n)
        p, nr = on_surface(xs, y_of(xs))
        lips_pos.append(p)
        lips_nrm.append(nr)
        lips_bright.append(np.full(n, brightness))
        lips_role.append(np.full(n, role))

    # Labio de arriba: borde, dos filas de relleno y su orilla de adentro.
    add_curve(60, upper_lip, 1, 1.0)
    for t in (0.35, 0.7):
        add_curve(44, lambda x, t=t: lip_line(x) + (upper_lip(x) - lip_line(x)) * (1 - t), 1, 0.55, MOUTH_HALF * 0.95)
    add_curve(56, lambda x: lip_line(x) + 0.006, 1, 1.0)
    # Labio de abajo: su orilla de adentro, relleno y borde.
    add_curve(56, lambda x: lip_line(x) - 0.006, 2, 1.0, MOUTH_HALF * 0.97)
    for t in (0.35, 0.7):
        add_curve(44, lambda x, t=t: lip_line(x) + (lower_lip(x) - lip_line(x)) * t, 2, 0.55, MOUTH_HALF * 0.92)
    add_curve(56, lower_lip, 2, 1.0, MOUTH_HALF * 0.97)

    all_pos = np.concatenate([skin_pos, *lips_pos])
    all_nrm = np.concatenate([skin_nrm, *lips_nrm])
    all_bright = np.concatenate([skin_bright, *lips_bright])
    all_role = np.concatenate([np.zeros(len(skin_pos)), *lips_role])
    n = len(all_pos)
    blob = (
        struct.pack("<I", n)
        + np.round(all_pos * 1000).astype("<i2").tobytes()
        + np.round(all_nrm * 127).astype("i1").tobytes()
        + np.round(all_bright * 255).astype("u1").tobytes()
        + all_role.astype("u1").tobytes()
    )
    with open(OUT, "wb") as f:
        f.write(blob)
    print(f"{n} puntos ({n - len(skin_pos)} de labios), {len(blob)} bytes → {os.path.normpath(OUT)}")


if __name__ == "__main__":
    main()
