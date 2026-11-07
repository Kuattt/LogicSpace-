import { strict as assert } from 'node:assert'
import { mkdtemp, mkdir, readFile, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import test from 'node:test'

const script = fileURLToPath(new URL('./postbuild.mjs', import.meta.url))

async function runPostbuild(branch) {
  const folder = await mkdtemp(join(tmpdir(), 'logicspace-site-seo-'))
  await mkdir(join(folder, 'dist'))
  await writeFile(
    join(folder, 'dist', 'index.html'),
    '<html><head><meta property="og:image" content="/images/workspace.png" /></head><body></body></html>',
  )
  const result = spawnSync(process.execPath, [script], {
    cwd: folder,
    env: {
      ...process.env,
      SITE_URL: '',
      CF_PAGES_URL: 'https://abc123.logicspace.pages.dev',
      CF_PAGES_BRANCH: branch,
    },
    encoding: 'utf8',
  })
  assert.equal(result.status, 0, result.stderr)
  const output = {
    html: await readFile(join(folder, 'dist', 'index.html'), 'utf8'),
    sitemap: await readFile(join(folder, 'dist', 'sitemap.xml'), 'utf8'),
    robots: await readFile(join(folder, 'dist', 'robots.txt'), 'utf8'),
  }
  await rm(folder, { recursive: true, force: true })
  return output
}

test('production sitemap and canonical use the stable Pages hostname', async () => {
  const { html, sitemap, robots } = await runPostbuild('main')
  assert.match(html, /canonical" href="https:\/\/logicspace\.pages\.dev\/"/)
  assert.match(html, /content="https:\/\/logicspace\.pages\.dev\/images\/workspace\.png"/)
  assert.match(sitemap, /https:\/\/logicspace\.pages\.dev\/download/)
  assert.match(robots, /Sitemap: https:\/\/logicspace\.pages\.dev\/sitemap\.xml/)
  assert.doesNotMatch(html, /noindex/)
})

test('preview deployments are excluded from crawling', async () => {
  const { html, robots } = await runPostbuild('website-build')
  assert.match(html, /name="robots" content="noindex, nofollow"/)
  assert.match(robots, /Disallow: \//)
})
