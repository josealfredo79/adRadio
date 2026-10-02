import { useEffect, useRef, useState } from 'react'
import * as THREE from 'three'
import BotFace, { type FaceMood } from '@/components/BotFace'

// Rostro 3D hecho de puntos de luz (estilo "face mesh") que mueve los labios
// con la voz de verdad. Sin modelos ni imágenes: la cabeza se esculpe con
// matemáticas — ~9 mil puntos sobre un elipsoide, con cuencas de ojos, cejas,
// nariz, pómulos, labios y mentón como relieves gaussianos.
//
// - Hablando: la mandíbula y el labio inferior siguen `getLevel()` (el volumen
//   real del audio que suena, ver useSpeaker.level).
// - Escuchando: la boca sigue tu voz (`volume`) y la cabeza asiente un poco.
// - Pensando: mira hacia arriba. Contento: sonrisa.
// Si el navegador no tiene WebGL, se muestra la carita de siempre (BotFace).

interface Props {
  mood: FaceMood
  /** 0–1: volumen del micrófono mientras escucha */
  volume?: number
  /** 0–1: apertura de boca mientras habla (voz real) */
  getLevel?: () => number
  size?: number
}

const N_SAMPLES = 34000
// En pantallas chicas (celulares, a veces de gama baja): menos puntos y
// resolución un poco menor; a ese tamaño casi no se nota y la GPU respira.
const N_SAMPLES_SMALL = 22000

const g = (dx: number, dy: number, sx: number, sy: number) => Math.exp(-((dx * dx) / (2 * sx * sx) + (dy * dy) / (2 * sy * sy)))
const smooth = (a: number, b: number, x: number) => {
  const t = Math.min(1, Math.max(0, (x - a) / (b - a)))
  return t * t * (3 - 2 * t)
}

/** Relieve del rostro (hacia la cámara) en coordenadas de la cabeza: y va de
 * -1 (mentón) a 1 (coronilla); los ojos quedan a media altura, como en una
 * cara real. */
function relief(x: number, y: number): number {
  const ax = Math.abs(x)
  return 1.5 * (
    -0.12 * g(ax - 0.26, y - 0.02, 0.11, 0.07) + // cuencas de los ojos
    0.07 * g(ax - 0.26, y - 0.01, 0.055, 0.04) + // ojos
    0.06 * g(ax - 0.25, y - 0.17, 0.15, 0.04) + // cejas
    0.03 * g(x, y - 0.4, 0.4, 0.25) + // frente
    0.1 * g(x, y + 0.08, 0.05, 0.15) + // tabique
    0.18 * g(x, y + 0.26, 0.07, 0.06) + // punta de la nariz
    0.07 * g(ax - 0.09, y + 0.29, 0.045, 0.04) + // aletas
    -0.03 * g(x, y + 0.36, 0.04, 0.03) + // surco bajo la nariz
    0.07 * g(x, y + 0.43, 0.15, 0.03) + // labio superior
    0.08 * g(x, y + 0.53, 0.13, 0.035) + // labio inferior
    -0.07 * g(x, y + 0.48, 0.16, 0.013) + // línea de la boca
    0.06 * g(ax - 0.38, y + 0.12, 0.12, 0.12) + // pómulos
    -0.04 * g(ax - 0.3, y + 0.32, 0.1, 0.1) + // mejillas (bajo el pómulo)
    0.08 * g(x, y + 0.8, 0.14, 0.09) + // mentón
    -0.05 * g(ax - 0.6, y - 0.08, 0.08, 0.15) // sienes
  )
}

// Luz desde arriba a la izquierda y un poco de frente: marca el relieve.
const LIGHT = new THREE.Vector3(-0.55, 0.6, 0.85).normalize()

interface FaceGeometry {
  base: Float32Array
  colors: Float32Array
  jaw: Float32Array
  upperLip: Float32Array
  corners: Float32Array
  lids: Float32Array
}

