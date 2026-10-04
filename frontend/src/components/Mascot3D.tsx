import { useEffect, useRef, useState } from 'react'
import * as THREE from 'three'
import { RoundedBoxGeometry } from 'three/examples/jsm/geometries/RoundedBoxGeometry.js'
import BotFace, { type FaceMood } from '@/components/BotFace'

// Mascota de IaRadio: un radiecito verde con antena y perillas, y una pantalla
// por cara (ojos grandes que parpadean, cachetes y una boca de caricatura con
// lengua). Mismo contrato que MeshHead3D: la boca se abre con su propia voz
// real (getLevel) y el ánimo cambia ojos, antena y color. Todo se arma con
// figuras de three.js — sin modelos ni licencias que acreditar.

interface Props {
  mood: FaceMood
  /** 0–1: volumen del micrófono mientras escucha (la antena brilla con él) */
  volume?: number
  /** 0–1: apertura de boca mientras habla (voz real) */
  getLevel?: () => number
  size?: number
}

const MOOD_BODY: Record<FaceMood, THREE.Color> = {
  idle: new THREE.Color('#4fc77f'),
  listening: new THREE.Color('#47cf9c'),
  thinking: new THREE.Color('#5cbf8c'),
  speaking: new THREE.Color('#52d083'),
  happy: new THREE.Color('#5fd879'),
  confused: new THREE.Color('#8fc66e'),
}

const GLOW = 0x8dffc8 // ojos, boca y antena
const SCREEN_Z = 0.556 // frente del cuerpo (profundidad 1.1 / 2) + un pelito

// Boca: columnas de vértices a lo ancho; arriba una curva de sonrisa y abajo
// baja según la apertura (perfil redondo, más honda al centro).
const MOUTH_COLS = 28
const MOUTH = { y: -0.13, w: 0.2, depth: 0.24, line: 0.032 }

function stripGeometry(): THREE.BufferGeometry {
  const geo = new THREE.BufferGeometry()
  geo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(MOUTH_COLS * 2 * 3), 3))
  const idx: number[] = []
  for (let i = 0; i < MOUTH_COLS - 1; i++) {
    const a = i * 2
    idx.push(a, a + 1, a + 2, a + 1, a + 3, a + 2)
  }
  geo.setIndex(idx)
  return geo
}

/** Rellena una tira entre top(u) y bottom(u), u de -1 a 1, con ancho `w`. */
function writeStrip(geo: THREE.BufferGeometry, w: number, z: number, top: (u: number) => number, bottom: (u: number) => number) {
  const attr = geo.getAttribute('position') as THREE.BufferAttribute
  const a = attr.array as Float32Array
  for (let i = 0; i < MOUTH_COLS; i++) {
    const u = (i / (MOUTH_COLS - 1)) * 2 - 1
    const t = top(u)
    const b = Math.min(t, bottom(u))
    a.set([u * w, t, z, u * w, b, z], i * 6)
  }
  attr.needsUpdate = true
  geo.computeBoundingSphere()
}

function roundedRect(w: number, h: number, r: number): THREE.Shape {
  const s = new THREE.Shape()
  const x = -w / 2
  const y = -h / 2
  s.moveTo(x + r, y)
  s.lineTo(x + w - r, y)
  s.quadraticCurveTo(x + w, y, x + w, y + r)
  s.lineTo(x + w, y + h - r)
  s.quadraticCurveTo(x + w, y + h, x + w - r, y + h)
  s.lineTo(x + r, y + h)
  s.quadraticCurveTo(x, y + h, x, y + h - r)
  s.lineTo(x, y + r)
  s.quadraticCurveTo(x, y, x + r, y)
  return s
}

/** Mancha suave y redonda (sombra en el piso y halo de la antena). */
function softTexture(): THREE.Texture {
  const c = document.createElement('canvas')
  c.width = c.height = 64
  const ctx = c.getContext('2d')
  if (ctx) {
    const g = ctx.createRadialGradient(32, 32, 0, 32, 32, 32)
    g.addColorStop(0, 'rgba(255,255,255,1)')
    g.addColorStop(1, 'rgba(255,255,255,0)')
    ctx.fillStyle = g
    ctx.fillRect(0, 0, 64, 64)
  }
  return new THREE.CanvasTexture(c)
}

