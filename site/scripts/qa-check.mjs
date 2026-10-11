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

const EXPECTED = ['index.html', 'how/index.html', 'examples/index.html', 'install/index.html', 'about/index.html', 'es/index.html', 'es/como/index.html', 'es/ejemplos/index.html', 'es/instalar/index.html', 'es/acerca/index.html', '404.html'];

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

// The install prompt has one source. The README must carry the same text.
const data = readFileSync(new URL('../src/data/site.ts', import.meta.url), 'utf8');
const repo = data.match(/REPO = '([^']+)'/)[1];
const prompt = data.match(/INSTALL_PROMPT =\s*`([^`]+)`/)[1].replace('${REPO}', repo);
const readme = readFileSync(new URL('../../README.md', import.meta.url), 'utf8');
if (!readme.includes(prompt)) errors.push('README.md does not contain the install prompt from src/data/site.ts');
if (!readFileSync(join(dist, 'index.html'), 'utf8').includes(prompt.slice(0, 40))) errors.push('home page does not show the install prompt');

if (errors.length) { console.error('QA FAILED\n  ' + errors.join('\n  ')); process.exit(1); }
console.log(`QA ok: ${pages.length} pages, no banned terms, install prompt matches README`);
