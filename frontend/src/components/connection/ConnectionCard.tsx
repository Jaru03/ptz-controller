import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useBusEvent } from '@/hooks/useBusEvent'
import { api } from '@/lib/api'
import type { CameraSettings, PtzStatus } from '@/lib/types'

/**
 * Grupo "Conexión" del panel lateral de gui/main_window.py: permite
 * reconectar sin reiniciar la app (ConnectionScreen solo cubre el
 * arranque). Compacto a propósito — el formulario completo con
 * descubrimiento ya se vio una vez en ConnectionScreen.
 */
export function ConnectionCard() {
  const [camera, setCamera] = useState<CameraSettings | null>(null)
  const [connected, setConnected] = useState(false)
  const [discovering, setDiscovering] = useState(false)

  useBusEvent<PtzStatus>('ptz.status', (status) => setConnected(status.connected))

  useEffect(() => {
    api.getSettings().then((settings) => setCamera(settings.camera))
  }, [])

  function update<K extends keyof CameraSettings>(key: K, value: CameraSettings[K]) {
    setCamera((prev) => (prev ? { ...prev, [key]: value } : prev))
  }

  async function handleDiscover() {
    setDiscovering(true)
    try {
      const found = await api.discover()
      if (found.length >= 1) {
        update('ip', found[0].host)
        update('port', found[0].port)
      }
    } finally {
      setDiscovering(false)
    }
  }

  async function toggleConnect() {
    if (connected) {
      await api.disconnect()
      return
    }
    if (camera) await api.applyConnectionSettings(camera)
    await api.connect()
  }

  if (!camera) return null

  return (
    <div className="space-y-2">
      <h2 className="text-sm font-medium">Conexión</h2>
      <div className="grid grid-cols-3 gap-2">
        <Input
          className="col-span-2"
          value={camera.ip}
          onChange={(e) => update('ip', e.target.value)}
          placeholder="IP"
        />
        <Input
          type="number"
          value={camera.port}
          onChange={(e) => update('port', Number(e.target.value) || 0)}
          placeholder="Puerto"
        />
      </div>
      <Input value={camera.username} onChange={(e) => update('username', e.target.value)} placeholder="Usuario" />
      <Input
        type="password"
        value={camera.password}
        onChange={(e) => update('password', e.target.value)}
        placeholder="Contraseña"
      />
      <div className="flex items-center gap-2">
        <Checkbox
          id="sidebar-mock"
          checked={camera.mock}
          onCheckedChange={(checked) => update('mock', checked === true)}
        />
        <Label htmlFor="sidebar-mock" className="text-sm font-normal">
          Cámara simulada (Mock)
        </Label>
      </div>
      <div className="flex gap-2">
        <Button size="sm" variant="outline" className="flex-1" onClick={handleDiscover} disabled={discovering}>
          {discovering ? 'Buscando…' : 'Buscar…'}
        </Button>
        <Button size="sm" className="flex-1" onClick={toggleConnect}>
          {connected ? 'Desconectar' : 'Conectar'}
        </Button>
      </div>
    </div>
  )
}
