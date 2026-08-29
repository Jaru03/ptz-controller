import { useEffect, useRef, useState } from 'react'
import { useBusEvent } from '@/hooks/useBusEvent'
import type { PtzStatus } from '@/lib/types'

const COLORS = {
  bg: '#1e1e2e',
  grid: '#2f2f42',
  axis: '#4a4a63',
  dot: '#00d9ff',
  dotGlow: 'rgba(0, 217, 255, 0.235)',
  text: '#cdd6f4',
  dim: '#7f849c',
  ok: '#a6e3a1',
  err: '#f38ba8',
  zoomBg: '#313244',
  zoomFill: '#f9e2af',
} as const

const EMPTY_STATUS: PtzStatus = {
  connected: false,
  pan: 0,
  tilt: 0,
  zoom: 0,
  speed: 0.5,
  device_name: '',
  ip: '',
  input_active: '',
  presets: [],
}

const MARGIN = 28

/**
 * Visualización "cámara virtual": posición (pan/tilt), zoom, estado de
 * conexión. Port directo a <canvas> de gui/camera_widget.py::CameraWidget
 * (QPainter) — mismo dibujo imperativo en cada actualización de estado,
 * sin necesidad de diffing de DOM a esta frecuencia.
 */
export function CameraStatusPanel() {
  const containerRef = useRef<HTMLDivElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const statusRef = useRef<PtzStatus>(EMPTY_STATUS)
  const [, forceRedraw] = useState(0)

  useBusEvent<PtzStatus>('ptz.status', (status) => {
    statusRef.current = status
    forceRedraw((n) => n + 1)
  })

  useEffect(() => {
    const container = containerRef.current
    const canvas = canvasRef.current
    if (!container || !canvas) return

    const draw = () => {
      const { width, height } = container.getBoundingClientRect()
      const dpr = window.devicePixelRatio || 1
      canvas.width = Math.max(1, Math.round(width * dpr))
      canvas.height = Math.max(1, Math.round(height * dpr))
      canvas.style.width = `${width}px`
      canvas.style.height = `${height}px`
      const ctx = canvas.getContext('2d')
      if (!ctx) return
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      drawScene(ctx, statusRef.current, width, height)
    }

    draw()
    const observer = new ResizeObserver(draw)
    observer.observe(container)
    return () => observer.disconnect()
  }, [])

  // Redibuja también cuando llega un nuevo status (sin cambiar de tamaño).
  useEffect(() => {
    const canvas = canvasRef.current
    const container = containerRef.current
    if (!canvas || !container) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    const { width, height } = container.getBoundingClientRect()
    drawScene(ctx, statusRef.current, width, height)
  })

  return (
    <div ref={containerRef} className="h-full min-h-64 w-full overflow-hidden rounded-md">
      <canvas ref={canvasRef} className="block" />
    </div>
  )
}

function drawScene(ctx: CanvasRenderingContext2D, status: PtzStatus, width: number, height: number) {
  ctx.fillStyle = COLORS.bg
  ctx.fillRect(0, 0, width, height)

  const field = playfieldRect(width, height)
  drawGrid(ctx, field)
  drawAxes(ctx, field)
  drawArrows(ctx, field)
  drawZoom(ctx, status, width, height)
  drawPositionDot(ctx, status, field)
  drawStatus(ctx, status, width)
  drawPositionText(ctx, status, width, height)
}

function playfieldRect(width: number, height: number) {
  return {
    left: MARGIN,
    top: MARGIN + 8,
    right: width - MARGIN,
    bottom: height - MARGIN - 42,
    width: Math.max(1, width - 2 * MARGIN),
    height: Math.max(1, height - 2 * MARGIN - 42),
  }
}

function drawGrid(ctx: CanvasRenderingContext2D, rect: ReturnType<typeof playfieldRect>) {
  ctx.strokeStyle = COLORS.grid
  ctx.lineWidth = 1
  for (let i = 1; i < 5; i++) {
    const x = rect.left + (rect.width * i) / 5
    const y = rect.top + (rect.height * i) / 5
    ctx.beginPath()
    ctx.moveTo(x, rect.top)
    ctx.lineTo(x, rect.bottom)
    ctx.moveTo(rect.left, y)
    ctx.lineTo(rect.right, y)
    ctx.stroke()
  }
}

function drawAxes(ctx: CanvasRenderingContext2D, rect: ReturnType<typeof playfieldRect>) {
  ctx.strokeStyle = COLORS.axis
  ctx.lineWidth = 1
  const centerX = rect.left + rect.width / 2
  const centerY = rect.top + rect.height / 2
  ctx.beginPath()
  ctx.moveTo(rect.left, centerY)
  ctx.lineTo(rect.right, centerY)
  ctx.moveTo(centerX, rect.top)
  ctx.lineTo(centerX, rect.bottom)
  ctx.stroke()
}

