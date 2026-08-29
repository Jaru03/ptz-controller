import { useEffect } from 'react'
import { bridge } from '@/lib/bridge'

/** Se suscribe a un topic del bus (ver gui_web/bridge.py) mientras el componente está montado. */
export function useBusEvent<T = unknown>(topic: string, handler: (payload: T) => void): void {
  useEffect(() => bridge.on(topic, handler as (payload: unknown) => void), [topic, handler])
}
