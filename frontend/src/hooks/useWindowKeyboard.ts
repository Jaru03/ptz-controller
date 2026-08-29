import { useEffect } from 'react'
import { api } from '@/lib/api'
import { mapKeyEvent } from '@/lib/keymap'

const TEXT_INPUT_TAGS = new Set(['INPUT', 'TEXTAREA', 'SELECT'])

function isTextInputFocused(): boolean {
  const el = document.activeElement
  return el !== null && TEXT_INPUT_TAGS.has(el.tagName)
}

/**
 * Reenvía keydown/keyup a Api.key_down/key_up cuando el backend de
 * teclado en marcha es "window" — equivalente a
 * gui/main_window.py::MainWindow.eventFilter/keyPressEvent/
 * keyReleaseEvent. Se consulta keyboardRequiresWindowEvents() (el
 * controlador real, no settings.keyboard.backend) porque con backend
 * "auto" el valor configurado no dice cuál de los dos arrancó
 * realmente.
 *
 * Ignora teclas mientras el foco está en un campo de texto (mismo
 * criterio que _TEXT_INPUT_WIDGETS en la GUI PySide6) y los keydown
 * repetidos por mantener la tecla pulsada (KeyboardController ya los
 * deduplica en Python, pero evita llamadas de más al bridge).
 */
export function useWindowKeyboard(): void {
  useEffect(() => {
    let active = true
    let cleanup = () => {}

    api.keyboardRequiresWindowEvents().then((required) => {
      if (!required || !active) return

      const onKeyDown = (e: KeyboardEvent) => {
        if (e.repeat || isTextInputFocused()) return
        const name = mapKeyEvent(e)
        if (name) void api.keyDown(name)
      }
      const onKeyUp = (e: KeyboardEvent) => {
        if (isTextInputFocused()) return
        const name = mapKeyEvent(e)
        if (name) void api.keyUp(name)
      }

      document.addEventListener('keydown', onKeyDown)
      document.addEventListener('keyup', onKeyUp)
      cleanup = () => {
        document.removeEventListener('keydown', onKeyDown)
        document.removeEventListener('keyup', onKeyUp)
      }
    })

    return () => {
      active = false
      cleanup()
    }
  }, [])
}
