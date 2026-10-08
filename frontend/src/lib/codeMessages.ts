import axios from 'axios'
import { getApiError } from '@/lib/api'

/** Error al verificar el código: si no es el correcto (400), qué hacer. */
export function verifyError(err: unknown): string {
  if (axios.isAxiosError(err) && err.response?.status === 400) {
    return 'Ese código no es. Usa el último que te llegó por WhatsApp.'
  }
  return getApiError(err, 'No se pudo verificar el código')
}
