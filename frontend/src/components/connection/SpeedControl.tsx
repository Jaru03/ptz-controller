import { useEffect, useState } from 'react'
import { Slider } from '@/components/ui/slider'
import { useBusEvent } from '@/hooks/useBusEvent'
import { api } from '@/lib/api'

interface SetSpeedCommand {
  speed: number
}

/**
 * Control de velocidad global. Igual que el slider de
 * gui/main_window.py: se inicializa desde settings.movement.speed y a
 * partir de ahí sigue los eventos "command.setSpeed" (también los
 * emitidos por el propio joystick o por esta misma llamada a
 * api.setSpeed, que hace el mismo viaje de ida y vuelta por el bus).
 */
export function SpeedControl() {
  const [speed, setSpeed] = useState(0.5)

  useEffect(() => {
    api.getSettings().then((settings) => setSpeed(settings.movement.speed))
  }, [])

  useBusEvent<SetSpeedCommand>('command.setSpeed', (cmd) => setSpeed(cmd.speed))

  const percent = Math.round(speed * 100)

  return (
    <div className="space-y-1.5">
      <div className="flex justify-between text-sm">
        <span>Velocidad</span>
        <span className="text-muted-foreground">{percent}%</span>
      </div>
      <Slider
        value={[percent]}
        max={100}
        step={1}
        onValueChange={([value]) => {
          const next = value / 100
          setSpeed(next)
          void api.setSpeed(next)
        }}
      />
    </div>
  )
}
