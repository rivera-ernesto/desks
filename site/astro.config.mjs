import { defineConfig } from 'astro/config';

// SITE_URL and BASE_PATH come from the environment so the same source builds
// for a project page (/desk) or a custom domain (/).
export default defineConfig({
  output: 'static',
  site: process.env.SITE_URL || 'http://localhost:4321',
  base: process.env.BASE_PATH || '/',
  trailingSlash: 'always',
});
