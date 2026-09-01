import { useEffect, useRef, useState } from 'react'
import { CameraStatusPanel } from '@/components/camera/CameraStatusPanel'
import { ConnectionDialog } from '@/components/connection/ConnectionDialog'
import { SpeedControl } from '@/components/connection/SpeedControl'
import { ControlsPanel } from '@/components/controls/ControlsPanel'
import { PresetsPanel } from '@/components/presets/PresetsPanel'
import { SettingsDialog } from '@/components/settings/SettingsDialog'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { UpdatesPanel } from '@/components/updates/UpdatesPanel'
import { VideoPanel } from '@/components/video/VideoPanel'
import { useBusEvent } from '@/hooks/useBusEvent'
import { useWindowKeyboard } from '@/hooks/useWindowKeyboard'
import type { JoystickInputState, KeyboardInputState, PtzStatus } from '@/lib/types'

/**
 * Vista principal (equivalente a gui/main_window.py::MainWindow):
 * pestañas a la izquierda (Cámara/Simulación/Controles/Actualizaciones)
 * + panel de control a la derecha (conexión, estado, velocidad,
 * presets, ajustes).
 */
export function MainScreen() {
  const [status, setStatus] = useState<PtzStatus | null>(null)
  const [keyboard, setKeyboard] = useState<KeyboardInputState | null>(null)
  const [joystick, setJoystick] = useState<JoystickInputState | null>(null)
  useBusEvent<PtzStatus>('ptz.status', setStatus)
  useBusEvent<KeyboardInputState>('input.keyboard', setKeyboard)
  useBusEvent<JoystickInputState>('input.joystick', setJoystick)
  useWindowKeyboard()

  return (
    <div className="flex h-svh w-full bg-background text-foreground">
      <div className="min-w-0 flex-1 p-4">
        <Tabs defaultValue="camera" className="h-full">
          <TabsList>
            <TabsTrigger value="video">Cámara</TabsTrigger>
            <TabsTrigger value="camera">Simulación</TabsTrigger>
            <TabsTrigger value="controls">Controles</TabsTrigger>
            <TabsTrigger value="updates">Actualizaciones</TabsTrigger>
          </TabsList>
          <TabsContent value="video" className="h-[calc(100%-2.5rem)]">
            <VideoPanel />
          </TabsContent>
          <TabsContent value="camera" className="h-[calc(100%-2.5rem)]">
            <CameraStatusPanel />
          </TabsContent>
          <TabsContent value="controls" className="h-[calc(100%-2.5rem)]">
            <ControlsPanel />
          </TabsContent>
          <TabsContent value="updates" className="h-[calc(100%-2.5rem)]">
            <UpdatesPanel />
          </TabsContent>
        </Tabs>
      </div>
      <aside className="w-72 shrink-0 space-y-4 overflow-y-auto border-l bg-card p-4">
        <StatusSummary status={status} keyboard={keyboard} joystick={joystick} />
        <SpeedControl />
        <PresetsPanel />
        <div className="space-y-2 border-t pt-4">
          <ConnectionDialog />
          <SettingsDialog />
        </div>
      </aside>
    </div>
  )
}

type InputSource = 'teclado' | 'mando'

/**
 * Última fuente de entrada detectada (teclado o mando), para mostrar
 * siempre una única fila fija en vez de que el indicador entre y salga
 * del DOM. Empieza en 'teclado' y solo cambia en el flanco de subida de
 * cada fuente (el momento en que pasa a estar activa), así que si ambas
 * están activas a la vez se queda con la que se detectó más
 * recientemente.
 */
function useActiveInputSource(
  keyboard: KeyboardInputState | null,
  joystick: JoystickInputState | null,
): InputSource {
  const [source, setSource] = useState<InputSource>('teclado')
  const wasKeyboardActive = useRef(false)
  const wasJoystickActive = useRef(false)

  useEffect(() => {
    const keyboardActive = keyboard?.active ?? false
    if (keyboardActive && !wasKeyboardActive.current) setSource('teclado')
    wasKeyboardActive.current = keyboardActive
  }, [keyboard])

  useEffect(() => {
    const joystickActive = joystick?.moving ?? false
    if (joystickActive && !wasJoystickActive.current) setSource('mando')
    wasJoystickActive.current = joystickActive
  }, [joystick])

  return source
}

function StatusSummary({
  status,
  keyboard,
  joystick,
}: {
  status: PtzStatus | null
  keyboard: KeyboardInputState | null
  joystick: JoystickInputState | null
}) {
  const source = useActiveInputSource(keyboard, joystick)
  const inputValue =
    source === 'teclado'
      ? `Teclado${keyboard?.active ? ` (${keyboard.backend})` : ''}`
      : `Mando${joystick?.name ? ` (${joystick.name})` : ''}`

  return (
    <div className="space-y-2 text-sm">
      <h2 className="font-medium">Estado</h2>
      <dl className="space-y-1 text-muted-foreground">
        <Row label="Conectada" value={status?.connected ? 'Sí' : 'No'} />
        <Row label="Cámara" value={status?.device_name || '—'} />
        <Row label="Entrada" value={inputValue} />
      </dl>
    </div>
  )
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-2">
      <dt className="shrink-0">{label}</dt>
      <dd className="text-right text-foreground">{value}</dd>
    </div>
  )
}
