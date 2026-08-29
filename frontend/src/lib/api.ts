/**
 * Wrapper tipado de `window.pywebview.api.*` (gui_web/api.py::Api).
 * pywebview inyecta `window.pywebview` de forma asíncrona tras cargar la
 * página; `ready()` espera el evento `pywebviewready` si aún no está.
 */
import type {
  AppSettings,
  CameraSettings,
  ControlsInfo,
  DiscoveredDevice,
  MovementSettings,
  UpdateResult,
} from './types'

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
  disconnect: () => call((a) => a.disconnect()),
  applyConnectionSettings: (patch: Partial<CameraSettings>) =>
    call((a) => a.apply_connection_settings(patch)),
  discover: (): Promise<DiscoveredDevice[]> => call((a) => a.discover()),
  gotoPreset: (token: string) => call((a) => a.goto_preset(token)),
  setPreset: (token: string, name: string) => call((a) => a.set_preset(token, name)),
  renamePreset: (token: string, name: string) => call((a) => a.rename_preset(token, name)),
  removePreset: (token: string) => call((a) => a.remove_preset(token)),
  setSpeed: (speed: number) => call((a) => a.set_speed(speed)),
  getSettings: (): Promise<AppSettings> => call((a) => a.get_settings()),
  saveSettings: (patch: {
    camera?: Partial<CameraSettings>
    movement?: Partial<MovementSettings>
  }): Promise<AppSettings> => call((a) => a.save_settings(patch)),
  getControlsInfo: (): Promise<ControlsInfo> => call((a) => a.get_controls_info()),
  getVersion: (): Promise<string> => call((a) => a.get_version()),
  checkForUpdates: (): Promise<UpdateResult> => call((a) => a.check_for_updates()),
  openReleasesPage: () => call((a) => a.open_releases_page()),
  quit: () => call((a) => a.quit()),
}
