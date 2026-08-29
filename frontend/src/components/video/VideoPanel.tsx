import { useState } from 'react'
import { useBusEvent } from '@/hooks/useBusEvent'
import type { StreamState } from '@/lib/types'

const NO_SIGNAL: StreamState = {
  status: 'stopped',
  message: 'Sin señal\n(conéctese una cámara real para ver el stream RTSP)',
}

function videoPort(): string | null {
  return new URLSearchParams(window.location.search).get('videoPort')
}

/**
 * `<img>` apuntando al servidor MJPEG local (gui_web/video_server.py).
 * `multipart/x-mixed-replace` lo decodifica de forma nativa el motor del
 * navegador (WebView2/WebKitGTK) — no hace falta librería ni <canvas>,
 * solo fijar el src una vez y dejar que el propio <img> se repinte con
 * cada parte del multipart.
 *
 * Fuera de "streaming" se desmonta el <img> (en vez de solo ocultarlo):
 * así el navegador cierra la conexión anterior y no se ve un último
 * frame congelado mientras el stream está caído.
 */
export function VideoPanel() {
  const [state, setState] = useState<StreamState>(NO_SIGNAL)
  useBusEvent<StreamState>('gui.streamState', setState)

  const port = videoPort()

  if (state.status !== 'streaming' || !port) {
    return (
      <div className="flex h-full items-center justify-center whitespace-pre-line rounded-md bg-[#15151f] p-6 text-center text-sm text-muted-foreground">
        {state.message || NO_SIGNAL.message}
      </div>
    )
  }

  return (
    <div className="flex h-full items-center justify-center overflow-hidden rounded-md bg-[#15151f]">
      <img
        src={`http://127.0.0.1:${port}/stream`}
        alt="Vista previa de la cámara"
        className="max-h-full max-w-full object-contain"
      />
    </div>
  )
}
