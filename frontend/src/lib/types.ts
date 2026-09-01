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

/** Payload de gui.streamState (gui_web/video_controller.py). */
export interface StreamState {
  status: 'stopped' | 'connecting' | 'streaming' | 'error'
  message: string
}

/** Payload de input.keyboard (controllers/keyboard_controller.py::_notify_active). */
export interface KeyboardInputState {
  active: boolean
  backend: string
}

/** Payload de input.joystick (controllers/joystick_controller.py). */
export interface JoystickInputState {
  connected: boolean
  name: string
  moving: boolean
}

export interface KeyboardConfig {
  backend: 'auto' | 'pynput' | 'qt' | 'window'
  up: string
  down: string
  left: string
  right: string
  zoom_in: string
  zoom_out: string
  preset_keys: string[]
  preset_hotkeys: Record<string, string>
  stop: string
  quit: string
}

export interface JoystickConfig {
  poll_rate: number
  deadzone: number
  pan_axis: number
  tilt_axis: number
  invert_tilt: boolean
  zoom_out_axis: number
  zoom_in_axis: number
  speed_down_button: number
  speed_up_button: number
  home_button: number
  preset_buttons: number[]
  device_overrides: Record<string, Record<string, unknown>>
}

/** Payload de Api.get_controls_info() (gui_web/api.py). */
export interface ControlsInfo {
  keyboard: KeyboardConfig
  joystick: JoystickConfig
}

/** Resultado de Api.save_keyboard_settings() (gui_web/api.py). */
export interface KeyboardSettingsResult {
  ok: boolean
  error?: string
  settings?: { keyboard: KeyboardConfig }
}

/** Payload de Api.check_for_updates() (models/version.py::UpdateResult). */
export interface UpdateResult {
  ok: boolean
  error: string
  current: string
  latest: string
  up_to_date: boolean
  release_url: string
}
