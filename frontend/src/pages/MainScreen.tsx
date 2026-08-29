import { useState } from 'react'
import { CameraStatusPanel } from '@/components/camera/CameraStatusPanel'
import { VideoPanel } from '@/components/video/VideoPanel'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useBusEvent } from '@/hooks/useBusEvent'
import type { PtzStatus } from '@/lib/types'

/**
 * Vista principal (equivalente a gui/main_window.py::MainWindow):
 * pestañas a la izquierda (Vista previa/Simulación/Controles/
 * Actualizaciones) + panel de estado a la derecha. En esta fase solo
 * "Simulación" (CameraStatusPanel) y el estado básico están conectados
 * de verdad; el resto de pestañas y el panel de conexión/presets llegan
 * en las fases siguientes.
 */
export function MainScreen() {
  const [status, setStatus] = useState<PtzStatus | null>(null)
  useBusEvent<PtzStatus>('ptz.status', setStatus)

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
            <PlaceholderPanel text="Referencia de controles — Fase 5" />
          </TabsContent>
          <TabsContent value="updates" className="h-[calc(100%-2.5rem)]">
            <PlaceholderPanel text="Actualizaciones — Fase 5" />
          </TabsContent>
        </Tabs>
      </div>
      <aside className="w-72 shrink-0 border-l bg-card p-4">
        <StatusSummary status={status} />
      </aside>
    </div>
  )
}

function PlaceholderPanel({ text }: { text: string }) {
  return (
    <div className="flex h-full items-center justify-center rounded-md border border-dashed text-sm text-muted-foreground">
      {text}
    </div>
  )
}

function StatusSummary({ status }: { status: PtzStatus | null }) {
  return (
    <div className="space-y-3 text-sm">
      <h2 className="font-medium">Estado</h2>
      <dl className="space-y-1 text-muted-foreground">
        <Row label="Conectada" value={status?.connected ? 'Sí' : 'No'} />
        <Row label="Cámara" value={status?.device_name || '—'} />
        <Row label="IP" value={status?.ip || '—'} />
        <Row label="Entrada" value={status?.input_active || '—'} />
        <Row label="Velocidad" value={status ? `${Math.round(status.speed * 100)}%` : '—'} />
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
