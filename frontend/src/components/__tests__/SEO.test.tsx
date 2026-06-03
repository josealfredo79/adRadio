import { render, waitFor } from '@testing-library/react'
import { HelmetProvider } from 'react-helmet-async'
import { describe, it, expect } from 'vitest'
import SEO from '../SEO'

function renderSEO(props: Parameters<typeof SEO>[0]) {
  return render(
    <HelmetProvider>
      <SEO {...props} />
    </HelmetProvider>,
  )
}

describe('SEO', () => {
  it('sets default title', async () => {
    renderSEO({})
    await waitFor(() => {
      expect(document.title).toContain('IaRadio')
    })
  })

  it('sets custom title with suffix', async () => {
    renderSEO({ title: 'Planes' })
    await waitFor(() => {
      expect(document.title).toBe('Planes | IaRadio')
    })
  })

  it('sets description meta', async () => {
    renderSEO({ description: 'Test description' })
    await waitFor(() => {
      const meta = document.querySelector('meta[name="description"]')
      expect(meta).toHaveAttribute('content', 'Test description')
    })
  })

  it('adds noindex when noIndex is true', async () => {
    renderSEO({ noIndex: true })
    await waitFor(() => {
      const robots = document.querySelector('meta[name="robots"]')
      expect(robots).toHaveAttribute('content', 'noindex, nofollow')
    })
  })

  it('adds canonical link', async () => {
    renderSEO({ canonical: 'https://example.com/page' })
    await waitFor(() => {
      const link = document.querySelector('link[rel="canonical"]')
      expect(link).toHaveAttribute('href', 'https://example.com/page')
    })
  })

  it('sets OG title and description', async () => {
    renderSEO({ ogTitle: 'OG Test', ogDescription: 'OG desc' })
    await waitFor(() => {
      const ogTitle = document.querySelector('meta[property="og:title"]')
      expect(ogTitle).toHaveAttribute('content', 'OG Test')
    })
    await waitFor(() => {
      const ogDesc = document.querySelector('meta[property="og:description"]')
      expect(ogDesc).toHaveAttribute('content', 'OG desc')
    })
  })
})
