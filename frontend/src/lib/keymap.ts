/**
 * Traducción de nombres canónicos de tecla ('w', 'space', 'kp_1'...) a
 * etiquetas legibles ('W', 'Espacio', 'Num 1'...). Port de
 * gui/controls_widget.py::_key_label — usado por ControlsPanel.tsx.
 *
 * El mapeo inverso (KeyboardEvent -> nombre canónico, equivalente a
 * controllers/keyboard_controller.py::qt_key_name) llega en la Fase 6,
 * cuando el backend "window" necesite capturar teclas desde el
 * frontend.
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
