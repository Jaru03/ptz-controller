/**
 * Receptor de eventos Python -> JS. Equivalente a QtEventBridge
 * (gui/main_window.py): gui_web/bridge.py llama a
 * `window.__ptzBridge.dispatch(topic, payload)` vía `evaluate_js` desde
 * hilos en segundo plano.
 *
 * Se cuelga en `window.__ptzBridge` (no un singleton de módulo) a
 * propósito: `evaluate_js` inyecta la llamada contra el scope global de
 * la página ya cargada, así que el objetivo tiene que ser un nombre
 * global estable, sin depender de cómo Vite renombre/trocee el módulo en
 * el build de producción.
 */

export type BusHandler = (payload: unknown) => void

export class BusBridge {
  private handlers = new Map<string, Set<BusHandler>>()

  /** Llamado desde Python (gui_web/bridge.py) con cada evento del bus. */
  dispatch(topic: string, payload: unknown): void {
    this.handlers.get(topic)?.forEach((handler) => handler(payload))
  }

  /** Se suscribe a un topic; devuelve la función para desuscribirse. */
  on(topic: string, handler: BusHandler): () => void {
    let set = this.handlers.get(topic)
    if (!set) {
      set = new Set()
      this.handlers.set(topic, set)
    }
    set.add(handler)
    return () => set!.delete(handler)
  }
}

window.__ptzBridge = window.__ptzBridge ?? new BusBridge()

export const bridge = window.__ptzBridge
