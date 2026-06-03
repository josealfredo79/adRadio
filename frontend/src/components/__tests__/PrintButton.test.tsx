import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import PrintButton from '../PrintButton'

describe('PrintButton', () => {
  it('renders default label', () => {
    render(<PrintButton />)
    expect(screen.getByText('Imprimir / PDF')).toBeInTheDocument()
  })

  it('renders custom label', () => {
    render(<PrintButton label="Descargar PDF" />)
    expect(screen.getByText('Descargar PDF')).toBeInTheDocument()
  })

  it('calls window.print on click', () => {
    const printSpy = vi.spyOn(window, 'print').mockImplementation(() => {})
    render(<PrintButton />)
    fireEvent.click(screen.getByRole('button'))
    expect(printSpy).toHaveBeenCalledTimes(1)
    printSpy.mockRestore()
  })

  it('applies custom className', () => {
    render(<PrintButton className="extra-class" />)
    expect(screen.getByRole('button').className).toContain('extra-class')
  })
})
