import { useEffect, useRef, useState } from 'react'
import * as THREE from 'three'
import BotFace, { type FaceMood } from '@/components/BotFace'
import { weights } from '@/components/headWeights'
import headMeshUrl from '@/assets/models/head-mesh.bin?url'

// Cabeza 3D "de modelado": piel sólida con luz, encima las líneas de su malla
// y un puntito en cada vértice, con globos oculares y el interior de la boca.
// Es la misma cabeza escaneada que PointFace3D (Lee Perry-Smith, CC BY 3.0;
// ver ahí el crédito y las unidades) y se mueve igual: los labios siguen la
// voz real, parpadea y la cabeza gira.
//
// El escaneo trae los labios unidos y los ojos cerrados; el generador
// (scripts/build_head_points.py) separa los labios y abre una almendra en cada
// ojo. Así al bajar la mandíbula los labios se separan sin estirar la piel
// (detrás va una cavidad oscura) y por la almendra se ven los ojos.
// head-mesh.bin lo genera scripts/build_head_points.py.

interface Props {
  mood: FaceMood
  /** 0–1: volumen del micrófono mientras escucha (solo lo usa la carita de respaldo) */
  volume?: number
  /** 0–1: apertura de boca mientras habla (voz real) */
  getLevel?: () => number
  size?: number
}

interface HeadMesh {
  positions: Float32Array
  normals: Int8Array
  fade: Uint8Array
  eye: Int8Array
  role: Uint8Array
  index: Uint16Array
}

async function loadMesh(): Promise<HeadMesh> {
  const res = await fetch(headMeshUrl)
  if (!res.ok) throw new Error(`head-mesh: ${res.status}`)
  const buf = await res.arrayBuffer()
  const view = new DataView(buf)
  const nv = view.getUint32(0, true)
  const nt = view.getUint32(4, true)
  const raw = new Int16Array(buf, 8, nv * 3)
  const normals = new Int8Array(buf, 8 + nv * 6, nv * 3)
  const fade = new Uint8Array(buf, 8 + nv * 9, nv)
  const eye = new Int8Array(buf, 8 + nv * 10, nv)
  const role = new Uint8Array(buf, 8 + nv * 11, nv)
  const index = new Uint16Array(buf, 8 + nv * 12, nt * 3)
  const positions = new Float32Array(nv * 3)
  for (let i = 0; i < nv * 3; i++) positions[i] = raw[i] / 1000
  return { positions, normals, fade, eye, role, index }
}

/** Pesos de animación por vértice (mandíbula, labio de arriba, comisuras, párpado). */
// Los párpados no usan el peso de parpadeo de PointFace3D (aLid) sino `aEye`
// del modelo: cuánto baja cada vértice del párpado de arriba al parpadear.
function weightAttributes(geo: THREE.BufferGeometry, pos: ArrayLike<number>, role?: Uint8Array, eye?: Int8Array) {
  const n = pos.length / 3
  const w = [0, 1, 2].map(() => new Float32Array(n))
  for (let i = 0; i < n; i++) {
    weights(pos[i * 3], pos[i * 3 + 1], pos[i * 3 + 2], role && (role[i] & 0x0f) === 2 ? 2 : 0).slice(0, 3).forEach((v, k) => (w[k][i] = v))
  }
  ;['aJaw', 'aUpper', 'aCorner'].forEach((name, k) => geo.setAttribute(name, new THREE.BufferAttribute(w[k], 1)))
  geo.setAttribute('aEye', eye ? new THREE.BufferAttribute(eye, 1, true) : new THREE.BufferAttribute(new Float32Array(n), 1))
}

/** Aristas únicas de los triángulos, para dibujar la malla. */
function edgeIndex(index: Uint16Array): Uint32Array {
  const seen = new Set<number>()
  const edges: number[] = []
  for (let t = 0; t < index.length; t += 3) {
    for (let k = 0; k < 3; k++) {
      const a = index[t + k]
      const b = index[t + ((k + 1) % 3)]
      const key = Math.min(a, b) * 65536 + Math.max(a, b)
      if (seen.has(key)) continue
      seen.add(key)
      edges.push(a, b)
    }
  }
  return new Uint32Array(edges)
}

/** Puntito redondo para los vértices. */
function dotTexture(): THREE.Texture {
  const c = document.createElement('canvas')
  c.width = c.height = 32
  const ctx = c.getContext('2d')
  if (ctx) {
    ctx.fillStyle = '#fff'
    ctx.beginPath()
    ctx.arc(16, 16, 13, 0, Math.PI * 2)
    ctx.fill()
  }
  const tex = new THREE.CanvasTexture(c)
  tex.generateMipmaps = false
  tex.minFilter = THREE.LinearFilter
  return tex
}

