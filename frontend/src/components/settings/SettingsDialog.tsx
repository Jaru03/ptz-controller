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
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { api } from '@/lib/api'
import type { AppSettings } from '@/lib/types'

const ZOOM_MODE_LABELS: Record<AppSettings['movement']['zoom_mode'], string> = {
  continuous: 'Continuo (recomendado, compatible con casi cualquier cámara)',
  step: 'A saltos (puede no mover el zoom en algunas cámaras)',
  auto: 'Automático (a saltos, y si falla con error, continuo)',
}

/** Equivalente a gui/settings_dialog.py::SettingsDialog. */
export function SettingsDialog() {
  const [open, setOpen] = useState(false)
  const [settings, setSettings] = useState<AppSettings | null>(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (open) api.getSettings().then(setSettings)
  }, [open])

  function updateCamera<K extends keyof AppSettings['camera']>(key: K, value: AppSettings['camera'][K]) {
    setSettings((prev) => (prev ? { ...prev, camera: { ...prev.camera, [key]: value } } : prev))
  }

  function updateMovement<K extends keyof AppSettings['movement']>(
    key: K,
    value: AppSettings['movement'][K],
  ) {
    setSettings((prev) => (prev ? { ...prev, movement: { ...prev.movement, [key]: value } } : prev))
  }

  async function handleSave() {
    if (!settings) return
    setSaving(true)
    try {
      await api.saveSettings({ camera: settings.camera, movement: settings.movement })
      setOpen(false)
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" className="w-full">
          Configuración…
        </Button>
      </DialogTrigger>
      <DialogContent className="max-h-[85vh] min-w-0 overflow-y-auto sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Configuración</DialogTitle>
        </DialogHeader>
        {settings && (
          // min-w-0: DialogContent es un grid y, sin esto, un hijo con
          // contenido intrínsecamente ancho (aunque envuelva bien)
          // puede "reventar" la pista del grid más allá de max-w-md.
          <div className="min-w-0 space-y-3">
            <div className="space-y-1.5">
              <Label>IP de la cámara</Label>
              <Input value={settings.camera.ip} onChange={(e) => updateCamera('ip', e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label>Puerto</Label>
              <Input
                type="number"
                min={1}
                max={65535}
                value={settings.camera.port}
                onChange={(e) => updateCamera('port', Number(e.target.value) || 0)}
              />
            </div>
            <div className="space-y-1.5">
              <Label>Usuario</Label>
              <Input value={settings.camera.username} onChange={(e) => updateCamera('username', e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label>Contraseña</Label>
              <Input
                type="password"
                value={settings.camera.password}
                onChange={(e) => updateCamera('password', e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label>URL RTSP</Label>
              <Input
                value={settings.camera.rtsp_url}
                onChange={(e) => updateCamera('rtsp_url', e.target.value)}
                placeholder="Automática vía ONVIF si se deja vacío"
              />
            </div>
            <div className="flex items-center gap-2">
              <Checkbox
                id="settings-mock"
                checked={settings.camera.mock}
                onCheckedChange={(checked) => updateCamera('mock', checked === true)}
              />
              <Label htmlFor="settings-mock" className="font-normal">
                Usar cámara simulada (Mock)
              </Label>
            </div>
            <div className="space-y-1.5">
              <Label>Velocidad</Label>
              <Input
                type="number"
                min={0}
                max={1}
                step={0.05}
                value={settings.movement.speed}
                onChange={(e) => updateMovement('speed', Number(e.target.value))}
              />
            </div>
            <div className="space-y-1.5">
              <Label>Zona muerta</Label>
              <Input
                type="number"
                min={0}
                max={0.5}
                step={0.01}
                value={settings.movement.deadzone}
                onChange={(e) => updateMovement('deadzone', Number(e.target.value))}
              />
            </div>
            <div className="space-y-1.5">
              <Label>Modo de zoom</Label>
              <Select
                value={settings.movement.zoom_mode}
                onValueChange={(value) =>
                  updateMovement('zoom_mode', value as AppSettings['movement']['zoom_mode'])
                }
              >
                {/* SelectTrigger es w-fit + whitespace-nowrap por defecto: con
                    estas etiquetas largas eso reventaba el ancho del Dialog. */}
                <SelectTrigger className="w-full">
                  <SelectValue className="truncate" />
                </SelectTrigger>
                <SelectContent>
                  {(Object.keys(ZOOM_MODE_LABELS) as Array<AppSettings['movement']['zoom_mode']>).map(
                    (mode) => (
                      <SelectItem key={mode} value={mode}>
                        {ZOOM_MODE_LABELS[mode]}
                      </SelectItem>
                    ),
                  )}
                </SelectContent>
              </Select>
            </div>
          </div>
        )}
        {/* Div propio en vez de DialogFooter: su sangría negativa por
            defecto (pensada para pegar el pie a los bordes del diálogo)
            se salía del ancho con estos campos + el scroll vertical. */}
        <div className="flex justify-end gap-2 pt-2">
          <Button variant="ghost" onClick={() => setOpen(false)}>
            Cancelar
          </Button>
          <Button onClick={handleSave} disabled={!settings || saving}>
            {saving ? 'Guardando…' : 'Guardar'}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
