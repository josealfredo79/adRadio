import { useCopilot } from '@/contexts/CopilotContext'
import PageBuilderModal from '@/components/PageBuilderModal'

// Abre el armador de página desde cualquier pantalla (lo pide el asistente).
export default function PageBuilderHost() {
  const { pageBuilderOpen, setPageBuilderOpen } = useCopilot()
  return pageBuilderOpen ? <PageBuilderModal onClose={() => setPageBuilderOpen(false)} /> : null
}
