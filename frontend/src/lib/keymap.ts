/**
 * Traducción entre nombres canónicos de tecla ('w', 'space', 'kp_1'...) y
 * el mundo del navegador: `mapKeyEvent` convierte un `KeyboardEvent` de JS
 * a nombre canónico (equivalente a
 * controllers/keyboard_controller.py::qt_key_name, usado por el backend
 * "window" — ver hooks/useWindowKeyboard.ts) y `keyLabel` hace lo
 * contrario, a una etiqueta legible ('W', 'Espacio', 'Num 1'...) para
 * ControlsPanel.tsx (port de gui/controls_widget.py::_key_label).
 */

const ALIASES: Record<string, string> = {
  esc: 'ESC',
  space: 'Espacio',
  up: '↑',
  down: '↓',
  left: '←',
  right: '→',
  shift: 'Shift',
  ctrl: 'Ctrl',
  alt: 'Alt',
}

export function keyLabel(name: string): string {
  if (name in ALIASES) return ALIASES[name]
  if (name.startsWith('kp_')) return `Num ${name.slice(3).toUpperCase()}`
  return name.toUpperCase()
}

// `code` es la tecla física (no cambia con Bloq Num ni con el layout de
// idioma), así que el pad numérico se identifica de forma consistente sin
// necesitar, a diferencia de Qt, dos tablas separadas según el estado de
// Bloq Num.
const NUMPAD_CODE: Record<string, string> = {
  Numpad0: 'kp_0',
  Numpad1: 'kp_1',
  Numpad2: 'kp_2',
  Numpad3: 'kp_3',
  Numpad4: 'kp_4',
  Numpad5: 'kp_5',
  Numpad6: 'kp_6',
  Numpad7: 'kp_7',
  Numpad8: 'kp_8',
  Numpad9: 'kp_9',
  NumpadEnter: 'kp_enter',
  NumpadAdd: 'kp_plus',
  NumpadSubtract: 'kp_minus',
  NumpadMultiply: 'kp_multiply',
  NumpadDivide: 'kp_divide',
  NumpadDecimal: 'kp_decimal',
}

const NAMED_KEY: Record<string, string> = {
  Escape: 'esc',
  ' ': 'space',
  ArrowUp: 'up',
  ArrowDown: 'down',
  ArrowLeft: 'left',
  ArrowRight: 'right',
  Home: 'home',
  End: 'end',
  PageUp: 'pageup',
  PageDown: 'pagedown',
  Insert: 'insert',
  Delete: 'delete',
  Tab: 'tab',
  Backspace: 'backspace',
  Enter: 'enter',
}

const FUNCTION_KEY_RE = /^F([1-9]|1[0-2])$/

/**
 * Convierte un `KeyboardEvent` en nombre canónico ('w', 'esc', 'kp_1',
 * 'f1'); cadena vacía si no hay mapeo (igual que `qt_key_name`).
 */
export function mapKeyEvent(e: KeyboardEvent): string {
  const numpad = NUMPAD_CODE[e.code]
  if (numpad) return numpad

  const { key } = e
  if (key.length === 1) {
    // Letras/dígitos/símbolos imprimibles: el propio carácter (en
    // minúscula) ya es el nombre canónico, igual que en pynput/Qt.
    return key.toLowerCase()
  }
  if (FUNCTION_KEY_RE.test(key)) return key.toLowerCase()
  return NAMED_KEY[key] ?? ''
}