// Tono de la piel según el ánimo: verde, con variaciones suaves (la luz hace
// el resto).
const MOOD_SKIN: Record<FaceMood, THREE.Color> = {
  idle: new THREE.Color('#5fd08a'),
  listening: new THREE.Color('#5fd6a4'),
  thinking: new THREE.Color('#6fc99a'),
  speaking: new THREE.Color('#62d892'),
  happy: new THREE.Color('#74e08a'),
  confused: new THREE.Color('#9ccf7a'),
}

const HEAD_SCALE = 0.33
const HEAD_Y = -0.31
// Ojos: centro de cada hueco (unidades del modelo) y radio del globo.
const EYE_CENTER = { x: 0.62, y: 1.7, z: 1.42 }
const EYE_RADIUS = 0.3

export default function MeshHead3D({ mood, volume = 0, getLevel, size = 280 }: Props) {
  const mount = useRef<HTMLDivElement>(null)
  const moodRef = useRef(mood)
  const levelRef = useRef(getLevel)
  const [failed, setFailed] = useState(false)
  moodRef.current = mood
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
    scene.add(new THREE.HemisphereLight(0xe6fff0, 0x10261c, 0.9))
    const key = new THREE.DirectionalLight(0xffffff, 2.2)
    key.position.set(-2, 2.5, 3)
    scene.add(key)
    const rim = new THREE.DirectionalLight(0xa8ffd0, 0.8)
    rim.position.set(3, 1, -2)
    scene.add(rim)

    // Mismo movimiento de boca y párpados para piel, líneas, puntos, ojos y
    // boca: por cuadro solo cambian 3 números.
    const uniforms = { uOpen: { value: 0 }, uSmile: { value: 0 }, uBlink: { value: 0 } }
    const deform = <M extends THREE.Material>(mat: M, fragment?: (glsl: string) => string): M => {
      mat.onBeforeCompile = (shader) => {
        Object.assign(shader.uniforms, uniforms)
        if (fragment) shader.fragmentShader = fragment(shader.fragmentShader)
        shader.vertexShader = shader.vertexShader
          .replace(
            '#include <common>',
            `#include <common>
attribute float aJaw;
attribute float aUpper;
attribute float aCorner;
attribute float aEye;
uniform float uOpen;
uniform float uSmile;
uniform float uBlink;`,
          )
          .replace(
            '#include <begin_vertex>',
            `#include <begin_vertex>
transformed.y += -uOpen * 0.42 * aJaw + uOpen * 0.06 * aUpper + uSmile * 0.05 * aCorner + uBlink * -0.16 * aEye;
transformed.x += (uSmile * 0.03 - uOpen * 0.05) * aCorner * sign(transformed.x);
transformed.z -= uOpen * 0.08 * aJaw;`,
          )
      }
      return mat
    }

    const head = new THREE.Group()
    head.scale.setScalar(HEAD_SCALE)
    head.position.y = HEAD_Y
    head.visible = false
    scene.add(head)

    const skinMat = deform(new THREE.MeshStandardMaterial({
      color: MOOD_SKIN.idle.clone(),
      roughness: 0.75,
      metalness: 0,
      vertexColors: true,
      transparent: true,
      // Doble cara: por la boca abierta se ve el revés de los labios.
      side: THREE.DoubleSide,
      // Empuja la piel un poco hacia atrás para que líneas y puntos no
      // parpadeen contra ella.
      polygonOffset: true,
      polygonOffsetFactor: 1,
      polygonOffsetUnits: 1,
    }), (glsl) => glsl.replace(
      '#include <color_fragment>',
      // El revés (adentro de los labios) en sombra, no iluminado como la cara.
      `#include <color_fragment>
if (!gl_FrontFacing) diffuseColor.rgb *= 0.3;`,
    ))
    const wireMat = deform(new THREE.LineBasicMaterial({ color: 0x0e4a2a, vertexColors: true, transparent: true, opacity: 0.35 }))
    const dot = dotTexture()
    const dotMat = deform(new THREE.PointsMaterial({
      color: 0x0b3a20,
      vertexColors: true,
      size: 0.016,
      sizeAttenuation: true,
      map: dot,
      alphaTest: 0.4,
      transparent: true,
    }))
    const eyeMat = deform(new THREE.MeshStandardMaterial({ color: 0xe9eef5, roughness: 0.35 }))
    const irisMat = new THREE.MeshStandardMaterial({ color: 0x2f7a4c, roughness: 0.4 })
    const pupilMat = new THREE.MeshStandardMaterial({ color: 0x151c2a, roughness: 0.3 })
    const mouthMat = deform(new THREE.MeshStandardMaterial({ color: 0x2a141c, roughness: 1, side: THREE.DoubleSide }))
    const disposables: { dispose: () => void }[] = [skinMat, wireMat, dot, dotMat, eyeMat, irisMat, pupilMat, mouthMat]

    let disposed = false
    loadMesh()
      .then((data) => {
        if (disposed) return
        const geo = new THREE.BufferGeometry()
        geo.setAttribute('position', new THREE.BufferAttribute(data.positions, 3))
        geo.setAttribute('normal', new THREE.BufferAttribute(data.normals, 3, true))
        // Color por vértice: el alfa desvanece el corte del cuello y lo de
        // adentro de la boca va en sombra.
        const rgba = new Uint8Array(data.fade.length * 4)
        for (let i = 0; i < data.fade.length; i++) {
          const tone = data.role[i] & 0x10 ? 40 : 255
          rgba.set([tone, tone, tone, data.fade[i]], i * 4)
        }
        geo.setAttribute('color', new THREE.BufferAttribute(rgba, 4, true))
        geo.setIndex(new THREE.BufferAttribute(data.index, 1))
        weightAttributes(geo, data.positions, data.role, data.eye)

        const wireGeo = new THREE.BufferGeometry()
        for (const name of ['position', 'color', 'aJaw', 'aUpper', 'aCorner', 'aEye']) wireGeo.setAttribute(name, geo.getAttribute(name))
        wireGeo.setIndex(new THREE.BufferAttribute(edgeIndex(data.index), 1))

        // Ojos: un globo en cada hueco, con iris y pupila al frente.
        const eyeGeo = new THREE.SphereGeometry(EYE_RADIUS, 24, 16)
        const irisGeo = new THREE.CircleGeometry(0.12, 24)
        const pupilGeo = new THREE.CircleGeometry(0.055, 20)
        const eyes = [-1, 1].map((side) => {
          const g = eyeGeo.clone()
          g.translate(side * EYE_CENTER.x, EYE_CENTER.y, EYE_CENTER.z)
          weightAttributes(g, g.getAttribute('position').array)
          return new THREE.Mesh(g, eyeMat)
        })
        const irises = [-1, 1].flatMap((side) => {
          const front = EYE_CENTER.z + EYE_RADIUS
          const iris = new THREE.Mesh(irisGeo, irisMat)
          iris.position.set(side * EYE_CENTER.x, EYE_CENTER.y - 0.02, front - 0.004)
          const pupil = new THREE.Mesh(pupilGeo, pupilMat)
          pupil.position.set(side * EYE_CENTER.x, EYE_CENTER.y - 0.02, front)
          return [iris, pupil]
        })

        // Interior de la boca: una cavidad oscura detrás de los labios; su
        // mitad de abajo baja con la mandíbula.
        const mouthGeo = new THREE.SphereGeometry(1, 24, 12, 0, Math.PI * 2, 0, Math.PI / 2)
        mouthGeo.rotateX(-Math.PI / 2)
        mouthGeo.scale(0.54, 0.32, 0.35)
        mouthGeo.translate(0, 0.42, 1.68)
        weightAttributes(mouthGeo, mouthGeo.getAttribute('position').array)

        const skin = new THREE.Mesh(geo, skinMat)
        head.add(new THREE.Mesh(mouthGeo, mouthMat), ...eyes, ...irises, skin, new THREE.LineSegments(wireGeo, wireMat), new THREE.Points(geo, dotMat))
        disposables.push(geo, wireGeo, eyeGeo, irisGeo, pupilGeo, mouthGeo, ...eyes.map((e) => e.geometry))
        head.visible = true
      })
      .catch(() => {
        if (!disposed) setFailed(true)
      })

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
      if (!visible || !head.visible) return
      const t = now / 1000
      const m = moodRef.current

      // Boca: solo se mueve con su propia voz; mientras te escucha, cerrada
      // (si siguiera tu micrófono parecería que habla encima de ti).
      const forced = (window as Window & { __iaradioFaceTest?: number }).__iaradioFaceTest
      const target =
        typeof forced === 'number' ? forced
          : m === 'speaking' ? (levelRef.current?.() ?? 0)
            : 0
      open += (target - open) * (target > open ? 0.55 : 0.22)
      smile += ((m === 'happy' ? 1 : m === 'idle' ? 0.2 : 0) - smile) * 0.08
      if (now > nextBlink) {
        blink = 1
        nextBlink = now + 2500 + Math.random() * 3000
      }
      blink *= 0.8
      uniforms.uOpen.value = open
      uniforms.uSmile.value = smile
      uniforms.uBlink.value = blink

      const sway = reduceMotion ? 0 : 1
      const yaw = Math.sin(t * 0.45) * 0.35 * sway
      const pitch =
        m === 'thinking' ? -0.2 : m === 'listening' ? 0.06 + Math.sin(t * 2.2) * 0.03 * sway : Math.sin(t * 0.33) * 0.035 * sway
      const roll = m === 'thinking' ? 0.08 : m === 'confused' ? -0.1 : 0
      head.rotation.y += (yaw - head.rotation.y) * 0.06
      head.rotation.x += (pitch - head.rotation.x) * 0.06
      head.rotation.z += (roll - head.rotation.z) * 0.06
      skinMat.color.lerp(MOOD_SKIN[m], 0.06)

      renderer.render(scene, camera)
    }
    raf = requestAnimationFrame(tick)

    return () => {
      disposed = true
      cancelAnimationFrame(raf)
      io.disconnect()
      for (const d of disposables) d.dispose()
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
