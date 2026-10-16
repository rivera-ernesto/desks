// One source for everything that is repeated across pages and checked by
// scripts/qa-check.mjs against the README.
export const REPO = 'https://github.com/rivera-ernesto/desks';
export const VERSION = 'v0.1.7';

export const INSTALL_PROMPT =
  `Set up Desks in this folder. Get version v0.1.7 of ${REPO}, read its INSTALL.md and follow it. First show me the list of files you will create or change, and wait for my yes. Keep everything I already have.`;

export const INSTALL_PROMPT_ES =
  `Instala Desks en esta carpeta. Obtén la versión v0.1.7 de ${REPO}, lee su INSTALL.md y síguelo. Primero muéstrame la lista de archivos que vas a crear o cambiar, y espera mi sí. Conserva todo lo que ya tengo. Respóndeme en español.`;

// Where "work with me" points. A repository link until the author chooses a contact channel.
export const CONTACT = 'https://github.com/rivera-ernesto';

export const NAV_ES = [
  { href: 'es/como/', label: 'Cómo funciona' },
  { href: 'es/ejemplos/', label: 'Ejemplos' },
  { href: 'es/instalar/', label: 'Instalar' },
  { href: 'es/abierto/', label: 'A la vista' },
  { href: 'es/acerca/', label: 'Acerca' },
];

// Each page and its counterpart in the other language.
export const PAIRS: Record<string, string> = {
  '': 'es/', 'how/': 'es/como/', 'examples/': 'es/ejemplos/', 'install/': 'es/instalar/', 'open/': 'es/abierto/', 'about/': 'es/acerca/',
};

export const NAV = [
  { href: 'how/', label: 'How it works' },
  { href: 'examples/', label: 'Examples' },
  { href: 'install/', label: 'Install' },
  { href: 'open/', label: 'In the open' },
  { href: 'about/', label: 'About' },
];
