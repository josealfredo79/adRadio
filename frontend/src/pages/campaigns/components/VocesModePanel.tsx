interface VocesModePanelProps {
  vocesCollectionPrompt: string
  onPromptChange: (val: string) => void
}

export function VocesModePanel({
  vocesCollectionPrompt,
  onPromptChange,
}: VocesModePanelProps) {
  return (
    <div>
      <label className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-300">
        📝 Solicitud para tus clientes
      </label>
      <textarea
        rows={2}
        placeholder="Ej: Mándanos un audio de 10 segundos diciendo cuál es tu platillo favorito 🎙️"
        value={vocesCollectionPrompt}
        onChange={(e) => onPromptChange(e.target.value)}
        className="w-full rounded-lg border border-border bg-background text-foreground px-3.5 py-2.5 text-sm focus:border-brand-500 focus:outline-none resize-none"
      />
      <p className="mt-1 text-xs text-purple-700 dark:text-purple-300 bg-purple-50 dark:bg-purple-950/30 rounded-lg px-3 py-2">
        🎤 Tus contactos recibirán este mensaje y podrán responder con audios. La IA transcribirá sus historias y después podrás generar una cápsula narrativa con ellas.
      </p>
    </div>
  )
}
