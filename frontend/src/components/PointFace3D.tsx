import { useEffect, useRef, useState } from 'react'
import * as THREE from 'three'
import BotFace, { type FaceMood } from '@/components/BotFace'
import { FACE_TRIANGLES, FACE_VERTICES } from '@/components/faceMeshData'

// Rostro 3D de puntos (estilo "face mesh") que mueve los labios con la voz de
// verdad. Estilo: puntos celestes en forma de triangulito sobre azul marino,
// dispersos en la piel y CONCENTRADOS en las líneas que dan la expresión
// (párpados, cejas, nariz, labios, contorno). La forma es la de un rostro
// humano real: el modelo canónico de MediaPipe Face Mesh (ver faceMeshData),
// con un punto en cada vértice y en la mitad de cada arista, más su malla tenue.
//
// - Hablando: la mandíbula y el labio inferior siguen `getLevel()` (el volumen
//   real del audio que suena, ver useSpeaker.level).
// - Escuchando: la boca sigue tu voz (`volume`) y la cabeza asiente un poco.
// - Pensando: mira hacia arriba. Contento: sonrisa. Parpadea solo.
// La deformación corre en el vertex shader: por cuadro solo cambian 3 números.
// Si el navegador no tiene WebGL, se muestra la carita de siempre (BotFace).

interface Props {
  mood: FaceMood
  /** 0–1: volumen del micrófono mientras escucha */
  volume?: number
  /** 0–1: apertura de boca mientras habla (voz real) */
  getLevel?: () => number
  size?: number
}

const g = (dx: number, dy: number, sx: number, sy: number) => Math.exp(-((dx * dx) / (2 * sx * sx) + (dy * dy) / (2 * sy * sy)))
const smooth = (a: number, b: number, x: number) => {
  const t = Math.min(1, Math.max(0, (x - a) / (b - a)))
  return t * t * (3 - 2 * t)
}

// ─── Las líneas que dan la expresión (índices de MediaPipe Face Mesh) ──────
// Se dibujan más brillantes que la malla: contorno, cejas, ojos, labios, nariz.
const FEATURE_LOOPS: number[][] = [
  [10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 288, 397, 365, 379, 378, 400, 377, 152, 148, 176, 149, 150, 136, 172, 58, 132, 93, 234, 127, 162, 21, 54, 103, 67, 109, 10], // contorno
  [61, 146, 91, 181, 84, 17, 314, 405, 321, 375, 291, 409, 270, 269, 267, 0, 37, 39, 40, 185, 61], // labios por fuera
  [78, 95, 88, 178, 87, 14, 317, 402, 318, 324, 308, 415, 310, 311, 312, 13, 82, 81, 80, 191, 78], // labios por dentro
  [33, 7, 163, 144, 145, 153, 154, 155, 133, 173, 157, 158, 159, 160, 161, 246, 33], // ojo
  [263, 249, 390, 373, 374, 380, 381, 382, 362, 398, 384, 385, 386, 387, 388, 466, 263], // ojo
  [46, 53, 52, 65, 55], [70, 63, 105, 66, 107], // ceja
  [276, 283, 282, 295, 285], [300, 293, 334, 296, 336], // ceja
  [168, 6, 197, 195, 5, 4, 1], // caballete de la nariz
  [98, 97, 2, 326, 327], [64, 98], [327, 294], // base de la nariz
]
// Centro y semiejes de cada ojo (en cm) para dibujar el iris.
const EYES = [
  { x: -3.15, y: 2.6, z: 3.95 },
  { x: 3.15, y: 2.6, z: 3.95 },
]
const SCALE = 1 / 10.4

interface FaceGeometry {
  /** Malla: los 468 vértices (para las líneas) */
  mesh: Float32Array
  meshWeights: Float32Array[]
  allEdges: number[]
  featureEdges: number[]
  /** Puntos: vértices + mitad de cada arista + iris */
  points: Float32Array
  pointColors: Float32Array
  pointWeights: Float32Array[]
}

