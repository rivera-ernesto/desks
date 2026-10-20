// Makes the share images (Open Graph), 1200×630 PNG, one per language, from the
// site's own colours and favicon mark. Run again after changing the name or tagline:
//   node scripts/make-og.mjs
import sharp from 'sharp';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const pub = join(dirname(fileURLToPath(import.meta.url)), '..', 'public');
const esc = (s) => s.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);
const images = [
  { file: 'og.png', lines: ['A way of working for Claude Code.', 'Sorted by topic, reviewed, closed in writing.'] },
  { file: 'og-es.png', lines: ['Una forma de trabajar con Claude Code.', 'Por temas, revisado, con un cierre escrito.'] },
];
for (const { file, lines } of images) {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630">
<rect width="1200" height="630" fill="#fbfaf7"/>
<rect x="0" y="590" width="1200" height="40" fill="#2f5d50"/>
<g transform="translate(110 150) scale(6.5)"><rect width="32" height="32" rx="7" fill="#2f5d50"/><rect x="6" y="11" width="20" height="3" rx="1.5" fill="#fff"/><rect x="8" y="14" width="3" height="9" fill="#fff"/><rect x="21" y="14" width="3" height="9" fill="#fff"/></g>
<text x="380" y="290" font-family="Helvetica, Arial, sans-serif" font-size="120" font-weight="700" fill="#1d1c1a" letter-spacing="-2">Desks</text>
<text x="384" y="360" font-family="Helvetica, Arial, sans-serif" font-size="38" fill="#1d1c1a">${esc(lines[0])}</text>
<text x="384" y="412" font-family="Helvetica, Arial, sans-serif" font-size="32" fill="#625f58">${esc(lines[1])}</text>
<text x="384" y="520" font-family="ui-monospace, Menlo, monospace" font-size="26" fill="#2f5d50">github.com/rivera-ernesto/desks</text>
</svg>`;
  await sharp(Buffer.from(svg)).png({ compressionLevel: 9, palette: true }).toFile(join(pub, file));
  console.log(`share image: public/${file}`);
}
