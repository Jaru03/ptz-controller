import { useEffect, useState } from 'react'
import { motion } from 'motion/react'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { api } from '@/lib/api'
import type { CameraSettings, DiscoveredDevice } from '@/lib/types'

const EMPTY_CAMERA: CameraSettings = {
  ip: '',
  port: 80,
  username: 'admin',
  password: '',
  rtsp_url: '',
  mock: true,
}

/**
 * Pantalla mostrada al arrancar, antes de la vista principal. Equivalente
 * a gui/connection_dialog.py::ConnectionDialog: pide IP/puerto/
 * credenciales/mock, permite buscar cámaras en la red y, al confirmar,
 * aplica los datos y pide conectar (bus.send(ConnectCommand())).
 */
export function ConnectionScreen({ onConnected }: { onConnected: () => void }) {
  const [camera, setCamera] = useState<CameraSettings>(EMPTY_CAMERA)
  const [loaded, setLoaded] = useState(false)
  const [discovering, setDiscovering] = useState(false)
  const [devices, setDevices] = useState<DiscoveredDevice[] | null>(null)
  const [error, setError] = useState('')
  const [connecting, setConnecting] = useState(false)

  useEffect(() => {
    api
      .getSettings()
      .then((settings) => setCamera(settings.camera))
      .catch((err: unknown) => setError(String(err)))
      .finally(() => setLoaded(true))
  }, [])

  function update<K extends keyof CameraSettings>(key: K, value: CameraSettings[K]) {
    setCamera((prev) => ({ ...prev, [key]: value }))
  }

  async function handleDiscover() {
    setDiscovering(true)
    setError('')
    try {
      const found = await api.discover()
      setDevices(found)
      if (found.length === 1) {
        update('ip', found[0].host)
        update('port', found[0].port)
        setDevices(null)
      } else if (found.length === 0) {
        setError('No se encontraron cámaras ONVIF.')
      }
    } catch (err) {
      setError(`Error al buscar cámaras: ${String(err)}`)
    } finally {
      setDiscovering(false)
    }
  }

  function pickDevice(device: DiscoveredDevice) {
    update('ip', device.host)
    update('port', device.port)
    setDevices(null)
  }

  async function handleConnect() {
    setConnecting(true)
    setError('')
    try {
      await api.applyConnectionSettings(camera)
      await api.connect()
      onConnected()
    } catch (err) {
      setError(String(err))
      setConnecting(false)
    }
  }

  function handleCancel() {
    void api.quit()
  }

  return (
    <div className="flex min-h-svh items-center justify-center bg-background p-6">
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35, ease: 'easeOut' }}
      >
        <Card className="w-96">
          <CardHeader>
            <CardTitle>Conectar con la cámara</CardTitle>
            <CardDescription>
              Datos de conexión ONVIF, o active «cámara simulada» para probar sin
              hardware.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-3 gap-3">
              <div className="col-span-2 space-y-1.5">
                <Label htmlFor="ip">IP</Label>
                <Input
                  id="ip"
                  value={camera.ip}
                  onChange={(e) => update('ip', e.target.value)}
                  disabled={!loaded}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="port">Puerto</Label>
                <Input
                  id="port"
                  type="number"
                  min={1}
                  max={65535}
                  value={camera.port}
                  onChange={(e) => update('port', Number(e.target.value) || 0)}
                  disabled={!loaded}
                />
              </div>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="username">Usuario</Label>
              <Input
                id="username"
                value={camera.username}
                onChange={(e) => update('username', e.target.value)}
                disabled={!loaded}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="password">Contraseña</Label>
              <Input
                id="password"
                type="password"
                value={camera.password}
                onChange={(e) => update('password', e.target.value)}
                disabled={!loaded}
              />
            </div>
            <div className="flex items-center gap-2">
              <Checkbox
                id="mock"
                checked={camera.mock}
                onCheckedChange={(checked) => update('mock', checked === true)}
                disabled={!loaded}
              />
              <Label htmlFor="mock" className="font-normal">
                Cámara simulada (Mock)
              </Label>
            </div>

            <Button
              type="button"
              variant="outline"
              className="w-full"
              onClick={handleDiscover}
              disabled={!loaded || discovering}
            >
              {discovering ? 'Buscando…' : 'Buscar cámaras…'}
            </Button>

            {devices && devices.length > 1 && (
              <div className="space-y-1 rounded-md border p-2">
                {devices.map((device) => (
                  <button
                    key={`${device.host}:${device.port}`}
                    type="button"
                    className="block w-full rounded px-2 py-1 text-left text-sm hover:bg-accent"
                    onClick={() => pickDevice(device)}
                  >
                    {device.host}:{device.port}
                  </button>
                ))}
              </div>
            )}

            {error && <p className="text-sm text-destructive">{error}</p>}
          </CardContent>
          <CardFooter className="flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={handleCancel}>
              Cancelar
            </Button>
            <Button type="button" onClick={handleConnect} disabled={!loaded || connecting}>
              {connecting ? 'Conectando…' : 'Conectar'}
            </Button>
          </CardFooter>
        </Card>
      </motion.div>
    </div>
  )
}
