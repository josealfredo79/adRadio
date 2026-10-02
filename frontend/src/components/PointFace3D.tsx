import { useEffect, useRef, useState } from 'react'
import * as THREE from 'three'
import BotFace, { type FaceMood } from '@/components/BotFace'
import headPointsUrl from '@/assets/models/head-points.bin?url'
import { weights } from '@/components/headWeights'

// Cabeza 3D completa hecha de puntos (estilo "face mesh") que mueve los labios
// con la voz de verdad. Puntos celestes en forma de triangulito sobre azul
// marino, iluminados desde arriba a la izquierda.
//
// La forma es un escaneo real de una cabeza humana: "Infinite, 3D Head Scan"
// de Lee Perry-Smith (Infinite Realities, www.ir-ltd.net), basado en un
// trabajo de www.triplegangers.com, licencia Creative Commons Attribution 3.0
// (https://creativecommons.org/licenses/by/3.0/). Se tomó del ejemplo de
// three.js (examples/models/gltf/LeePerrySmith) y se redujo a sus vértices
// (cabeza, orejas y cuello) más unos labios dibujados encima, porque el
// escaneo casi no tiene puntos en la boca. Lo genera
// scripts/build_head_points.py en `head-points.bin`:
//   uint32 n · int16[n·3] posición (milésimas) · int8[n·3] normal (·127) ·
//   uint8[n] brillo · uint8[n] rol (0 piel, 1 labio de arriba, 2 de abajo).
// Unidades del modelo: x a los lados (0 = centro de la cara), y hacia arriba
// (ojos ≈ 1.68, línea de la boca ≈ 0.42, mentón ≈ -0.6), z hacia la cámara.
//
// - Hablando: la mandíbula y el labio inferior siguen `getLevel()` (el volumen
//   real del audio que suena, ver useSpeaker.level).
// - Escuchando: boca cerrada y la cabeza asiente un poco.
// - Pensando: mira hacia arriba. Contento: sonrisa. Parpadea solo.
// La deformación y la luz corren en el shader: por cuadro solo cambian 3
// números. Sin WebGL (o si no carga el modelo) se muestra la carita (BotFace).

interface Props {
  mood: FaceMood
  /** 0–1: volumen del micrófono mientras escucha (solo lo usa la carita de respaldo) */
  volume?: number
  /** 0–1: apertura de boca mientras habla (voz real) */
  getLevel?: () => number
  size?: number
}

interface HeadGeometry {
  positions: Float32Array
  normals: Int8Array
  bright: Uint8Array
  weights: Float32Array[]
}

