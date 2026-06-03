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
    // Wait for auth refresh to complete (may timeout if no backend)
    await expect(page.getByRole('heading', { name: /iniciar sesión/i })).toBeVisible({ timeout: 15000 })
    await expect(page.locator('input[type="email"]')).toBeVisible()
    await expect(page.locator('input[type="password"]')).toBeVisible()
  })

  test('shows error on invalid credentials', async ({ page }) => {
    await page.goto('/login')
    await expect(page.locator('input[type="email"]')).toBeVisible({ timeout: 15000 })
    await page.locator('input[type="email"]').fill('test@test.com')
    await page.locator('input[type="password"]').fill('wrongpass')
    await page.getByRole('button', { name: /entrar|iniciar/i }).click()
    await expect(page.getByText(/error|inválido|incorrecto/i)).toBeVisible({ timeout: 20000 })
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
    // PrivateRoute redirects to /login after auth refresh fails
    await page.waitForURL(/\/login/, { timeout: 20000 })
    expect(page.url()).toContain('/login')
  })

  test('/app/campaigns redirects unauthenticated users', async ({ page }) => {
    await page.goto('/app/campaigns')
    await page.waitForURL(/\/login/, { timeout: 20000 })
    expect(page.url()).toContain('/login')
  })
})
