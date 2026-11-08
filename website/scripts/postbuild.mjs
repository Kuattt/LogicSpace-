import { readFile, writeFile } from 'node:fs/promises'
import { join } from 'node:path'

const value = process.env.SITE_URL || process.env.CF_PAGES_URL
if (!value) {
  console.log(
    'SITE_URL/CF_PAGES_URL unavailable: sitemap and canonical URL will be added by the Pages build.',
  )
  process.exit(0)
}

const parsed = new URL(value)
if (
  parsed.protocol !== 'https:' ||
  parsed.username ||
  parsed.password ||
  parsed.search ||
  parsed.hash
) {
  throw new Error('SITE_URL/CF_PAGES_URL must be a clean HTTPS origin')
}
const isPreview = Boolean(process.env.CF_PAGES_BRANCH && process.env.CF_PAGES_BRANCH !== 'main')
let origin = parsed.origin
// CF_PAGES_URL can point at a hash-specific deployment. Use the stable Pages
// project hostname for production SEO unless an explicit SITE_URL was supplied.
if (!process.env.SITE_URL && process.env.CF_PAGES_BRANCH === 'main') {
  const labels = parsed.hostname.split('.')
  if (labels.length === 4 && labels.slice(-2).join('.') === 'pages.dev') {
    origin = `https://${labels.slice(1).join('.')}`
  }
}
const paths = [
  '/',
  '/features',
  '/download',
  '/install',
  '/docs',
  '/docs/getting-started',
  '/docs/linux-guide',
  '/docs/windows-guide',
  '/docs/interface',
  '/docs/circuit-editor',
  '/docs/simulator',
  '/docs/components',
  '/docs/cpu-assembly',
  '/docs/hdl',
  '/docs/debugger',
  '/docs/fpga',
  '/docs/faq',
  '/docs/known-limitations',
  '/docs/troubleshooting',
  '/releases',
  '/about',
]
const escapeXml = (text) => text.replaceAll('&', '&amp;').replaceAll('<', '&lt;')
const sitemap = `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${paths.map((path) => `  <url><loc>${escapeXml(origin + path)}</loc></url>`).join('\n')}\n</urlset>\n`
await writeFile(join('dist', 'sitemap.xml'), sitemap)
await writeFile(
  join('dist', 'robots.txt'),
  isPreview
    ? 'User-agent: *\nDisallow: /\n'
    : `User-agent: *\nAllow: /\nSitemap: ${origin}/sitemap.xml\n`,
)
const indexPath = join('dist', 'index.html')
let html = await readFile(indexPath, 'utf8')
html = html.replace('content="/images/workspace.png"', `content="${origin}/images/workspace.png"`)
html = html.replace(
  '</head>',
  `  <link rel="canonical" href="${origin}/" />\n    <meta property="og:url" content="${origin}/" />\n  </head>`,
)
if (isPreview)
  html = html.replace('</head>', '  <meta name="robots" content="noindex, nofollow" />\n  </head>')
await writeFile(indexPath, html)
console.log(`Generated sitemap and canonical URL for ${origin}`)
