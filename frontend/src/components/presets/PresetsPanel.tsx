import { useState } from 'react'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useBusEvent } from '@/hooks/useBusEvent'
import { api } from '@/lib/api'
import type { PresetInfo } from '@/lib/types'

/**
 * Equivalente al grupo "Presets" de gui/main_window.py: lista + ir/
 * guardar/renombrar/borrar. El diálogo de nombre+token replica
 * MainWindow._prompt_preset (dejar el token vacío hace que lo asigne la
 * cámara).
 */
export function PresetsPanel() {
  const [presets, setPresets] = useState<PresetInfo[]>([])
  const [selected, setSelected] = useState<string | null>(null)
  const [prompt, setPrompt] = useState<{ mode: 'save' | 'rename'; name: string; token: string } | null>(
    null,
  )

  useBusEvent<PresetInfo[]>('ptz.presets', (list) => setPresets(list || []))

  const selectedPreset = presets.find((p) => p.token === selected) ?? null

  function goto(token: string) {
    void api.gotoPreset(token)
  }

  function openSave() {
    setPrompt({ mode: 'save', name: '', token: '' })
  }

  function openRename() {
    if (!selectedPreset) return
    setPrompt({ mode: 'rename', name: selectedPreset.name, token: selectedPreset.token })
  }

  function remove() {
    if (!selected) return
    void api.removePreset(selected)
    setSelected(null)
  }

  function confirmPrompt() {
    if (!prompt) return
    if (prompt.mode === 'save') {
      void api.setPreset(prompt.token.trim(), prompt.name.trim())
    } else {
      const originalToken = selectedPreset?.token ?? ''
      const newToken = prompt.token.trim()
      if (newToken !== originalToken) {
        void api.removePreset(originalToken)
        void api.setPreset(newToken, prompt.name.trim())
      } else {
        void api.renamePreset(originalToken, prompt.name.trim())
      }
    }
    setPrompt(null)
  }

  return (
    <div className="space-y-2">
      <h2 className="text-sm font-medium">Presets</h2>
      <div className="max-h-48 space-y-1 overflow-y-auto rounded-md border p-1">
        {presets.length === 0 && (
          <p className="p-2 text-sm text-muted-foreground">Sin presets guardados</p>
        )}
        {presets.map((preset) => (
          <button
            key={preset.token}
            type="button"
            onDoubleClick={() => goto(preset.token)}
            onClick={() => setSelected(preset.token)}
            className={`block w-full rounded px-2 py-1 text-left text-sm hover:bg-accent ${
              selected === preset.token ? 'bg-accent' : ''
            }`}
          >
            {preset.name || `Preset ${preset.token}`} <span className="text-muted-foreground">[{preset.token}]</span>
          </button>
        ))}
      </div>
      <div className="grid grid-cols-4 gap-1">
        <Button size="sm" variant="outline" disabled={!selected} onClick={() => selected && goto(selected)}>
          Ir
        </Button>
        <Button size="sm" variant="outline" onClick={openSave}>
          Guardar
        </Button>
        <Button size="sm" variant="outline" disabled={!selected} onClick={openRename}>
          Renombrar
        </Button>
        <Button size="sm" variant="outline" disabled={!selected} onClick={remove}>
          Borrar
        </Button>
      </div>

      <Dialog open={prompt !== null} onOpenChange={(open) => !open && setPrompt(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{prompt?.mode === 'save' ? 'Guardar preset' : 'Renombrar preset'}</DialogTitle>
            <DialogDescription>
              Deje el token vacío para que la cámara le asigne uno automáticamente.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div className="space-y-1.5">
              <Label htmlFor="preset-name">Nombre</Label>
              <Input
                id="preset-name"
                value={prompt?.name ?? ''}
                onChange={(e) => setPrompt((p) => (p ? { ...p, name: e.target.value } : p))}
                placeholder="Nombre del preset (ej. Entrada principal)"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="preset-token">Token</Label>
              <Input
                id="preset-token"
                value={prompt?.token ?? ''}
                onChange={(e) => setPrompt((p) => (p ? { ...p, token: e.target.value } : p))}
                placeholder="Vacío: lo asigna la cámara"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setPrompt(null)}>
              Cancelar
            </Button>
            <Button onClick={confirmPrompt}>Aceptar</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