export default function Mascot3D({ mood, volume = 0, getLevel, size = 280 }: Props) {
  const mount = useRef<HTMLDivElement>(null)
  const moodRef = useRef(mood)
  const levelRef = useRef(getLevel)
  const volumeRef = useRef(volume)
  const [failed, setFailed] = useState(false)
  moodRef.current = mood
  levelRef.current = getLevel
  volumeRef.current = volume

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
    camera.position.set(0, 0.12, 5.4)
    scene.add(new THREE.HemisphereLight(0xf0fff6, 0x1a3326, 1.1))
    const key = new THREE.DirectionalLight(0xffffff, 2.4)
    key.position.set(-2, 3, 3.5)
    scene.add(key)
    const rim = new THREE.DirectionalLight(0xb8ffdc, 1)
    rim.position.set(3, 1.5, -2)
    scene.add(rim)

    const disposables: { dispose: () => void }[] = []
    const keep = <T extends { dispose: () => void }>(d: T): T => {
      disposables.push(d)
      return d
    }

    // Todo lo que flota y gira junto.
    const bot = new THREE.Group()
    scene.add(bot)

    // Cuerpo: caja muy redondeada con un poco de barniz.
    const bodyMat = keep(new THREE.MeshPhysicalMaterial({ color: MOOD_BODY.idle.clone(), roughness: 0.42, clearcoat: 0.7, clearcoatRoughness: 0.3 }))
    bot.add(new THREE.Mesh(keep(new RoundedBoxGeometry(1.6, 1.4, 1.1, 6, 0.32)), bodyMat))

    // Pantalla-cara con su marco.
    const bezel = new THREE.Mesh(keep(new THREE.ShapeGeometry(roundedRect(1.36, 1.0, 0.24), 8)), keep(new THREE.MeshStandardMaterial({ color: 0x1f6b45, roughness: 0.6 })))
    bezel.position.set(0, 0.1, SCREEN_Z - 0.003)
    const screen = new THREE.Mesh(keep(new THREE.ShapeGeometry(roundedRect(1.26, 0.9, 0.2), 8)), keep(new THREE.MeshStandardMaterial({ color: 0x0b1b2c, roughness: 0.25, metalness: 0.1 })))
    screen.position.set(0, 0.1, SCREEN_Z)
    bot.add(bezel, screen)

    // Cara (todo plano sobre la pantalla); se asoma hacia donde está el cursor.
    const face = new THREE.Group()
    face.position.set(0, 0.1, SCREEN_Z + 0.002)
    bot.add(face)
    const glowMat = keep(new THREE.MeshBasicMaterial({ color: GLOW }))
    const circle = keep(new THREE.CircleGeometry(1, 40))
    const arch = keep(new THREE.TorusGeometry(0.1, 0.03, 8, 28, Math.PI))
    const shineMat = keep(new THREE.MeshBasicMaterial({ color: 0xffffff }))
    const eyes = [-1, 1].map((side) => {
      const g = new THREE.Group()
      g.position.set(side * 0.29, 0.13, 0)
      const open = new THREE.Mesh(circle, glowMat)
      open.scale.set(0.105, 0.15, 1)
      const shine = new THREE.Mesh(circle, shineMat)
      shine.scale.setScalar(0.032)
      shine.position.set(0.035, 0.06, 0.001)
      const happy = new THREE.Mesh(arch, glowMat)
      happy.visible = false
      g.add(open, shine, happy)
      face.add(g)
      return { g, open, shine, happy }
    })
    const cheekMat = keep(new THREE.MeshBasicMaterial({ color: 0xff7aa8, transparent: true, opacity: 0.45 }))
    for (const side of [-1, 1]) {
      const cheek = new THREE.Mesh(circle, cheekMat)
      cheek.scale.set(0.085, 0.055, 1)
      cheek.position.set(side * 0.46, -0.07, 0)
      face.add(cheek)
    }

    // Boca: contorno brillante, adentro oscuro y la lengua abajo.
    const mouthOuter = keep(stripGeometry())
    const mouthInner = keep(stripGeometry())
    const tongue = keep(stripGeometry())
    face.add(
      new THREE.Mesh(mouthOuter, glowMat),
      new THREE.Mesh(mouthInner, keep(new THREE.MeshBasicMaterial({ color: 0x14061a }))),
      new THREE.Mesh(tongue, keep(new THREE.MeshBasicMaterial({ color: 0xff6f91 }))),
    )

    // Perillas de radio a los lados.
    const knobMat = keep(new THREE.MeshStandardMaterial({ color: 0x2e8f5c, roughness: 0.35, metalness: 0.2 }))
    const knobGeo = keep(new THREE.CylinderGeometry(0.17, 0.17, 0.1, 32))
    const notchGeo = keep(new THREE.BoxGeometry(0.02, 0.04, 0.22))
    const knobs = [-1, 1].map((side) => {
      const k = new THREE.Group()
      k.position.set(side * 0.82, 0.08, 0)
      k.rotation.z = Math.PI / 2
      const notch = new THREE.Mesh(notchGeo, keep(new THREE.MeshStandardMaterial({ color: 0xe8fff2 })))
      notch.position.set(0, side * -0.05, 0)
      k.add(new THREE.Mesh(knobGeo, knobMat), notch)
      bot.add(k)
      return k
    })

    // Antena: se mece como resorte y la punta brilla.
    const antenna = new THREE.Group()
    antenna.position.set(0.38, 0.66, 0)
    antenna.rotation.z = -0.25
    const rod = new THREE.Mesh(keep(new THREE.CylinderGeometry(0.025, 0.03, 0.5, 12)), knobMat)
    rod.position.y = 0.25
    const tipMat = keep(new THREE.MeshStandardMaterial({ color: GLOW, emissive: GLOW, emissiveIntensity: 0.6 }))
    const tip = new THREE.Mesh(keep(new THREE.SphereGeometry(0.075, 20, 14)), tipMat)
    tip.position.y = 0.53
    const soft = keep(softTexture())
    const halo = new THREE.Sprite(keep(new THREE.SpriteMaterial({ map: soft, color: GLOW, transparent: true, opacity: 0.35, depthWrite: false })))
    halo.position.y = 0.53
    halo.scale.setScalar(0.4)
    antenna.add(rod, tip, halo)
    bot.add(antenna)

    // Sombra en el piso (no se mueve con el bot; solo se encoge al subir).
    const shadow = new THREE.Mesh(keep(new THREE.PlaneGeometry(1.6, 0.5)), keep(new THREE.MeshBasicMaterial({ map: soft, color: 0x000000, transparent: true, opacity: 0.35, depthWrite: false })))
    shadow.rotation.x = -Math.PI / 2
    shadow.position.y = -1.0
    scene.add(shadow)

    const reduceMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
    let visible = true
    const io = new IntersectionObserver(([entry]) => { visible = entry.isIntersecting })
    io.observe(el)

    // Hacia dónde mira: el cursor, relativo al centro del bot.
    const look = { x: 0, y: 0 }
    const onPointer = (e: PointerEvent) => {
      const r = el.getBoundingClientRect()
      look.x = Math.max(-1, Math.min(1, (e.clientX - (r.left + r.width / 2)) / (window.innerWidth / 2)))
      look.y = Math.max(-1, Math.min(1, (e.clientY - (r.top + r.height / 2)) / (window.innerHeight / 2)))
    }
    window.addEventListener('pointermove', onPointer, { passive: true })

    let voice = 0
    let open = 0
    let smile = 0
    let blink = 0
    let nextBlink = performance.now() + 2200
    let antennaVel = 0
    let antennaAngle = 0
    let glow = 0
    const eyeAt = { x: 0, y: 0 }
    let raf = 0

    const tick = (now: number) => {
      raf = requestAnimationFrame(tick)
      if (!visible) return
      const t = now / 1000
      const m = moodRef.current
      const sway = reduceMotion ? 0 : 1

      // Boca: igual que MeshHead3D — solo con su propia voz, suavizada.
      const forced = (window as Window & { __iaradioFaceTest?: number }).__iaradioFaceTest
      const target = typeof forced === 'number' ? forced : m === 'speaking' ? (levelRef.current?.() ?? 0) : 0
      voice += (target - voice) * 0.3
      const goal = Math.min(1, Math.pow(voice, 1.1) * 1.1)
      open += (goal - open) * (goal > open ? 0.3 : 0.18)
      const smileGoal = m === 'happy' ? 1 : m === 'confused' ? -0.4 : m === 'thinking' ? 0.1 : 0.6
      smile += (smileGoal - smile) * 0.1

      const w = MOUTH.w * (1 - open * 0.15) * (m === 'thinking' ? 0.6 : 1)
      const curve = (u: number) => MOUTH.y + smile * 0.06 * u * u
      const lip = (u: number) => MOUTH.line * (0.55 + 0.45 * Math.sqrt(1 - u * u))
      const drop = (u: number) => open * MOUTH.depth * Math.sqrt(1 - u * u)
      writeStrip(mouthOuter, w, 0, (u) => curve(u) + lip(u) / 2, (u) => curve(u) - lip(u) / 2 - drop(u))
      const iw = Math.max(0.001, w - MOUTH.line * 0.8)
      const innerTop = (u: number) => curve((u * iw) / w) - MOUTH.line * 0.35
      const innerBottom = (u: number) => curve((u * iw) / w) + MOUTH.line * 0.35 - drop((u * iw) / w)
      writeStrip(mouthInner, iw, 0.001, innerTop, innerBottom)
      const tw = iw * 0.62
      const tk = tw / iw
      writeStrip(tongue, tw, 0.002, (u) => innerBottom(u * tk) + (innerTop(u * tk) - innerBottom(u * tk)) * 0.42, (u) => innerBottom(u * tk))

      // Ojos: parpadean, se vuelven arquitos ^^ cuando está feliz, miran
      // arriba al pensar y uno se achica cuando no entendió.
      if (now > nextBlink) {
        blink = 1
        nextBlink = now + 2200 + Math.random() * 3200
      }
      blink *= 0.78
      const lookGoal = m === 'thinking'
        ? { x: 0.06 + Math.sin(t * 1.3) * 0.02, y: 0.06 }
        : { x: look.x * 0.07 * sway, y: -look.y * 0.04 * sway }
      eyeAt.x += (lookGoal.x - eyeAt.x) * 0.1
      eyeAt.y += (lookGoal.y - eyeAt.y) * 0.1
      const big = m === 'listening' ? 1.12 : 1
      eyes.forEach((e, i) => {
        const happy = m === 'happy'
        e.open.visible = !happy
        e.shine.visible = !happy && blink < 0.5
        e.happy.visible = happy
        const squint = m === 'confused' && i === 0 ? 0.55 : 1
        e.open.scale.set(0.105 * big, 0.15 * big * squint * Math.max(0.08, 1 - blink), 1)
        e.g.position.x = (i === 0 ? -0.29 : 0.29) + eyeAt.x
        e.g.position.y = 0.13 + eyeAt.y
      })

      // Flota, se mece y voltea un poquito hacia ti.
      bot.position.y = Math.sin(t * 1.6) * 0.05 * sway + (m === 'happy' ? Math.abs(Math.sin(t * 6)) * 0.05 * sway : 0)
      const yaw = Math.sin(t * 0.5) * 0.22 * sway + look.x * 0.18 * sway
      const pitch = m === 'thinking' ? -0.12 : m === 'listening' ? 0.08 : look.y * 0.08 * sway
      const roll = m === 'confused' ? -0.12 : m === 'thinking' ? 0.07 : Math.sin(t * 0.7) * 0.03 * sway
      bot.rotation.y += (yaw - bot.rotation.y) * 0.06
      bot.rotation.x += (pitch - bot.rotation.x) * 0.06
      bot.rotation.z += (roll - bot.rotation.z) * 0.06
      shadow.scale.setScalar(1 - bot.position.y * 0.8)

      // Antena: resorte que se sacude con la voz y con el brinco.
      const kick = (m === 'speaking' ? voice * 0.8 : 0) + Math.cos(t * 1.6) * 0.015 * sway
      antennaVel += (-antennaAngle * 0.12 - antennaVel * 0.12) + kick * 0.04 * Math.sin(t * 9)
      antennaAngle += antennaVel
      antenna.rotation.z = -0.25 + antennaAngle
      const glowGoal = m === 'listening' ? 0.5 + volumeRef.current * 1.5 : m === 'speaking' ? 0.4 + voice : m === 'thinking' ? 0.5 + 0.5 * Math.sin(t * 5) : 0.35
      glow += (glowGoal - glow) * 0.15
      tipMat.emissiveIntensity = 0.4 + glow
      halo.material.opacity = Math.min(0.85, 0.15 + glow * 0.4)
      halo.scale.setScalar(0.35 + glow * 0.25)

      // Las perillas giran despacito, como sintonizando.
      knobs.forEach((k, i) => { k.rotation.y = t * (m === 'thinking' ? 1.5 : 0.25) * (i ? 1 : -1) })
      bodyMat.color.lerp(MOOD_BODY[m], 0.06)

      renderer.render(scene, camera)
    }
    raf = requestAnimationFrame(tick)

    return () => {
      cancelAnimationFrame(raf)
      io.disconnect()
      window.removeEventListener('pointermove', onPointer)
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
