import { defineConfig } from 'astro/config';
import sitemap from '@astrojs/sitemap';
import { PAIRS } from './src/data/site.ts';

// SITE_URL and BASE_PATH come from the environment so the same source builds
// for a project page (/desks/) or a custom domain (/).
const base = () => (process.env.BASE_PATH || '/').replace(/\/?$/, '/');

export default defineConfig({
  output: 'static',
  site: process.env.SITE_URL || 'http://localhost:4321',
  base: process.env.BASE_PATH || '/',
  trailingSlash: 'always',
  // Astro 7 defaults to 'jsx' whitespace rules, which can join inline elements ("EN / ES" -> "EN/ES"); keep v6's lossless compression.
  compressHTML: true,
  integrations: [sitemap({
    filter: (page) => !page.includes('/404'),
    // The Spanish pages have their own slugs (how/ ↔ es/como/), so the pairs come from PAIRS,
    // the same table the pages use for their hreflang links.
    serialize(item) {
      const root = new URL(base(), item.url).href;
      const rel = item.url.slice(root.length);
      const en = Object.entries(PAIRS).find(([e, s]) => e === rel || s === rel);
      if (en) item.links = [{ lang: 'en', url: root + en[0] }, { lang: 'es', url: root + en[1] }, { lang: 'x-default', url: root + en[0] }];
      return item;
    },
  })],
});
