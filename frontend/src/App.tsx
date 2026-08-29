import { motion } from 'motion/react'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'

/**
 * Página de prueba de la Fase 0: solo confirma que Vite + React +
 * Tailwind + shadcn/ui + Motion cargan correctamente dentro de pywebview
 * (vía file://) y en el ejecutable empaquetado con PyInstaller. Se
 * sustituye por ConnectionScreen/MainScreen en las fases siguientes.
 */
function App() {
  return (
    <div className="flex min-h-svh items-center justify-center bg-background p-6">
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35, ease: 'easeOut' }}
      >
        <Card className="w-96">
          <CardHeader>
            <CardTitle>Controlador PTZ</CardTitle>
            <CardDescription>
              Fase 0: scaffold de frontend funcionando dentro de pywebview.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Button>Todo listo</Button>
          </CardContent>
        </Card>
      </motion.div>
    </div>
  )
}

export default App