/** Pesos de animación de un punto (en cm): mandíbula, labio de arriba, comisuras, párpado. */
function weights(x: number, y: number): [number, number, number, number] {
  const ax = Math.abs(x)
  // Todo lo que está bajo la línea de la boca baja con la mandíbula, menos
  // hacia los lados (la quijada gira, no se desliza).
  const jaw = smooth(-4.05, -4.45, y) * Math.exp(-(x * x) / (2 * 3.4 * 3.4))
  const upper = smooth(-3.0, -3.6, y) * smooth(-4.4, -4.0, y) * Math.exp(-(x * x) / (2 * 1.6 * 1.6))
  const corner = g(ax - 2.45, y + 4.3, 0.7, 0.6)
  const lid = smooth(2.66, 2.8, y) * g(ax - 3.15, y - 2.9, 1.2, 0.35)
  return [jaw, upper, corner, lid]
}

function buildFace(): FaceGeometry {
  const n = FACE_VERTICES.length / 3
  const mesh = new Float32Array(n * 3)
  const meshW = [0, 1, 2, 3].map(() => new Float32Array(n))
  const cm = (i: number, k: number) => FACE_VERTICES[i * 3 + k] / 100
  for (let i = 0; i < n; i++) {
    const x = cm(i, 0)
    const y = cm(i, 1)
    mesh[i * 3] = x * SCALE
    mesh[i * 3 + 1] = (y + 0.4) * SCALE
    mesh[i * 3 + 2] = (cm(i, 2) - 3) * SCALE
    weights(x, y).forEach((w, k) => (meshW[k][i] = w))
  }

  // Aristas únicas de los triángulos.
  const seen = new Set<number>()
  const allEdges: number[] = []
  for (let t = 0; t < FACE_TRIANGLES.length; t += 3) {
    for (let k = 0; k < 3; k++) {
      const a = FACE_TRIANGLES[t + k]
      const b = FACE_TRIANGLES[t + ((k + 1) % 3)]
      const key = Math.min(a, b) * 1000 + Math.max(a, b)
      if (seen.has(key)) continue
      seen.add(key)
      allEdges.push(a, b)
    }
  }
  const featureEdges: number[] = []
  const featureSet = new Set<number>()
  for (const loop of FEATURE_LOOPS) {
    for (let i = 0; i < loop.length; i++) {
      featureSet.add(loop[i])
      if (i > 0) featureEdges.push(loop[i - 1], loop[i])
    }
  }

  // Puntos: cada vértice, la mitad de cada arista y un anillo de iris. Los
  // pesos de los puntos intermedios salen del promedio de sus extremos.
  const pts: number[] = []
  const col: number[] = []
  const w: number[][] = [[], [], [], []]
  const push = (x: number, y: number, z: number, bright: number, ws: number[]) => {
    pts.push(x, y, z)
    col.push(bright, bright, bright)
    ws.forEach((v, k) => w[k].push(v))
  }
  for (let i = 0; i < n; i++) {
    push(mesh[i * 3], mesh[i * 3 + 1], mesh[i * 3 + 2], featureSet.has(i) ? 1 : 0.75, meshW.map((m) => m[i]))
  }
  for (let e = 0; e < allEdges.length; e += 2) {
    const a = allEdges[e]
    const b = allEdges[e + 1]
    const mid = (k: number) => (mesh[a * 3 + k] + mesh[b * 3 + k]) / 2
    push(mid(0), mid(1), mid(2), 0.45, meshW.map((m) => (m[a] + m[b]) / 2))
  }
  for (const eye of EYES) {
    const ring = 12
    for (let i = 0; i < ring; i++) {
      const ang = (i / ring) * Math.PI * 2
      const y = eye.y + Math.sin(ang) * 0.3
      if (y > 2.93 || y < 2.32) continue // el párpado tapa arriba y abajo
      push((eye.x + Math.cos(ang) * 0.3) * SCALE, (y + 0.4) * SCALE, (eye.z - 3) * SCALE, 0.95, [0, 0, 0, 0])
    }
    push(eye.x * SCALE, (eye.y + 0.4) * SCALE, (eye.z - 3) * SCALE, 1, [0, 0, 0, 0]) // pupila
  }
  return {
    mesh,
    meshWeights: meshW,
    allEdges,
    featureEdges,
    points: new Float32Array(pts),
    pointColors: new Float32Array(col),
    pointWeights: w.map((a) => new Float32Array(a)),
  }
}