function buildFace(samples: number): FaceGeometry {
  const pts: number[] = []
  const shade: number[] = []
  const jaw: number[] = []
  const upper: number[] = []
  const corners: number[] = []
  const lids: number[] = []
  const golden = Math.PI * (3 - Math.sqrt(5))
  const n = new THREE.Vector3()
  const e = 0.004
  for (let i = 0; i < samples; i++) {
    // Esfera de Fibonacci: puntos repartidos parejo, sin rejilla visible.
    const sy = 1 - (i / (samples - 1)) * 2
    const r = Math.sqrt(1 - sy * sy)
    const th = golden * i
    const sx = Math.cos(th) * r
    const sz = Math.sin(th) * r
    if (sz < -0.3) continue // solo el frente y los lados, como la foto

    let x = sx * 0.74
    const y = sy
    let z = sz * 0.82
    // Quijada más angosta hacia el mentón.
    x *= 1 - 0.32 * smooth(-0.3, -1, y)
    z *= 1 - 0.12 * smooth(-0.35, -1, y)
    // El relieve solo en la cara (frente), no en la nuca ni los lados.
    const front = smooth(0.15, 0.65, sz)
    const d = relief(x, y) * front
    z += d
    if (y > 0.93 || y < -0.97) continue
    pts.push(x, y, z)

    // Normal de la superficie: la de la esfera, inclinada por la pendiente
    // del relieve (diferencias finitas). Con ella, luz y sombra de verdad.
    const ddx = ((relief(x + e, y) - relief(x - e, y)) / (2 * e)) * front
    const ddy = ((relief(x, y + e) - relief(x, y - e)) / (2 * e)) * front
    n.set(sx - ddx * sz, sy - ddy * sz, sz).normalize()
    const diffuse = Math.max(0, n.dot(LIGHT))
    const facing = Math.max(0, n.z)
    // De frente se ve el relieve; en la orilla los puntos se enciman y
    // brillarían de más, así que se apagan con el ángulo.
    const b = Math.min(1, (0.2 + 1.1 * diffuse) * (0.2 + 0.8 * facing))
    shade.push(b, b, b)

    jaw.push(front * smooth(-0.48, -0.54, y) * smooth(-1.02, -0.6, y) * Math.exp(-(x * x) / (2 * 0.3 * 0.3)))
    upper.push(front * g(x, y + 0.44, 0.17, 0.04))
    corners.push(front * g(Math.abs(x) - 0.15, y + 0.48, 0.05, 0.05))
    lids.push(front * g(Math.abs(x) - 0.26, y - 0.04, 0.1, 0.03))
  }
  return {
    base: new Float32Array(pts),
    colors: new Float32Array(shade),
    jaw: new Float32Array(jaw),
    upperLip: new Float32Array(upper),
    corners: new Float32Array(corners),
    lids: new Float32Array(lids),
  }
}

const MOOD_COLOR: Record<FaceMood, THREE.Color> = {
  idle: new THREE.Color('#e0e7ff'),
  listening: new THREE.Color('#a5b4fc'),
  thinking: new THREE.Color('#c4b5fd'),
  speaking: new THREE.Color('#ffffff'),
  happy: new THREE.Color('#f0abfc'),
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
    camera.position.set(0, -0.05, 4.4)

    const face = buildFace(small ? N_SAMPLES_SMALL : N_SAMPLES)
    const geo = new THREE.BufferGeometry()
    geo.setAttribute('position', new THREE.BufferAttribute(face.base, 3))
    geo.setAttribute('color', new THREE.BufferAttribute(face.colors, 3))
    // Pesos por punto (cuánto lo mueve la mandíbula, el labio de arriba, la
    // sonrisa y el parpadeo). La deformación la hace la GPU en el shader: por
    // cuadro solo cambian 3 números, no las posiciones de ~25 mil puntos.
    geo.setAttribute('aJaw', new THREE.BufferAttribute(face.jaw, 1))
    geo.setAttribute('aUpper', new THREE.BufferAttribute(face.upperLip, 1))
    geo.setAttribute('aCorner', new THREE.BufferAttribute(face.corners, 1))
    geo.setAttribute('aLid', new THREE.BufferAttribute(face.lids, 1))
    const uniforms = { uOpen: { value: 0 }, uSmile: { value: 0 }, uBlink: { value: 0 } }
    const mat = new THREE.PointsMaterial({
      size: 0.021,
      sizeAttenuation: true,
      vertexColors: true,
      transparent: true,
      opacity: 1,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
      color: MOOD_COLOR.idle.clone(),
    })
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
transformed.y += -uOpen * 0.2 * aJaw + uOpen * 0.025 * aUpper + uSmile * 0.035 * aCorner - uBlink * 0.035 * aLid;
transformed.z -= uOpen * 0.03 * aJaw;`,
        )
    }
    const head = new THREE.Points(geo, mat)
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
      smile += ((m === 'happy' ? 1 : m === 'idle' ? 0.25 : 0) - smile) * 0.08
      if (now > nextBlink) {
        blink = 1
        nextBlink = now + 2500 + Math.random() * 3000
      }
      blink *= 0.82

      uniforms.uOpen.value = open
      uniforms.uSmile.value = smile
      uniforms.uBlink.value = blink

      // Cabeza: gira suave; asiente al escuchar; mira arriba al pensar.
      const sway = reduceMotion ? 0 : 1
      const yaw = Math.sin(t * 0.45) * 0.32 * sway
      const pitch =
        m === 'thinking' ? -0.22 : m === 'listening' ? 0.06 + Math.sin(t * 2.2) * 0.03 * sway : Math.sin(t * 0.33) * 0.04 * sway
      const roll = m === 'thinking' ? 0.1 : m === 'confused' ? -0.12 : 0
      head.rotation.y += (yaw - head.rotation.y) * 0.06
      head.rotation.x += (pitch - head.rotation.x) * 0.06
      head.rotation.z += (roll - head.rotation.z) * 0.06
      mat.color.lerp(MOOD_COLOR[m], 0.06)

      renderer.render(scene, camera)
    }
    raf = requestAnimationFrame(tick)

    return () => {
      cancelAnimationFrame(raf)
      io.disconnect()
      geo.dispose()
      mat.dispose()
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
