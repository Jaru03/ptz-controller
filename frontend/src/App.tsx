import { useState } from 'react'
import { motion } from 'motion/react'
import { ConnectionScreen } from '@/pages/ConnectionScreen'
import { MainScreen } from '@/pages/MainScreen'

type View = 'connection' | 'main'

/**
 * Ventana única con cambio de vista en el lado cliente (en vez de un
 * segundo webview.create_window): evita duplicar el bridge/EventBridge y
 * coincide con el flujo actual (ConnectionDialog -> MainWindow en el
 * mismo proceso).
 *
 * Sin AnimatePresence: se probó con mode="wait" (fundido de salida de la
 * vista anterior antes de montar la siguiente) y en pruebas automatizadas
 * de UI se quedaba bloqueado indefinidamente esperando a que la
 * animación de salida completara — probablemente por el throttling de
 * requestAnimationFrame que aplican los navegadores a pestañas en según
 * plano/sin foco. Bloquear el montaje de la siguiente vista detrás de
 * una animación de salida es muy arriesgado para una transición crítica
 * (si no completa, el usuario se queda atascado sin forma de continuar).
 * Cada vista monta al instante (React) y solo el fundido de *entrada* es
 * cosa de Motion — eso nunca bloquea nada, porque el montaje ya ocurrió.
 */
function App() {
  const [view, setView] = useState<View>('connection')

  return view === 'connection' ? (
    <motion.div key="connection" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.25 }}>
      <ConnectionScreen onConnected={() => setView('main')} />
    </motion.div>
  ) : (
    <motion.div key="main" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.25 }}>
      <MainScreen />
    </motion.div>
  )
}

export default App