/** Triangulito como "sprite" de cada punto, como en la referencia. */
function triangleTexture(): THREE.Texture {
  const c = document.createElement('canvas')
  c.width = c.height = 32
  const ctx = c.getContext('2d')
  if (ctx) {
    ctx.fillStyle = '#fff'
    ctx.beginPath()
    ctx.moveTo(16, 4)
    ctx.lineTo(29, 27)
    ctx.lineTo(3, 27)
    ctx.closePath()
    ctx.fill()
  }
  const tex = new THREE.CanvasTexture(c)
  // Sin mipmaps: al achicarse, el triángulo se promediaba con el fondo
  // transparente, quedaba bajo el alphaTest y la mayoría de los puntos se
  // descartaban (se veían diminutos y apagados).
  tex.generateMipmaps = false
  tex.minFilter = THREE.LinearFilter
  tex.magFilter = THREE.LinearFilter
  return tex
}

const MOOD_COLOR: Record<FaceMood, THREE.Color> = {
  idle: new THREE.Color('#5fd3f3'),
  listening: new THREE.Color('#8be9ff'),
  thinking: new THREE.Color('#a5b4fc'),
  speaking: new THREE.Color('#7fe3ff'),
  happy: new THREE.Color('#86efac'),
  confused: new THREE.Color('#fda4af'),
}

