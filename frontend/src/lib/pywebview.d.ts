import type { AppSettings, CameraSettings, DiscoveredDevice } from './types'

/**
 * pywebview inyecta `window.pywebview.api` de forma asíncrona (tras
 * cargar la página) y dispara el evento `pywebviewready` en `window`
 * cuando ya está disponible (ver lib/api.ts::ready()). Esta forma debe
 * mantenerse en paso con los métodos de gui_web/api.py::Api — no hay
 * generación automática entre Python y TS, así que al añadir un método
 * ahí hay que añadirlo aquí también.
 */
declare global {
  interface Window {
    pywebview?: {
      api: {
        connect(): Promise<{ ok: boolean }>
        apply_connection_settings(
          patch: Partial<CameraSettings>,
        ): Promise<{ ok: boolean }>
        discover(): Promise<DiscoveredDevice[]>
        get_settings(): Promise<AppSettings>
        quit(): Promise<{ ok: boolean }>
      }
    }
    __ptzBridge: import('./bridge').BusBridge
  }

  interface WindowEventMap {
    pywebviewready: Event
  }
}

export {}
