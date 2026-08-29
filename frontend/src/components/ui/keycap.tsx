/**
 * Insignia con aspecto de tecla física (borde + sombra inferior),
 * reutilizada para mostrar valores cortos "de identificador": teclas en
 * ControlsPanel.tsx y el token de preset en PresetsPanel.tsx.
 */
export function KeyCap({ children, small }: { children: React.ReactNode; small?: boolean }) {
  return (
    <span
      className={`inline-flex shrink-0 items-center justify-center rounded-md border bg-background font-mono font-medium shadow-[0_2px_0_0] shadow-border ${
        small ? 'h-6 min-w-6 px-1.5 text-xs' : 'h-9 min-w-9 px-2 text-sm'
      }`}
    >
      {children}
    </span>
  )
}

/** Píldora que agrupa un KeyCap con su descripción (p. ej. una tecla + "preset 1"). */
export function Chip({ children }: { children: React.ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border bg-background py-1 pr-3 pl-1 text-sm">
      {children}
    </span>
  )
}
