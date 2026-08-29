import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import { api } from '@/lib/api'
import type { UpdateResult } from '@/lib/types'

type Status = 'idle' | 'checking' | 'ok' | 'warn' | 'error'

/** Equivalente a gui/updates_widget.py::UpdatesWidget. */
export function UpdatesPanel() {
  const [version, setVersion] = useState('')
  const [status, setStatus] = useState<Status>('idle')
  const [message, setMessage] = useState('Pulse el botón para comprobar si hay una versión nueva.')

  useEffect(() => {
    api.getVersion().then(setVersion)
  }, [])

  async function handleCheck() {
    setStatus('checking')
    setMessage('Comprobando…')
    let result: UpdateResult
    try {
      result = await api.checkForUpdates()
    } catch (err) {
      setStatus('error')
      setMessage(`No se pudo comprobar: ${String(err)}`)
      return
    }
    if (!result.ok) {
      setStatus('error')
      setMessage(`No se pudo comprobar: ${result.error || 'error desconocido'}`)
      return
    }
    if (result.up_to_date) {
      setStatus('ok')
      setMessage(`Está al día: la versión instalada es la más reciente (v${result.current}).`)
      return
    }
    setStatus('warn')
    setMessage(
      `Nueva versión disponible: ${result.latest} (tiene v${result.current}). Abra la página de releases para descargarla.`,
    )
  }

  return (
    <div className="h-full space-y-4 overflow-y-auto p-1">
      <section className="space-y-2">
        <h3 className="text-sm font-medium">Versión instalada</h3>
        <div className="rounded-md border p-3 text-sm">
          <span className="text-muted-foreground">ptz-controller: </span>
          {version || '—'}
        </div>
      </section>

      <section className="space-y-2">
        <h3 className="text-sm font-medium">Buscar actualizaciones</h3>
        <div className="space-y-3 rounded-md border p-3">
          <p className={`text-sm ${STATUS_CLASS[status]}`}>{message}</p>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" onClick={handleCheck} disabled={status === 'checking'}>
              Buscar actualizaciones
            </Button>
            <Button size="sm" variant="outline" onClick={() => void api.openReleasesPage()}>
              Abrir página de releases
            </Button>
          </div>
        </div>
      </section>

      <p className="rounded-md border bg-muted/50 p-3 text-sm text-muted-foreground">
        La comprobación consulta la API pública de GitHub y no envía ningún dato de su
        cámara ni de su configuración.
      </p>
    </div>
  )
}

const STATUS_CLASS: Record<Status, string> = {
  idle: 'text-muted-foreground',
  checking: 'text-muted-foreground',
  ok: 'text-emerald-600 dark:text-emerald-400',
  warn: 'text-amber-600 dark:text-amber-400',
  error: 'text-destructive',
}
