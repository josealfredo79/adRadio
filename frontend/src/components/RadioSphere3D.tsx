import { useEffect, useRef } from 'react'
import * as THREE from 'three'

export default function RadioSphere3D() {
  const mountRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const mount = mountRef.current
    if (!mount) return

    // ── Scene setup ──────────────────────────────────────────
    const W = mount.clientWidth
    const H = mount.clientHeight

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    renderer.setSize(W, H)
    renderer.setClearColor(0x000000, 0)
    mount.appendChild(renderer.domElement)

    const scene = new THREE.Scene()
    const camera = new THREE.PerspectiveCamera(50, W / H, 0.1, 100)
    camera.position.set(0, 0, 5.5)

    // ── Core sphere (wireframe) ───────────────────────────────
    const coreGeo = new THREE.SphereGeometry(1, 32, 32)
    const coreMat = new THREE.MeshBasicMaterial({
      color: 0x6366f1,
      wireframe: true,
      transparent: true,
      opacity: 0.18,
    })
    const coreMesh = new THREE.Mesh(coreGeo, coreMat)
    scene.add(coreMesh)

    // Inner glowing sphere
    const innerGeo = new THREE.SphereGeometry(0.82, 24, 24)
    const innerMat = new THREE.MeshBasicMaterial({
      color: 0x818cf8,
      transparent: true,
      opacity: 0.06,
    })
    scene.add(new THREE.Mesh(innerGeo, innerMat))

    // ── Radio wave rings ─────────────────────────────────────
    const RINGS = 5
    const rings: { mesh: THREE.Mesh; born: number; delay: number }[] = []

    for (let i = 0; i < RINGS; i++) {
      const geo = new THREE.TorusGeometry(1, 0.008, 8, 80)
      const mat = new THREE.MeshBasicMaterial({
        color: 0xa855f7,
        transparent: true,
        opacity: 0,
      })
      const mesh = new THREE.Mesh(geo, mat)
      // tilt each ring slightly differently
      mesh.rotation.x = Math.PI / 2 + (i * 0.08)
      mesh.rotation.y = i * 0.3
      scene.add(mesh)
      rings.push({ mesh, born: -1, delay: i * 0.8 })
    }

    // ── Floating particles ───────────────────────────────────
    const PARTICLE_COUNT = 180
    const positions = new Float32Array(PARTICLE_COUNT * 3)
    const pSizes = new Float32Array(PARTICLE_COUNT)
    for (let i = 0; i < PARTICLE_COUNT; i++) {
      const r = 1.4 + Math.random() * 1.8
      const theta = Math.random() * Math.PI * 2
      const phi = Math.acos(2 * Math.random() - 1)
      positions[i * 3]     = r * Math.sin(phi) * Math.cos(theta)
      positions[i * 3 + 1] = r * Math.sin(phi) * Math.sin(theta)
      positions[i * 3 + 2] = r * Math.cos(phi)
      pSizes[i] = 1.5 + Math.random() * 2.5
    }
    const pGeo = new THREE.BufferGeometry()
    pGeo.setAttribute('position', new THREE.BufferAttribute(positions, 3))
    pGeo.setAttribute('size', new THREE.BufferAttribute(pSizes, 1))
    const pMat = new THREE.PointsMaterial({
      color: 0x6366f1,
      size: 0.04,
      transparent: true,
      opacity: 0.55,
      sizeAttenuation: true,
    })
    const particles = new THREE.Points(pGeo, pMat)
    scene.add(particles)

    // ── Mouse parallax ───────────────────────────────────────
    let mouseX = 0
    let mouseY = 0
    const onMouseMove = (e: MouseEvent) => {
      mouseX = (e.clientX / window.innerWidth - 0.5) * 2
      mouseY = (e.clientY / window.innerHeight - 0.5) * 2
    }
    window.addEventListener('mousemove', onMouseMove)

    // ── Resize ───────────────────────────────────────────────
    const onResize = () => {
      if (!mount) return
      const w = mount.clientWidth
      const h = mount.clientHeight
      renderer.setSize(w, h)
      camera.aspect = w / h
      camera.updateProjectionMatrix()
    }
    window.addEventListener('resize', onResize)

    // ── Animation loop ───────────────────────────────────────
    const RING_DURATION = 3.5 // seconds per ring expansion
    const timer = new THREE.Timer()
    let animId: number

    const animate = () => {
      animId = requestAnimationFrame(animate)
      timer.update()
      const t = timer.getElapsed()

      // Slowly rotate core
      coreMesh.rotation.y = t * 0.12
      coreMesh.rotation.x = t * 0.06

      // Rotate particles slowly opposite
      particles.rotation.y = -t * 0.04
      particles.rotation.x = t * 0.02

      // Camera parallax with mouse
      camera.position.x += (mouseX * 0.6 - camera.position.x) * 0.04
      camera.position.y += (-mouseY * 0.6 - camera.position.y) * 0.04
      camera.lookAt(scene.position)

      // Animate rings: expand from 1 → 3.5 radius, fade in then out
      rings.forEach((r, i) => {
        const loopT = (t - r.delay) % (RINGS * 0.8)
        const progress = Math.max(0, Math.min(1, loopT / RING_DURATION))

        const scale = 1 + progress * 2.5
        r.mesh.scale.setScalar(scale)

        // Fade: ramp up 0→0.6 first 30%, hold, ramp down 70%→100%
        let opacity = 0
        if (progress < 0.3) opacity = (progress / 0.3) * 0.5
        else if (progress < 0.7) opacity = 0.5
        else opacity = ((1 - progress) / 0.3) * 0.5
        ;(r.mesh.material as THREE.MeshBasicMaterial).opacity = opacity
      })

      renderer.render(scene, camera)
    }
    animate()

    return () => {
      cancelAnimationFrame(animId)
      timer.dispose()
      window.removeEventListener('mousemove', onMouseMove)
      window.removeEventListener('resize', onResize)
      renderer.dispose()
      if (mount.contains(renderer.domElement)) mount.removeChild(renderer.domElement)
    }
  }, [])

  return (
    <div
      ref={mountRef}
      className="absolute inset-0 w-full h-full"
      style={{ pointerEvents: 'none' }}
    />
  )
}
