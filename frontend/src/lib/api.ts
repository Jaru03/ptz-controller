/**
 * Wrapper tipado de `window.pywebview.api.*` (gui_web/api.py::Api).
 * pywebview inyecta `window.pywebview` de forma asíncrona tras cargar la
 * página; `ready()` espera el evento `pywebviewready` si aún no está.
 */
import type { AppSettings, CameraSettings, DiscoveredDevice } from './types'

function ready(): Promise<void> {
  if (window.pywebview) return Promise.resolve()
  return new Promise((resolve) => {
    window.addEventListener('pywebviewready', () => resolve(), { once: true })
  })
}

async function call<T>(fn: (api: NonNullable<Window['pywebview']>['api']) => Promise<T>): Promise<T> {
  await ready()
  return fn(window.pywebview!.api)
}

export const api = {
  connect: () => call((a) => a.connect()),
  applyConnectionSettings: (patch: Partial<CameraSettings>) =>
    call((a) => a.apply_connection_settings(patch)),
  discover: (): Promise<DiscoveredDevice[]> => call((a) => a.discover()),
  getSettings: (): Promise<AppSettings> => call((a) => a.get_settings()),
  quit: () => call((a) => a.quit()),
}
