import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
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

/**
 * Equivalente a gui/settings_dialog.py::SettingsDialog: solo comportamiento
 * de movimiento (velocidad, zona muerta, modo de zoom). La identidad de la
 * cámara (IP, credenciales, RTSP, mock) vive únicamente en
 * ConnectionDialog, para no repetir el mismo formulario en dos diálogos.
 */
export function SettingsDialog() {
  const [open, setOpen] = useState(false)
  const [movement, setMovement] = useState<AppSettings['movement'] | null>(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (open) api.getSettings().then((settings) => setMovement(settings.movement))
  }, [open])

  function updateMovement<K extends keyof AppSettings['movement']>(
    key: K,
    value: AppSettings['movement'][K],
  ) {
    setMovement((prev) => (prev ? { ...prev, [key]: value } : prev))
  }

  async function handleSave() {
    if (!movement) return
    setSaving(true)
    try {
      await api.saveSettings({ movement })
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
        {movement && (
          // min-w-0: DialogContent es un grid y, sin esto, un hijo con
          // contenido intrínsecamente ancho (aunque envuelva bien)
          // puede "reventar" la pista del grid más allá de max-w-md.
          <div className="min-w-0 space-y-3">
            <div className="space-y-1.5">
              <Label>Velocidad</Label>
              <Input
                type="number"
                min={0}
                max={1}
                step={0.05}
                value={movement.speed}
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
                value={movement.deadzone}
                onChange={(e) => updateMovement('deadzone', Number(e.target.value))}
              />
            </div>
            <div className="space-y-1.5">
              <Label>Modo de zoom</Label>
              <Select
                value={movement.zoom_mode}
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
          <Button onClick={handleSave} disabled={!movement || saving}>
            {saving ? 'Guardando…' : 'Guardar'}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
