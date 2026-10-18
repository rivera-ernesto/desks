// Fails the build on facts that must hold in the built site. Each check asserts
// something concrete about dist/, because a check that only advises gets skipped.
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';

const dist = process.argv[2] || 'dist';
const walk = (d) => readdirSync(d).flatMap((f) => {
  const p = join(d, f);
  return statSync(p).isDirectory() ? walk(p) : p.endsWith('.html') ? [p] : [];
});
const pages = walk(dist);
const errors = [];

const EXPECTED = ['index.html', 'how/index.html', 'examples/index.html', 'install/index.html', 'about/index.html', 'open/index.html', 'es/abierto/index.html', 'es/index.html', 'es/como/index.html', 'es/ejemplos/index.html', 'es/instalar/index.html', 'es/acerca/index.html', '404.html'];

// Both languages from day one: every page says which language it is in, and each has its pair.
for (const p of pages) {
  const html = readFileSync(p, 'utf8');
  const es = p.includes(join(dist, 'es'));
  if (!html.includes(es ? '<html lang="es">' : '<html lang="en">')) errors.push(`${p}: wrong or missing lang attribute`);
  if (!p.endsWith('404.html') && !html.includes('hreflang=')) errors.push(`${p}: no link to its other-language page`);
}
for (const e of EXPECTED) if (!pages.includes(join(dist, e))) errors.push(`missing page: ${e}`);

// Words from the private setup this was extracted from, and unfinished copy.
const BANNED = [/\{\{/, /\bTODO\b/, /\[PLACEHOLDER\]/i, /lorem ipsum/i, /\bcharla\b/i, /\bPM lane\b/i, /Letra Chica/i, /\bUL(s)?\b/];
for (const p of pages) {
  const html = readFileSync(p, 'utf8');
  for (const b of BANNED) if (b.test(html)) errors.push(`${p}: contains ${b}`);
}

// Search engines and link previews: every page except 404 names its canonical address
// under the real base, both languages and a default, and a 1200×630 image with alt text.
// Nothing links to the host root by mistake: on a project page that is someone else's site.
const site = (process.env.SITE_URL || 'http://localhost:4321').replace(/\/$/, '');
const basePath = (process.env.BASE_PATH || '/').replace(/\/?$/, '/');
const prefix = site + basePath;
for (const p of pages) {
  const html = readFileSync(p, 'utf8');
  const is404 = p.endsWith('404.html');
  const canon = html.match(/<link rel="canonical" href="([^"]+)"/)?.[1];
  if (is404) {
    if (!html.includes('name="robots" content="noindex"')) errors.push(`${p}: 404 page is not noindex`);
    if (canon) errors.push(`${p}: 404 page has a canonical address`);
  } else {
    if (!canon || !canon.startsWith(prefix)) errors.push(`${p}: canonical missing or outside ${prefix}`);
    for (const h of ['en', 'es', 'x-default']) {
      const m = html.match(new RegExp(`hreflang="${h}" href="([^"]+)"`));
      if (!m || !m[1].startsWith(prefix)) errors.push(`${p}: hreflang ${h} missing or outside ${prefix}`);
    }
  }
  const og = html.match(/property="og:image" content="([^"]+)"/)?.[1];
  if (!og || !og.startsWith(prefix)) errors.push(`${p}: og:image missing or outside ${prefix}`);
  if (!html.includes('property="og:image:width" content="1200"') || !html.includes('property="og:image:height" content="630"') || !/property="og:image:alt" content="[^"]+"/.test(html)) errors.push(`${p}: og:image size or alt missing`);
  for (const m of html.matchAll(/(?:href|src)="(\/[^"]*)"/g)) if (!m[1].startsWith(basePath)) errors.push(`${p}: root link ${m[1]} skips the base ${basePath}`);
}
for (const f of ['og.png', 'og-es.png']) {
  const b = readFileSync(join(dist, f));
  if (b.readUInt32BE(16) !== 1200 || b.readUInt32BE(20) !== 630) errors.push(`${f}: not 1200×630`);
}
const robots = readFileSync(join(dist, 'robots.txt'), 'utf8');
if (/^Disallow: \/\s*$/m.test(robots) || !robots.includes(`Sitemap: ${prefix}sitemap-index.xml`)) errors.push('robots.txt blocks the site or does not point at the sitemap');
const sitemap = readdirSync(dist).filter((f) => /^sitemap-\d+\.xml$/.test(f)).map((f) => readFileSync(join(dist, f), 'utf8')).join('');
const locs = [...sitemap.matchAll(/<loc>([^<]+)<\/loc>/g)].map((m) => m[1]);
if (locs.length !== EXPECTED.length - 1 || locs.some((l) => !l.startsWith(prefix) || l.includes('404'))) errors.push(`sitemap: expected ${EXPECTED.length - 1} pages under ${prefix}, found ${locs.length}`);

// The theme choice is stored under the site's own key: every project page on the host shares localStorage.
for (const p of pages) if (/localStorage\.(get|set)Item\('theme'/.test(readFileSync(p, 'utf8'))) errors.push(`${p}: theme key without the site prefix`);

// The install prompt has one source. The README must carry the same text.
const data = readFileSync(new URL('../src/data/site.ts', import.meta.url), 'utf8');
const repo = data.match(/REPO = '([^']+)'/)[1];
const prompt = data.match(/INSTALL_PROMPT =\s*`([^`]+)`/)[1].replace('${REPO}', repo);
const readme = readFileSync(new URL('../../README.md', import.meta.url), 'utf8');
if (!readme.includes(prompt)) errors.push('README.md does not contain the install prompt from src/data/site.ts');
if (!readFileSync(join(dist, 'index.html'), 'utf8').includes(prompt.slice(0, 40))) errors.push('home page does not show the install prompt');

if (errors.length) { console.error('QA FAILED\n  ' + errors.join('\n  ')); process.exit(1); }
console.log(`QA ok: ${pages.length} pages, no banned terms, canonical/hreflang/og under ${prefix}, sitemap and robots, install prompt matches README`);
