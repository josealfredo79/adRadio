import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import FollowupSettingsCard from '@/components/FollowupSettingsCard'
import api from '@/lib/api'

const setUser = vi.fn()
let followup: boolean | undefined = true
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({ user: { followup_enabled: followup }, setUser }),
}))

function renderCard() {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <FollowupSettingsCard />
    </QueryClientProvider>,
  )
}

describe('FollowupSettingsCard', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('viene encendido y al apagarlo guarda followup_enabled=false', async () => {
    followup = true
    const patch = vi.spyOn(api, 'patch').mockResolvedValue({ data: { followup_enabled: false } })
    renderCard()
    const box = screen.getByRole('checkbox', { name: /seguimiento a los interesados/i }) as HTMLInputElement
    expect(box.checked).toBe(true)
    fireEvent.click(box)
    await waitFor(() => expect(patch).toHaveBeenCalledWith('/me', { followup_enabled: false }))
  })

  it('una cuenta sin el campo todavía lo ve encendido', () => {
    followup = undefined
    renderCard()
    expect((screen.getByRole('checkbox') as HTMLInputElement).checked).toBe(true)
  })
})
