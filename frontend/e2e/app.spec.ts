import { test, expect } from '@playwright/test'

test.describe('Landing page', () => {
  test('loads and shows title', async ({ page }) => {
    await page.goto('/')
    await expect(page).toHaveTitle(/IaRadio/)
  })

  test('shows CTA button', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByRole('link', { name: /empezar|crear cuenta/i }).first()).toBeVisible()
  })
})

test.describe('Login page', () => {
  test('shows login form', async ({ page }) => {
    await page.goto('/login')
    await expect(page.getByRole('heading', { name: /iniciar sesión/i })).toBeVisible()
    await expect(page.getByPlaceholder(/correo|email/i)).toBeVisible()
    await expect(page.getByPlaceholder(/contraseña|password/i)).toBeVisible()
  })

  test('shows error on invalid credentials', async ({ page }) => {
    await page.goto('/login')
    await page.getByPlaceholder(/correo|email/i).fill('test@test.com')
    await page.getByPlaceholder(/contraseña|password/i).fill('wrongpass')
    await page.getByRole('button', { name: /entrar|iniciar/i }).click()
    await expect(page.getByText(/error|inválido|incorrecto/i)).toBeVisible({ timeout: 10000 })
  })
})

test.describe('Public pages', () => {
  test('terms page loads', async ({ page }) => {
    await page.goto('/terms')
    await expect(page.locator('h1')).toBeVisible()
  })

  test('privacy page loads', async ({ page }) => {
    await page.goto('/privacy')
    await expect(page.locator('h1')).toBeVisible()
  })

  test('customer stories page loads', async ({ page }) => {
    await page.goto('/customer-stories')
    await expect(page.locator('h1')).toBeVisible()
  })
})

test.describe('Protected routes redirect to login', () => {
  test('/app/dashboard redirects unauthenticated users', async ({ page }) => {
    await page.goto('/app/dashboard')
    await page.waitForURL(/\/login/)
    expect(page.url()).toContain('/login')
  })

  test('/app/campaigns redirects unauthenticated users', async ({ page }) => {
    await page.goto('/app/campaigns')
    await page.waitForURL(/\/login/)
    expect(page.url()).toContain('/login')
  })
})
