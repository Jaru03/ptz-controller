import { useEffect, useState } from 'react'
import { Gamepad2, Keyboard } from 'lucide-react'
import { GamepadDiagram } from '@/components/controls/GamepadDiagram'
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
    <div className="h-full space-y-8 overflow-y-auto p-2">
      <KeyboardSection keyboard={info.keyboard} />
      <div className="border-t" />
      <JoystickSection joystick={info.joystick} />
      <p className="rounded-md border bg-muted/50 p-4 text-sm text-muted-foreground">
        Los controles pueden personalizarse en config.yaml (secciones keyboard y
        joystick). Las teclas de escena se asignan por posición a los presets de la
        cámara; el pad numérico funciona igual que la fila de dígitos.
      </p>
    </div>
  )
}

function KeyboardSection({ keyboard }: { keyboard: ControlsInfo['keyboard'] }) {
  const hotkeyEntries = Object.entries(keyboard.preset_hotkeys)

  return (
    <section className="space-y-5">
      <SectionTitle icon={Keyboard} text="Teclado" />

      <div className="flex flex-wrap items-start gap-10">
        <Field label="Movimiento">
          <div className="flex flex-col items-center gap-1.5">
            <KeyCap>{keyLabel(keyboard.up)}</KeyCap>
            <div className="flex gap-1.5">
              <KeyCap>{keyLabel(keyboard.left)}</KeyCap>
              <KeyCap>{keyLabel(keyboard.down)}</KeyCap>
              <KeyCap>{keyLabel(keyboard.right)}</KeyCap>
            </div>
          </div>
        </Field>

        <Field label="Zoom">
          <div className="flex items-center gap-2">
            <LabeledKey keyName={keyboard.zoom_in} caption="zoom +" />
            <LabeledKey keyName={keyboard.zoom_out} caption="zoom −" />
          </div>
        </Field>

        <Field label="Detener / Salir">
          <div className="flex items-center gap-2">
            <LabeledKey keyName={keyboard.stop} caption="detener" />
            <LabeledKey keyName={keyboard.quit} caption="salir" />
          </div>
        </Field>
      </div>

      <Field label="Escenas (presets)">
        <div className="flex flex-wrap gap-2">
          {keyboard.preset_keys.map((key, index) => (
            <Chip key={key}>
              <KeyCap small>{keyLabel(key)}</KeyCap>
              <span className="text-muted-foreground">preset {index + 1}</span>
            </Chip>
          ))}
        </div>
      </Field>

      {hotkeyEntries.length > 0 && (
        <Field label="Atajos fijos">
          <div className="flex flex-wrap gap-2">
            {hotkeyEntries.map(([key, token]) => (
              <Chip key={key}>
                <KeyCap small>{keyLabel(key)}</KeyCap>
                <span className="text-muted-foreground">token {token}</span>
              </Chip>
            ))}
          </div>
        </Field>
      )}
    </section>
  )
}

function JoystickSection({ joystick }: { joystick: ControlsInfo['joystick'] }) {
  return (
    <section className="space-y-5">
      <SectionTitle icon={Gamepad2} text="Mando (joystick)" />
      <div className="mx-auto max-w-xl">
        <GamepadDiagram joystick={joystick} />
      </div>
    </section>
  )
}

function SectionTitle({ icon: Icon, text }: { icon: typeof Keyboard; text: string }) {
  return (
    <h3 className="flex items-center gap-2 text-sm font-medium">
      <Icon className="size-4 text-muted-foreground" />
      {text}
    </h3>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-2">
      <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">{label}</p>
      {children}
    </div>
  )
}

function LabeledKey({ keyName, caption }: { keyName: string; caption: string }) {
  return (
    <div className="flex flex-col items-center gap-1.5">
      <KeyCap>{keyLabel(keyName)}</KeyCap>
      <span className="text-xs text-muted-foreground">{caption}</span>
    </div>
  )
}

function KeyCap({ children, small }: { children: React.ReactNode; small?: boolean }) {
  return (
    <span
      className={`inline-flex items-center justify-center rounded-md border bg-background font-mono font-medium shadow-[0_2px_0_0] shadow-border ${
        small ? 'h-6 min-w-6 px-1.5 text-xs' : 'h-9 min-w-9 px-2 text-sm'
      }`}
    >
      {children}
    </span>
  )
}

function Chip({ children }: { children: React.ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border bg-background py-1 pr-3 pl-1 text-sm">
      {children}
    </span>
  )
}
