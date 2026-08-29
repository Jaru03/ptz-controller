import type { JoystickConfig } from '@/lib/types'

/**
 * Diagrama del mando: silueta esquemática + líneas guía hacia una
 * etiqueta que explica qué hace cada control, con los valores reales de
 * config.yaml (ejes/botones). Sustituye a la lista de filas
 * "Movimiento/Zoom/Velocidad/Home/Presets" — más fácil de leer de un
 * vistazo que un texto denso.
 */
export function GamepadDiagram({ joystick }: { joystick: JoystickConfig }) {
  const tilt = joystick.invert_tilt ? 'invertido' : 'normal'
  const presetLines = joystick.preset_buttons
    .slice(0, 4)
    .map((button, index) => `Preset ${index + 1} · botón ${button}`)
  const extraPresets = joystick.preset_buttons.slice(4)

  const buttonPositions = [
    { x: 440, y: 140 },
    { x: 396, y: 184 },
    { x: 484, y: 184 },
    { x: 440, y: 228 },
  ]

  return (
    <div className="space-y-2">
      <svg viewBox="-90 -20 810 360" className="w-full" role="img" aria-label="Diagrama del mando">
        {/* Cuerpo: una cápsula central + dos círculos en las esquinas
            inferiores hacen de "grips", todo del mismo color para que
            se vea como una sola silueta. */}
        <g className="fill-muted stroke-border" strokeWidth="1.5">
          <circle cx="200" cy="200" r="58" />
          <circle cx="440" cy="200" r="58" />
          <rect x="160" y="100" width="320" height="130" rx="65" />
        </g>

        {/* Gatillos y hombreras, arriba del cuerpo */}
        <g className="fill-background stroke-border" strokeWidth="1.5">
          <rect x="150" y="60" width="70" height="26" rx="8" />
          <rect x="420" y="60" width="70" height="26" rx="8" />
          <rect x="155" y="90" width="60" height="20" rx="6" />
          <rect x="425" y="90" width="60" height="20" rx="6" />
        </g>
        <Anchor x={185} y={73} />
        <Anchor x={455} y={73} />

        {/* Stick izquierdo (pan/tilt) */}
        <circle cx="230" cy="185" r="32" className="fill-background stroke-border" strokeWidth="1.5" />
        <circle cx="230" cy="185" r="18" className="fill-primary/70 stroke-primary" strokeWidth="1.5" />
        <Anchor x={230} y={185} />

        {/* Home, centro del cuerpo */}
        <circle cx="320" cy="150" r="14" className="fill-background stroke-border" strokeWidth="1.5" />
        <Anchor x={320} y={150} />

        {/* Botones de presets, en rombo a la derecha */}
        {presetLines.map((_, i) => {
          const pos = buttonPositions[i]
          return (
            <g key={i}>
              <circle cx={pos.x} cy={pos.y} r="15" className="fill-background stroke-border" strokeWidth="1.5" />
              <text
                x={pos.x}
                y={pos.y}
                textAnchor="middle"
                dominantBaseline="central"
                className="fill-foreground text-[13px] font-medium"
              >
                {i + 1}
              </text>
            </g>
          )
        })}
        <Anchor x={buttonPositions[2].x} y={buttonPositions[2].y} />

        {/* Líneas guía + etiquetas */}
        <Callout from={{ x: 230, y: 185 }} to={{ x: -60, y: 185 }} align="start" baseline="central">
          {['Pan / Tilt', `eje ${joystick.pan_axis} / eje ${joystick.tilt_axis} (${tilt})`]}
        </Callout>

        <Callout from={{ x: 185, y: 73 }} to={{ x: -60, y: 10 }} align="start" baseline="central">
          {['Zoom', `− eje ${joystick.zoom_out_axis} · + eje ${joystick.zoom_in_axis}`]}
        </Callout>

        <Callout from={{ x: 455, y: 73 }} to={{ x: 600, y: 10 }} align="start" baseline="central">
          {['Velocidad', `− botón ${joystick.speed_down_button} · + botón ${joystick.speed_up_button}`]}
        </Callout>

        <Callout from={{ x: 320, y: 150 }} to={{ x: 320, y: 300 }} align="middle" baseline="hanging">
          {[`Home · botón ${joystick.home_button}`]}
        </Callout>

        <Callout from={buttonPositions[2]} to={{ x: 600, y: 155 }} align="start" baseline="central">
          {presetLines}
        </Callout>
      </svg>
      {extraPresets.length > 0 && (
        <p className="text-xs text-muted-foreground">
          Presets adicionales:{' '}
          {extraPresets.map((button, i) => `${i + 5} → botón ${button}`).join(' · ')}
        </p>
      )}
    </div>
  )
}

function Anchor({ x, y }: { x: number; y: number }) {
  return <circle cx={x} cy={y} r="2.5" className="fill-muted-foreground" />
}

function Callout({
  from,
  to,
  align,
  baseline,
  children: lines,
}: {
  from: { x: number; y: number }
  to: { x: number; y: number }
  align: 'start' | 'middle' | 'end'
  baseline: 'central' | 'hanging'
  children: string[]
}) {
  return (
    <g>
      <path
        d={`M ${from.x} ${from.y} L ${to.x} ${to.y}`}
        className="stroke-muted-foreground/50"
        strokeWidth="1"
        fill="none"
        strokeDasharray="3 3"
      />
      <text x={to.x} y={to.y} textAnchor={align} dominantBaseline={baseline} className="fill-foreground text-[12px]">
        {lines.map((line, i) => (
          // El atributo x de un tspan es una posición ABSOLUTA en SVG, no
          // relativa al <text> padre: hay que repetirlo en cada línea o
          // todas menos la primera caen al borde izquierdo del lienzo.
          <tspan key={i} x={to.x} dy={i === 0 ? 0 : 15} className={i === 0 ? 'font-medium' : undefined}>
            {line}
          </tspan>
        ))}
      </text>
    </g>
  )
}
