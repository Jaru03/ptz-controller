import { useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { ConnectionScreen } from '@/pages/ConnectionScreen'

type View = 'connection' | 'main'

/**
 * Ventana única con cambio de vista en el lado cliente (en vez de un
 * segundo webview.create_window): evita duplicar el bridge/EventBridge y
 * coincide con el flujo actual (ConnectionDialog -> MainWindow en el
 * mismo proceso). MainScreen llega en la Fase 2.
 */
function App() {
  const [view, setView] = useState<View>('connection')

  return (
    <AnimatePresence mode="wait">
      {view === 'connection' ? (
        <motion.div key="connection" exit={{ opacity: 0 }}>
          <ConnectionScreen onConnected={() => setView('main')} />
        </motion.div>
      ) : (
        <motion.div
          key="main"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="flex min-h-svh items-center justify-center bg-background p-6 text-muted-foreground"
        >
          Conectado — la pantalla principal llega en la Fase 2.
        </motion.div>
      )}
    </AnimatePresence>
  )
}

export default App
