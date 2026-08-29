import { useEffect, useState } from 'react'

/** True cuando `window.pywebview.api` ya está disponible. */
export function usePywebviewReady(): boolean {
  const [readyState, setReadyState] = useState(() => Boolean(window.pywebview))

  useEffect(() => {
    if (readyState) return
    const onReady = () => setReadyState(true)
    window.addEventListener('pywebviewready', onReady, { once: true })
    return () => window.removeEventListener('pywebviewready', onReady)
  }, [readyState])

  return readyState
}
