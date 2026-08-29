import { useEffect, useState } from 'react'
import { keyLabel } from '@/lib/keymap'
import { api } from '@/lib/api'
import type { ControlsInfo } from '@/lib/types'

/**
 * Referencia de solo lectura de teclado/mando. Equivalente a
 * gui/controls_widget.py::ControlsWidget: los controles se personalizan
 * editando config.yaml, no desde aquí.
 */
export function ControlsPanel() {
  const [info, setInfo] = useState<ControlsInfo | null>(null)

  useEffect(() => {
    api.getControlsInfo().then(setInfo)
  }, [])

  if (!info) return null

  return (
    <div className="h-full space-y-4 overflow-y-auto p-1">
      <KeyboardGroup keyboard={info.keyboard} />
      <JoystickGroup joystick={info.joystick} />
      <p className="rounded-md border bg-muted/50 p-3 text-sm text-muted-foreground">
        Los controles pueden personalizarse en config.yaml (secciones keyboard y
        joystick). Las teclas de preset se asignan por posición a las escenas de la
        cámara; el pad numérico funciona igual que la fila de dígitos.
      </p>
    </div>
  )
}

function KeyboardGroup({ keyboard }: { keyboard: ControlsInfo['keyboard'] }) {
  const movement = [keyboard.up, keyboard.down, keyboard.left, keyboard.right]
    .map(keyLabel)
    .join(' / ')
  const presetRows = keyboard.preset_keys
    .map((key, index) => `${keyLabel(key)} → preset ${index + 1}`)
    .join(' · ')
  const hotkeyEntries = Object.entries(keyboard.preset_hotkeys)

  return (
    <section className="space-y-2">
      <h3 className="text-sm font-medium">Teclado</h3>
      <Rows
        rows={[
          ['Movimiento', movement],
          ['Zoom', `${keyLabel(keyboard.zoom_in)} (zoom +) / ${keyLabel(keyboard.zoom_out)} (zoom −)`],
          ['Escenas (presets)', presetRows || '—'],
          ...(hotkeyEntries.length
            ? ([
                [
                  'Atajos fijos',
                  hotkeyEntries.map(([key, token]) => `${keyLabel(key)} → token ${token}`).join(' · '),
                ],
              ] as const)
            : []),
          ['Detener', keyLabel(keyboard.stop)],
          ['Salir', keyLabel(keyboard.quit)],
        ]}
      />
    </section>
  )
}

function JoystickGroup({ joystick }: { joystick: ControlsInfo['joystick'] }) {
  const tilt = joystick.invert_tilt ? 'invertido' : 'normal'
  const presets = joystick.preset_buttons
    .map((button, index) => `${index + 1} → botón ${button}`)
    .join(', ')

  return (
    <section className="space-y-2">
      <h3 className="text-sm font-medium">Mando (joystick)</h3>
      <Rows
        rows={[
          [
            'Movimiento',
            `Stick izquierdo (pan: eje ${joystick.pan_axis}, tilt: eje ${joystick.tilt_axis}, ${tilt})`,
          ],
          ['Zoom', `Eje ${joystick.zoom_in_axis} (zoom +) / eje ${joystick.zoom_out_axis} (zoom −)`],
          ['Velocidad', `Botón ${joystick.speed_up_button} (+1) / Botón ${joystick.speed_down_button} (−1)`],
          ['Home', `Botón ${joystick.home_button}`],
          ['Presets', presets || '—'],
        ]}
      />
    </section>
  )
}

function Rows({ rows }: { rows: readonly (readonly [string, string])[] }) {
  return (
    <dl className="space-y-1.5 rounded-md border p-3 text-sm">
      {rows.map(([label, value]) => (
        <div key={label} className="flex flex-col gap-0.5 sm:flex-row sm:justify-between sm:gap-4">
          <dt className="shrink-0 text-muted-foreground">{label}</dt>
          <dd className="text-right">{value}</dd>
        </div>
      ))}
    </dl>
  )
}
