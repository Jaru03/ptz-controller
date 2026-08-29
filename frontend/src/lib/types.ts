/**
 * Tipos espejo de models/commands.py y config/settings.py. Se amplía en
 * fases sucesivas conforme el resto de paneles (presets, ajustes,
 * controles) los necesite.
 */

export interface CameraSettings {
  ip: string
  port: number
  username: string
  password: string
  rtsp_url: string
  mock: boolean
}

export interface MovementSettings {
  speed: number
  speeds: number[]
  deadzone: number
  repeat_interval_ms: number
  zoom_mode: 'continuous' | 'step' | 'auto'
  zoom_step: number
}

/** Subconjunto de Settings que ya usa el frontend; el resto llega en fases posteriores. */
export interface AppSettings {
  camera: CameraSettings
  movement: MovementSettings
}

export interface DiscoveredDevice {
  host: string
  port: number
  xaddrs: string[]
  scopes: string[]
  types: string[]
}

export interface PresetInfo {
  token: string
  name: string
}

export interface PtzStatus {
  connected: boolean
  pan: number
  tilt: number
  zoom: number
  speed: number
  device_name: string
  ip: string
  input_active: string
  presets: PresetInfo[]
}