function drawArrows(ctx: CanvasRenderingContext2D, rect: ReturnType<typeof playfieldRect>) {
  ctx.fillStyle = COLORS.dim
  ctx.font = 'bold 11px system-ui, sans-serif'
  const centerX = rect.left + rect.width / 2
  const centerY = rect.top + rect.height / 2
  ctx.textAlign = 'center'
  ctx.textBaseline = 'top'
  ctx.fillText('↑', centerX, rect.top + 2)
  ctx.textBaseline = 'bottom'
  ctx.fillText('↓', centerX, rect.bottom - 2)
  ctx.textAlign = 'left'
  ctx.textBaseline = 'middle'
  ctx.fillText('←', rect.left + 2, centerY)
  ctx.textAlign = 'right'
  ctx.fillText('→', rect.right - 2, centerY)
}

function drawZoom(ctx: CanvasRenderingContext2D, status: PtzStatus, width: number, height: number) {
  const barX = MARGIN
  const barY = height - MARGIN - 8
  const barW = width - 2 * MARGIN
  const barH = 8

  roundedRect(ctx, barX, barY, barW, barH, 4)
  ctx.fillStyle = COLORS.zoomBg
  ctx.fill()

  const fillW = barW * Math.max(0, Math.min(1, status.zoom))
  if (fillW > 0) {
    roundedRect(ctx, barX, barY, fillW, barH, 4)
    ctx.fillStyle = COLORS.zoomFill
    ctx.fill()
  }

  ctx.fillStyle = COLORS.dim
  ctx.font = '9px system-ui, sans-serif'
  ctx.textAlign = 'left'
  ctx.textBaseline = 'bottom'
  ctx.fillText(
    `Zoom ${signed(status.zoom)}   Velocidad ${Math.round(status.speed * 100)}%`,
    barX,
    barY - 4,
  )
}

function drawPositionDot(ctx: CanvasRenderingContext2D, status: PtzStatus, rect: ReturnType<typeof playfieldRect>) {
  const centerX = rect.left + rect.width / 2
  const centerY = rect.top + rect.height / 2
  const radiusX = rect.width / 2 - 14
  const radiusY = rect.height / 2 - 14

  const dotX = centerX + status.pan * radiusX
  const dotY = centerY - status.tilt * radiusY

  ctx.fillStyle = COLORS.dotGlow
  ctx.beginPath()
  ctx.arc(dotX, dotY, 10, 0, Math.PI * 2)
  ctx.fill()

  ctx.fillStyle = COLORS.dot
  ctx.beginPath()
  ctx.arc(dotX, dotY, 5, 0, Math.PI * 2)
  ctx.fill()
}

function drawStatus(ctx: CanvasRenderingContext2D, status: PtzStatus, _width: number) {
  ctx.fillStyle = status.connected ? COLORS.ok : COLORS.err
  ctx.beginPath()
  ctx.arc(MARGIN + 9, 15, 5, 0, Math.PI * 2)
  ctx.fill()

  ctx.fillStyle = COLORS.text
  ctx.font = '9px system-ui, sans-serif'
  ctx.textAlign = 'left'
  ctx.textBaseline = 'middle'
  const state = status.connected ? 'Conectada' : 'Desconectada'
  ctx.fillText(`${status.device_name} — ${state}`, MARGIN + 20, 15)
}

function drawPositionText(ctx: CanvasRenderingContext2D, status: PtzStatus, width: number, height: number) {
  ctx.fillStyle = COLORS.dim
  ctx.font = '9px system-ui, sans-serif'
  ctx.textAlign = 'right'
  ctx.textBaseline = 'middle'
  ctx.fillText(
    `Pan ${signed(status.pan)}  Tilt ${signed(status.tilt)}`,
    width - MARGIN,
    height - MARGIN - 14,
  )
}

function roundedRect(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  const radius = Math.min(r, w / 2, h / 2)
  ctx.beginPath()
  ctx.moveTo(x + radius, y)
  ctx.arcTo(x + w, y, x + w, y + h, radius)
  ctx.arcTo(x + w, y + h, x, y + h, radius)
  ctx.arcTo(x, y + h, x, y, radius)
  ctx.arcTo(x, y, x + w, y, radius)
  ctx.closePath()
}

function signed(value: number): string {
  const sign = value >= 0 ? '+' : ''
  return `${sign}${value.toFixed(2)}`
}
