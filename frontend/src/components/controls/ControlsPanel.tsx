import { useCallback, useEffect, useState } from 'react'
import { Gamepad2, Keyboard } from 'lucide-react'
import { GamepadDiagram } from '@/components/controls/GamepadDiagram'
import { Chip, KeyCap } from '@/components/ui/keycap'
import { keyLabel, mapKeyEvent } from '@/lib/keymap'
import { api } from '@/lib/api'
import type { ControlsInfo, KeyboardConfig } from '@/lib/types'

type ActionField = 'up' | 'down' | 'left' | 'right' | 'zoom_in' | 'zoom_out' | 'stop' | 'quit'

type Binding = { kind: 'action'; field: ActionField } | { kind: 'preset'; index: number }

function bindingKey(binding: Binding): string {
  return binding.kind === 'action' ? `action:${binding.field}` : `preset:${binding.index}`
}

/**
 * Referencia de teclado/mando. El teclado es totalmente reasignable: clic
 * en una tecla, pulsar la nueva y se guarda vía
 * ``Api.save_keyboard_settings`` (gui_web/api.py), que muta la misma
 * instancia de ``KeyboardConfig`` que usa el ``KeyboardController`` en
 * marcha — el cambio aplica en caliente, sin reiniciar nada. El mando
 * sigue siendo de solo lectura (se personaliza en config.yaml).
 */
export function ControlsPanel() {
  const [info, setInfo] = useState<ControlsInfo | null>(null)
  const [listening, setListening] = useState<Binding | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api.getControlsInfo().then(setInfo)
  }, [])

  const applyBinding = useCallback(
    async (binding: Binding, key: string) => {
      const patch: Partial<KeyboardConfig> =
        binding.kind === 'action'
          ? { [binding.field]: key }
          : {
              preset_keys: (info?.keyboard.preset_keys ?? []).map((existing, index) =>
                index === binding.index ? key : existing,
              ),
            }
      const result = await api.saveKeyboardSettings(patch)
      if (!result.ok) {
        setError(result.error ?? 'No se pudo guardar la tecla')
        return
      }
      setError('')
      setInfo((prev) => (prev && result.settings ? { ...prev, keyboard: result.settings.keyboard } : prev))
    },
    [info],
  )

  // Captura el siguiente keydown mientras haya una tecla "escuchando".
  // ESC cancela la captura en vez de asignarse (evita que quede
  // atrapada la única forma habitual de cancelar).
  useEffect(() => {
    if (!listening) return
    const binding = listening
    const onKeyDown = (e: KeyboardEvent) => {
      e.preventDefault()
      e.stopPropagation()
      setListening(null)
      if (e.key === 'Escape') return
      const key = mapKeyEvent(e)
      if (key) void applyBinding(binding, key)
    }
    document.addEventListener('keydown', onKeyDown, { capture: true })
    return () => document.removeEventListener('keydown', onKeyDown, { capture: true })
  }, [listening, applyBinding])

  if (!info) return null

  return (
    <div className="h-full space-y-8 overflow-y-auto p-2">
      <KeyboardSection
        keyboard={info.keyboard}
        listening={listening}
        onStartListening={setListening}
      />
      {error && (
        <p className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </p>
      )}
      <div className="border-t" />
      <JoystickSection joystick={info.joystick} />
      <p className="rounded-md border bg-muted/50 p-4 text-sm text-muted-foreground">
        Clic en una tecla y pulse la nueva para reasignarla. Las escenas se asignan por
        posición a los presets de la cámara; el pad numérico funciona igual que la fila de
        dígitos. El mando se personaliza en config.yaml (sección joystick).
      </p>
    </div>
  )
}

function KeyboardSection({
  keyboard,
  listening,
  onStartListening,
}: {
  keyboard: ControlsInfo['keyboard']
  listening: Binding | null
  onStartListening: (binding: Binding) => void
}) {
  const hotkeyEntries = Object.entries(keyboard.preset_hotkeys)

  return (
    <section className="space-y-5">
      <SectionTitle icon={Keyboard} text="Teclado" />

      <div className="flex flex-wrap items-start gap-10">
        <Field label="Movimiento">
          <div className="flex flex-col items-center gap-1.5">
            <RebindableKey
              keyName={keyboard.up}
              binding={{ kind: 'action', field: 'up' }}
              listening={listening}
              onStart={onStartListening}
            />
            <div className="flex gap-1.5">
              <RebindableKey
                keyName={keyboard.left}
                binding={{ kind: 'action', field: 'left' }}
                listening={listening}
                onStart={onStartListening}
              />
              <RebindableKey
                keyName={keyboard.down}
                binding={{ kind: 'action', field: 'down' }}
                listening={listening}
                onStart={onStartListening}
              />
              <RebindableKey
                keyName={keyboard.right}
                binding={{ kind: 'action', field: 'right' }}
                listening={listening}
                onStart={onStartListening}
              />
            </div>
          </div>
        </Field>

        <Field label="Zoom">
          <div className="flex items-center gap-2">
            <LabeledKey
              keyName={keyboard.zoom_in}
              caption="zoom +"
              binding={{ kind: 'action', field: 'zoom_in' }}
              listening={listening}
              onStart={onStartListening}
            />
            <LabeledKey
              keyName={keyboard.zoom_out}
              caption="zoom −"
              binding={{ kind: 'action', field: 'zoom_out' }}
              listening={listening}
              onStart={onStartListening}
            />
          </div>
        </Field>

        <Field label="Detener / Salir">
          <div className="flex items-center gap-2">
            <LabeledKey
              keyName={keyboard.stop}
              caption="detener"
              binding={{ kind: 'action', field: 'stop' }}
              listening={listening}
              onStart={onStartListening}
            />
            <LabeledKey
              keyName={keyboard.quit}
              caption="salir"
              binding={{ kind: 'action', field: 'quit' }}
              listening={listening}
              onStart={onStartListening}
            />
          </div>
        </Field>
      </div>

      <Field label="Escenas (presets)">
        <div className="flex flex-wrap gap-2">
          {keyboard.preset_keys.map((key, index) => (
            <Chip key={index}>
              <RebindableKey
                small
                keyName={key}
                binding={{ kind: 'preset', index }}
                listening={listening}
                onStart={onStartListening}
              />
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

function LabeledKey({
  keyName,
  caption,
  binding,
  listening,
  onStart,
}: {
  keyName: string
  caption: string
  binding: Binding
  listening: Binding | null
  onStart: (binding: Binding) => void
}) {
  return (
    <div className="flex flex-col items-center gap-1.5">
      <RebindableKey keyName={keyName} binding={binding} listening={listening} onStart={onStart} />
      <span className="text-xs text-muted-foreground">{caption}</span>
    </div>
  )
}

function RebindableKey({
  keyName,
  binding,
  listening,
  onStart,
  small,
}: {
  keyName: string
  binding: Binding
  listening: Binding | null
  onStart: (binding: Binding) => void
  small?: boolean
}) {
  const isListening = listening !== null && bindingKey(listening) === bindingKey(binding)
  return (
    <button
      type="button"
      onClick={() => onStart(binding)}
      title="Clic para reasignar esta tecla"
      className={`cursor-pointer rounded-md transition-shadow ${
        isListening ? 'ring-2 ring-ring ring-offset-2 ring-offset-background' : ''
      }`}
    >
      <KeyCap small={small}>{isListening ? '…' : keyLabel(keyName)}</KeyCap>
    </button>
  )
}
