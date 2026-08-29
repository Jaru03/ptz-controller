import { useState } from 'react'
import { CameraStatusPanel } from '@/components/camera/CameraStatusPanel'
import { ConnectionCard } from '@/components/connection/ConnectionCard'
import { SpeedControl } from '@/components/connection/SpeedControl'
import { ControlsPanel } from '@/components/controls/ControlsPanel'
import { PresetsPanel } from '@/components/presets/PresetsPanel'
import { SettingsDialog } from '@/components/settings/SettingsDialog'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { UpdatesPanel } from '@/components/updates/UpdatesPanel'
import { VideoPanel } from '@/components/video/VideoPanel'
import { useBusEvent } from '@/hooks/useBusEvent'
import { useWindowKeyboard } from '@/hooks/useWindowKeyboard'
import type { PtzStatus } from '@/lib/types'

/**
 * Vista principal (equivalente a gui/main_window.py::MainWindow):
 * pestañas a la izquierda (Vista previa/Simulación/Controles/
 * Actualizaciones) + panel de control a la derecha (conexión, estado,
 * velocidad, presets, ajustes).
 */
export function MainScreen() {
  const [status, setStatus] = useState<PtzStatus | null>(null)
  useBusEvent<PtzStatus>('ptz.status', setStatus)
  useWindowKeyboard()

  return (
    <div className="flex h-svh w-full bg-background text-foreground">
      <div className="min-w-0 flex-1 p-4">
        <Tabs defaultValue="camera" className="h-full">
          <TabsList>
            <TabsTrigger value="video">Vista previa</TabsTrigger>
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
        <ConnectionCard />
        <StatusSummary status={status} />
        <SpeedControl />
        <PresetsPanel />
        <SettingsDialog />
      </aside>
    </div>
  )
}

function StatusSummary({ status }: { status: PtzStatus | null }) {
  return (
    <div className="space-y-2 text-sm">
      <h2 className="font-medium">Estado</h2>
      <dl className="space-y-1 text-muted-foreground">
        <Row label="Conectada" value={status?.connected ? 'Sí' : 'No'} />
        <Row label="Cámara" value={status?.device_name || '—'} />
        <Row label="IP" value={status?.ip || '—'} />
        <Row label="Entrada" value={status?.input_active || '—'} />
      </dl>
    </div>
  )
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-2">
      <dt>{label}</dt>
      <dd className="text-foreground">{value}</dd>
    </div>
  )
}
