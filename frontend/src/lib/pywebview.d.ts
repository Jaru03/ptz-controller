import type { AppSettings, CameraSettings, ControlsInfo, DiscoveredDevice, UpdateResult } from './types'

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
        disconnect(): Promise<{ ok: boolean }>
        apply_connection_settings(
          patch: Partial<CameraSettings>,
        ): Promise<{ ok: boolean }>
        discover(): Promise<DiscoveredDevice[]>
        goto_preset(token: string): Promise<{ ok: boolean }>
        set_preset(token: string, name: string): Promise<{ ok: boolean }>
        rename_preset(token: string, name: string): Promise<{ ok: boolean }>
        remove_preset(token: string): Promise<{ ok: boolean }>
        set_speed(speed: number): Promise<{ ok: boolean }>
        get_settings(): Promise<AppSettings>
        save_settings(patch: {
          camera?: Partial<CameraSettings>
          movement?: Partial<import('./types').MovementSettings>
        }): Promise<AppSettings>
        keyboard_requires_window_events(): Promise<boolean>
        key_down(name: string): Promise<void>
        key_up(name: string): Promise<void>
        get_controls_info(): Promise<ControlsInfo>
        get_version(): Promise<string>
        check_for_updates(): Promise<UpdateResult>
        open_releases_page(): Promise<{ ok: boolean }>
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