async function loadHead(): Promise<HeadGeometry> {
  const res = await fetch(headPointsUrl)
  if (!res.ok) throw new Error(`head-points: ${res.status}`)
  const buf = await res.arrayBuffer()
  const n = new DataView(buf).getUint32(0, true)
  const raw = new Int16Array(buf, 4, n * 3)
  const normals = new Int8Array(buf, 4 + n * 6, n * 3)
  const bright = new Uint8Array(buf, 4 + n * 9, n)
  const role = new Uint8Array(buf, 4 + n * 10, n)
  const positions = new Float32Array(n * 3)
  const w = [0, 1, 2, 3].map(() => new Float32Array(n))
  for (let i = 0; i < n; i++) {
    const x = raw[i * 3] / 1000
    const y = raw[i * 3 + 1] / 1000
    const z = raw[i * 3 + 2] / 1000
    positions[i * 3] = x
    positions[i * 3 + 1] = y
    positions[i * 3 + 2] = z
    weights(x, y, z, role[i]).forEach((v, k) => (w[k][i] = v))
  }
  return { positions, normals, bright, weights: w }
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

// Escala y posición de la cabeza en la escena (unidades del modelo → mundo).
const HEAD_SCALE = 0.33
const HEAD_Y = -0.31

export default function PointFace3D({ mood, volume = 0, getLevel, size = 280 }: Props) {
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

    const uniforms = { uOpen: { value: 0 }, uSmile: { value: 0 }, uBlink: { value: 0 } }
    const geo = new THREE.BufferGeometry()
    const sprite = triangleTexture()
    const mat = new THREE.PointsMaterial({
      size: 0.036,
      sizeAttenuation: true,
      map: sprite,
      alphaTest: 0.25,
      transparent: true,
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
attribute vec3 aNormal;
attribute float aBright;
attribute float aJaw;
attribute float aUpper;
attribute float aCorner;
attribute float aLid;
uniform float uOpen;
uniform float uSmile;
uniform float uBlink;
varying float vShade;`,
        )
        .replace(
          '#include <begin_vertex>',
          `#include <begin_vertex>
transformed.y += -uOpen * 0.42 * aJaw + uOpen * 0.06 * aUpper + uSmile * 0.05 * aCorner - uBlink * 0.1 * aLid;
transformed.x += (uSmile * 0.03 - uOpen * 0.05) * aCorner * sign(transformed.x);
transformed.z -= uOpen * 0.08 * aJaw;
// Luz fija respecto a la cámara: al girar la cabeza, la sombra se mueve con
// ella. Los puntos de la cara de atrás se apagan (no se transparenta la nuca).
vec3 vn = normalize(normalMatrix * aNormal);
float facing = clamp(vn.z * 2.5 + 0.2, 0.0, 1.0);
float diffuse = max(dot(vn, normalize(vec3(-0.45, 0.5, 0.85))), 0.0);
vShade = (0.35 + 0.95 * pow(diffuse, 1.3)) * facing * aBright;`,
        )
      shader.fragmentShader = shader.fragmentShader
        .replace('#include <common>', `#include <common>
varying float vShade;`)
        .replace('#include <color_fragment>', `#include <color_fragment>
if (vShade < 0.02) discard;
diffuseColor.rgb *= vShade;`)
    }

    const head = new THREE.Points(geo, mat)
    head.scale.setScalar(HEAD_SCALE)
    head.position.y = HEAD_Y
    head.visible = false
    scene.add(head)

    let disposed = false
    loadHead()
      .then((data) => {
        if (disposed) return
        geo.setAttribute('position', new THREE.BufferAttribute(data.positions, 3))
        geo.setAttribute('aNormal', new THREE.BufferAttribute(data.normals, 3, true))
        geo.setAttribute('aBright', new THREE.BufferAttribute(data.bright, 1, true))
        ;['aJaw', 'aUpper', 'aCorner', 'aLid'].forEach((name, k) => geo.setAttribute(name, new THREE.BufferAttribute(data.weights[k], 1)))
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
      // window.__iaradioFaceTest (0–1) solo lo pone una prueba automática: el
      // navegador de pruebas no tiene bocina y el volumen medido sería 0.
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
      blink *= 0.82
      uniforms.uOpen.value = open
      uniforms.uSmile.value = smile
      uniforms.uBlink.value = blink

      // Cabeza: casi de frente; gira un poco para que se note que es 3D,
      // asiente al escuchar y mira arriba al pensar.
      const sway = reduceMotion ? 0 : 1
      const yaw = Math.sin(t * 0.45) * 0.35 * sway
      const pitch =
        m === 'thinking' ? -0.2 : m === 'listening' ? 0.06 + Math.sin(t * 2.2) * 0.03 * sway : Math.sin(t * 0.33) * 0.035 * sway
      const roll = m === 'thinking' ? 0.08 : m === 'confused' ? -0.1 : 0
      head.rotation.y += (yaw - head.rotation.y) * 0.06
      head.rotation.x += (pitch - head.rotation.x) * 0.06
      head.rotation.z += (roll - head.rotation.z) * 0.06
      mat.color.lerp(MOOD_COLOR[m], 0.06)

      renderer.render(scene, camera)
    }
    raf = requestAnimationFrame(tick)

    return () => {
      disposed = true
      cancelAnimationFrame(raf)
      io.disconnect()
      geo.dispose()
      mat.dispose()
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
