# LogicSpace website

This directory is the standalone React + TypeScript website for LogicSpace. It is separate from the Python desktop app. Content describes the **published v3.0.0 source release**, including its limitations.

## Local development

Requires Node.js 24 (see `.node-version`).

```sh
cd website
npm ci
npm run dev
```

Run checks and create a production build:

```sh
npm run typecheck
npm test
npm run build
```

`SITE_URL=https://your-site.example npm run build` generates a sitemap, canonical URL, absolute Open Graph image URL, and `robots.txt` for that origin. Cloudflare Pages supplies `CF_PAGES_URL` automatically. Builds on a preview branch include `noindex, nofollow` metadata and disallow crawling in `robots.txt`.

For production on Pages, the build normalizes a hash-specific `CF_PAGES_URL` to the stable `<project>.pages.dev` hostname. If a custom domain is added later, set `SITE_URL` explicitly to that HTTPS origin.

## Cloudflare Pages Git Integration

Use the official GitHub repository `Kuattt/LogicSpace-` and grant the Cloudflare GitHub app access only to that repository.

| Setting           | Value                                   |
| ----------------- | --------------------------------------- |
| Root directory    | `website`                               |
| Build command     | `npm ci && npm run build`               |
| Output directory  | `dist`                                  |
| Node.js           | `24.22.2` via `.node-version`           |
| Production branch | `main` **after owner review and merge** |

The `website-build` branch is intended for a preview deployment. Do not merge or enable production until the owner reviews the preview. Cloudflare Pages serves the React routes through its single-page application fallback; do not add a root `404.html` without providing an equivalent fallback rule.

When connecting Git before the owner approves production, leave **production deployments disabled** and enable previews only for `website-build`. Keep `main` selected as the future production branch. This avoids an initial production build from a branch that does not yet contain `website/`.

No GitHub or Cloudflare tokens are required in the repository. This site uses no analytics, cookies, registration, or backend. Language and theme preferences are stored locally in the visitor's browser.

## Source of product claims

Release links and archive SHA-256 are in `src/content.ts`. Documentation and product descriptions were checked against the published v3.0.0 tag, release assets, README, changelog, `install.sh`, and screenshots. Update those references only after checking a new published release. The published source ZIP contains no project license; later local licensing drafts are not presented as final terms here.
