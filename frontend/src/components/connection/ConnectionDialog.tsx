import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useBusEvent } from '@/hooks/useBusEvent'
import { api } from '@/lib/api'
import type { CameraSettings, PtzStatus } from '@/lib/types'

/**
 * Reconectar sin reiniciar la app, en un diálogo (no un formulario
 * siempre visible en el panel lateral): mostrar los mismos campos de
 * IP/usuario/contraseña dos veces —aquí y en ConnectionScreen al
 * arrancar— quedaba repetitivo. El estado de conexión en sí sigue
 * visible permanentemente en el resumen "Estado" de MainScreen.
 *
 * Única fuente de verdad para la identidad de la cámara (IP, puerto,
 * credenciales, RTSP, mock): se guarda con
 * ``Api.apply_connection_settings``, que persiste a config.yaml.
 * SettingsDialog no repite estos campos, solo edita el comportamiento
 * de movimiento — ver su propio docstring.
 */
export function ConnectionDialog() {
  const [open, setOpen] = useState(false)
  const [camera, setCamera] = useState<CameraSettings | null>(null)
  const [connected, setConnected] = useState(false)
  const [discovering, setDiscovering] = useState(false)

  useBusEvent<PtzStatus>('ptz.status', (status) => setConnected(status.connected))

  useEffect(() => {
    if (open) api.getSettings().then((settings) => setCamera(settings.camera))
  }, [open])

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
    setOpen(false)
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" className="w-full">
          Conexión…
        </Button>
      </DialogTrigger>
      <DialogContent className="min-w-0 sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Conexión</DialogTitle>
        </DialogHeader>
        {camera && (
          <div className="min-w-0 space-y-3">
            <div className="grid grid-cols-3 gap-2">
              <div className="col-span-2 space-y-1.5">
                <Label htmlFor="conn-ip">IP</Label>
                <Input id="conn-ip" value={camera.ip} onChange={(e) => update('ip', e.target.value)} />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="conn-port">Puerto</Label>
                <Input
                  id="conn-port"
                  type="number"
                  value={camera.port}
                  onChange={(e) => update('port', Number(e.target.value) || 0)}
                />
              </div>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="conn-user">Usuario</Label>
              <Input
                id="conn-user"
                value={camera.username}
                onChange={(e) => update('username', e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="conn-pass">Contraseña</Label>
              <Input
                id="conn-pass"
                type="password"
                value={camera.password}
                onChange={(e) => update('password', e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="conn-rtsp">URL RTSP</Label>
              <Input
                id="conn-rtsp"
                value={camera.rtsp_url}
                onChange={(e) => update('rtsp_url', e.target.value)}
                placeholder="Automática vía ONVIF si se deja vacío"
              />
            </div>
            <div className="flex items-center gap-2">
              <Checkbox
                id="conn-mock"
                checked={camera.mock}
                onCheckedChange={(checked) => update('mock', checked === true)}
              />
              <Label htmlFor="conn-mock" className="font-normal">
                Cámara simulada (Mock)
              </Label>
            </div>
            <div className="flex gap-2 pt-1">
              <Button variant="outline" className="flex-1" onClick={handleDiscover} disabled={discovering}>
                {discovering ? 'Buscando…' : 'Buscar cámaras…'}
              </Button>
              <Button className="flex-1" onClick={toggleConnect}>
                {connected ? 'Desconectar' : 'Conectar'}
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
