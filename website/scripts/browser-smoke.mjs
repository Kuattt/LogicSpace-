import assert from 'node:assert/strict'
import { chromium } from 'playwright-core'

const base = process.env.PREVIEW_URL || 'http://127.0.0.1:4173'
const routes = [
  '/',
  '/features',
  '/download',
  '/install',
  '/docs',
  '/docs/getting-started',
  '/docs/interface',
  '/docs/circuit-editor',
  '/docs/simulator',
  '/docs/components',
  '/docs/cpu-assembly',
  '/docs/hdl',
  '/docs/debugger',
  '/docs/fpga',
  '/docs/faq',
  '/docs/troubleshooting',
  '/releases',
  '/about',
]
const browser = await chromium.launch({
  executablePath: process.env.CHROME_BIN || '/usr/bin/google-chrome',
  headless: true,
  args: ['--no-sandbox'],
})
const errors = []
try {
  const page = await browser.newPage({
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 1,
  })
  page.on('pageerror', (error) => errors.push(error.message))
  page.on('console', (message) => {
    if (message.type() === 'error') errors.push(message.text())
  })
  const discovered = new Set()
  for (const path of routes) {
    const response = await page.goto(base + path)
    assert.equal(response.status(), 200, `HTTP ${path}`)
    assert.ok(await page.locator('h1').first().isVisible(), `heading ${path}`)
    assert.ok((await page.title()).includes('LogicSpace'), `title ${path}`)
    for (const image of await page.locator('img').all()) await image.scrollIntoViewIfNeeded()
    await page.waitForFunction(() =>
      [...document.images].every((img) => img.complete && img.naturalWidth > 0),
    )
    for (const link of await page.locator('a[href^="/"]').all()) {
      discovered.add(await link.getAttribute('href'))
    }
  }
  for (const href of discovered) assert.ok(routes.includes(href), `internal link ${href}`)

  await page.goto(base + '/')
  for (const image of await page.locator('img').all()) await image.scrollIntoViewIfNeeded()
  await page.waitForFunction(() =>
    [...document.images].every((img) => img.complete && img.naturalWidth > 0),
  )
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }))
  await page.waitForFunction(() => window.scrollY === 0)
  await page.screenshot({ path: '/tmp/logicspace-site-desktop.png', fullPage: true })
  assert.equal(
    await page
      .locator('.demo-output strong')
      .allTextContents()
      .then((values) => values.join('')),
    '10',
  )
  await page.getByRole('button', { name: 'Toggle input A' }).click()
  assert.equal(
    await page
      .locator('.demo-output strong')
      .allTextContents()
      .then((values) => values.join('')),
    '01',
  )
  await page.getByRole('button', { name: 'Toggle input B' }).click()
  assert.equal(
    await page
      .locator('.demo-output strong')
      .allTextContents()
      .then((values) => values.join('')),
    '10',
  )

  await page.getByRole('button', { name: 'Switch to light theme' }).click()
  assert.equal(await page.locator('html').getAttribute('data-theme'), 'light')
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }))
  await page.waitForFunction(() => window.scrollY === 0)
  await page.waitForTimeout(250)
  await page.screenshot({ path: '/tmp/logicspace-site-light.png', fullPage: false })
  await page.getByRole('button', { name: 'Switch to Russian' }).click()
  assert.equal(await page.locator('html').getAttribute('lang'), 'ru')
  assert.ok((await page.locator('h1').textContent()).includes('Собери схему'))
  await page.goto(base + '/docs')
  await page.getByRole('searchbox').fill('триггер')
  assert.ok((await page.locator('.doc-list-item').count()) > 0)
  await page.getByRole('searchbox').fill('no-such-topic-123')
  assert.ok(await page.getByText('Ничего не найдено').isVisible())
  await page.goto(base + '/not-a-real-route')
  assert.ok((await page.locator('h1').textContent()).includes('подключён'))

  const mobile = await browser.newPage({
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 1,
    isMobile: true,
    hasTouch: true,
  })
  mobile.on('pageerror', (error) => errors.push(error.message))
  mobile.on('console', (message) => {
    if (message.type() === 'error') errors.push(message.text())
  })
  await mobile.goto(base + '/')
  for (const image of await mobile.locator('img').all()) await image.scrollIntoViewIfNeeded()
  await mobile.waitForFunction(() =>
    [...document.images].every((img) => img.complete && img.naturalWidth > 0),
  )
  await mobile.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }))
  await mobile.waitForFunction(() => window.scrollY === 0)
  await mobile.screenshot({ path: '/tmp/logicspace-site-mobile.png', fullPage: true })
  assert.ok(await mobile.getByRole('button', { name: 'Open menu' }).isVisible())
  await mobile.getByRole('button', { name: 'Open menu' }).click()
  await mobile
    .getByRole('navigation', { name: 'Main navigation' })
    .getByRole('link', { name: 'Features' })
    .click()
  assert.ok(mobile.url().endsWith('/features'))
  for (const viewport of [320, 390, 768]) {
    await mobile.setViewportSize({ width: viewport, height: 844 })
    for (const path of ['/', '/features', '/download', '/docs', '/about']) {
      await mobile.goto(base + path)
      const width = await mobile.evaluate(() => ({
        scroll: document.documentElement.scrollWidth,
        viewport: window.innerWidth,
      }))
      assert.ok(
        width.scroll <= width.viewport + 3,
        `horizontal overflow ${path} at ${viewport}: ${JSON.stringify(width)}`,
      )
    }
  }
  assert.deepEqual(errors, [], 'browser JS errors')
  console.log(
    'Browser smoke passed: 18 routes, internal links, images, circuit toggle, themes, RU search, 404, mobile navigation and widths 320/390/768.',
  )
} finally {
  await browser.close()
}