export default function PointFace3D({ mood, volume = 0, getLevel, size = 280 }: Props) {
  const mount = useRef<HTMLDivElement>(null)
  const moodRef = useRef(mood)
  const volumeRef = useRef(volume)
  const levelRef = useRef(getLevel)
  const [failed, setFailed] = useState(false)
  moodRef.current = mood
  volumeRef.current = volume
  levelRef.current = getLevel

  useEffect(() => {
    const el = mount.current
    if (!el) return
    let renderer: THREE.WebGLRenderer
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
    } catch {
      setFailed(true)
      return
    }
    const W = size
    const H = Math.round(size * 1.15)
    const small = window.innerWidth < 640
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, small ? 1.5 : 2))
    renderer.setSize(W, H)
    renderer.setClearColor(0x000000, 0)
    el.appendChild(renderer.domElement)

    const scene = new THREE.Scene()
    const camera = new THREE.PerspectiveCamera(30, W / H, 0.1, 20)
    camera.position.set(0, -0.05, 4.2)

    const face = buildFace()
    const uniforms = { uOpen: { value: 0 }, uSmile: { value: 0 }, uBlink: { value: 0 } }
    // Pesos por punto (mandíbula, labio de arriba, sonrisa, parpadeo). La
    // deformación la hace la GPU: por cuadro solo cambian 3 números. Puntos y
    // líneas usan el mismo shader, así se mueven juntos.
    const withWeights = (geo: THREE.BufferGeometry, w: Float32Array[]) => {
      ;['aJaw', 'aUpper', 'aCorner', 'aLid'].forEach((name, k) => geo.setAttribute(name, new THREE.BufferAttribute(w[k], 1)))
      return geo
    }
    const deform = (mat: THREE.Material) => {
      mat.onBeforeCompile = (shader) => {
        Object.assign(shader.uniforms, uniforms)
        shader.vertexShader = shader.vertexShader
          .replace(
            '#include <common>',
            `#include <common>
attribute float aJaw;
attribute float aUpper;
attribute float aCorner;
attribute float aLid;
uniform float uOpen;
uniform float uSmile;
uniform float uBlink;`,
          )
          .replace(
            '#include <begin_vertex>',
            `#include <begin_vertex>
transformed.y += -uOpen * 0.11 * aJaw + uOpen * 0.015 * aUpper + uSmile * 0.025 * aCorner - uBlink * 0.06 * aLid;
transformed.x += uSmile * 0.012 * aCorner * sign(transformed.x);
transformed.z -= uOpen * 0.03 * aJaw;`,
          )
      }
      return mat
    }

    const pointGeo = withWeights(new THREE.BufferGeometry(), face.pointWeights)
    pointGeo.setAttribute('position', new THREE.BufferAttribute(face.points, 3))
    pointGeo.setAttribute('color', new THREE.BufferAttribute(face.pointColors, 3))
    const sprite = triangleTexture()
    const pointMat = deform(new THREE.PointsMaterial({
      size: 0.04,
      sizeAttenuation: true,
      vertexColors: true,
      map: sprite,
      alphaTest: 0.25,
      transparent: true,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
      color: MOOD_COLOR.idle.clone(),
    })) as THREE.PointsMaterial

    // Malla tenue (todas las aristas) y líneas de expresión más marcadas.
    const lineGeo = (edges: number[]) => {
      const geo = withWeights(new THREE.BufferGeometry(), face.meshWeights)
      geo.setAttribute('position', new THREE.BufferAttribute(face.mesh, 3))
      geo.setIndex(edges)
      return geo
    }
    const meshGeo = lineGeo(face.allEdges)
    const featureGeo = lineGeo(face.featureEdges)
    const lineMat = (opacity: number) =>
      deform(new THREE.LineBasicMaterial({
        color: MOOD_COLOR.idle.clone(),
        transparent: true,
        opacity,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
      })) as THREE.LineBasicMaterial
    const meshMat = lineMat(0.13)
    const featureMat = lineMat(0.55)

    const head = new THREE.Group()
    head.add(new THREE.LineSegments(meshGeo, meshMat), new THREE.LineSegments(featureGeo, featureMat), new THREE.Points(pointGeo, pointMat))
    scene.add(head)

    const reduceMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
    let visible = true
    const io = new IntersectionObserver(([entry]) => { visible = entry.isIntersecting })
    io.observe(el)

    let open = 0
    let smile = 0
    let blink = 0
    let nextBlink = performance.now() + 2500
    let raf = 0

    const tick = (now: number) => {
      raf = requestAnimationFrame(tick)
      if (!visible) return
      const t = now / 1000
      const m = moodRef.current

      // Boca: voz real al hablar, tu voz al escuchar.
      // window.__iaradioFaceTest (0–1) solo lo pone una prueba automática: el
      // navegador de pruebas no tiene bocina y el volumen medido sería 0.
      const forced = (window as Window & { __iaradioFaceTest?: number }).__iaradioFaceTest
      const target =
        typeof forced === 'number' ? forced
          : m === 'speaking' ? (levelRef.current?.() ?? 0)
            : m === 'listening' ? volumeRef.current * 0.7
              : 0
      open += (target - open) * (target > open ? 0.55 : 0.22)
      smile += ((m === 'happy' ? 1 : m === 'idle' ? 0.2 : 0) - smile) * 0.08
      if (now > nextBlink) {
        blink = 1
        nextBlink = now + 2500 + Math.random() * 3000
      }
      blink *= 0.82
      uniforms.uOpen.value = open
      uniforms.uSmile.value = smile
      uniforms.uBlink.value = blink

      // Cabeza: casi de frente, como la referencia; gira poquito, asiente al
      // escuchar y mira arriba al pensar.
      const sway = reduceMotion ? 0 : 1
      const yaw = Math.sin(t * 0.45) * 0.2 * sway
      const pitch =
        m === 'thinking' ? -0.2 : m === 'listening' ? 0.06 + Math.sin(t * 2.2) * 0.03 * sway : Math.sin(t * 0.33) * 0.035 * sway
      const roll = m === 'thinking' ? 0.08 : m === 'confused' ? -0.1 : 0
      head.rotation.y += (yaw - head.rotation.y) * 0.06
      head.rotation.x += (pitch - head.rotation.x) * 0.06
      head.rotation.z += (roll - head.rotation.z) * 0.06
      for (const mt of [pointMat, meshMat, featureMat]) mt.color.lerp(MOOD_COLOR[m], 0.06)

      renderer.render(scene, camera)
    }
    raf = requestAnimationFrame(tick)

    return () => {
      cancelAnimationFrame(raf)
      io.disconnect()
      for (const d of [pointGeo, meshGeo, featureGeo, pointMat, meshMat, featureMat]) d.dispose()
      sprite.dispose()
      renderer.dispose()
      if (el.contains(renderer.domElement)) el.removeChild(renderer.domElement)
    }
  }, [size])

  if (failed) return <BotFace mood={mood} volume={volume} size={Math.round(size * 0.6)} />

  return (
    <div
      ref={mount}
      role="img"
      aria-label={mood === 'speaking' ? 'Asistente hablando' : mood === 'listening' ? 'Asistente escuchando' : 'Asistente'}
      style={{ width: size, height: Math.round(size * 1.15) }}
      className="select-none"
    />
  )
}
