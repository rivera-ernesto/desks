# Desks: inicio rápido

Desk es una forma de trabajar con Claude Code: un tema por sesión, respuestas revisadas por
modelos de otras empresas antes de que las leas, y un cierre escrito para retomar después sin
volver a explicar nada.

Sirve para trabajo real que no es código: vender algo, planificar, redactar, investigar una
decisión, llevar un proyecto pequeño. Necesitas un plan pago de Claude y Claude Code (la pestaña
Code de la app de escritorio, o la terminal).

## 1) Instalar (dos minutos)

Abre con Claude Code la carpeta donde quieres trabajar. Puede ser una carpeta que ya usas: Desk no
reemplaza nada de lo que tengas. Pega esto:

```text
Instala Desks en esta carpeta. Obtén la versión v0.1.0 de https://github.com/rivera-ernesto/desks, lee su INSTALL.md y síguelo. Primero muéstrame la lista de archivos que vas a crear o cambiar, y espera mi sí. Conserva todo lo que ya tengo. Respóndeme en español.
```

Antes de copiar nada te muestra la lista de archivos y espera tu sí. El archivo que sigue,
[INSTALL.md](../../INSTALL.md), tiene unas cien líneas y solo copia archivos: léelo si quieres
saber qué hace.

Al terminar te dirá qué archivos creó. Abre una **sesión nueva** en la misma carpeta.

## 2) Tu primer Desk

Escribe, con un tema real que tengas pendiente:

```text
desk vender-camara
```

Claude crea `desks/vender-camara/`, anota el objetivo y empieza. Trabaja normal. Cuando te dé una
recomendación, mira la última línea de la respuesta: dice cómo fue revisada.

## 3) Activar la revisión con otros modelos (tres minutos, gratis)

```text
desk setup
```

Te guía para crear una clave gratuita de OpenRouter. La clave no se pega en el chat: se guarda con
un comando en tu equipo. Desde ahí, cada recomendación importante pasa por modelos de otras
empresas, y Claude tiene que responder a sus objeciones antes de contestarte.

Qué sale de tu equipo: solo un archivo con la pregunta y la propuesta, sin nombres ni contactos.
El script se niega a enviar correos, teléfonos, claves o cualquier palabra de tu lista privada.

## 4) Cerrar y retomar

```text
desk close
```

Deja escrito dónde quedó todo. Otro día, en una sesión nueva: `desk vender-camara`, y sigue desde
ahí. Cuando la sesión se alarga, Claude mismo propone cerrar: las sesiones largas gastan más.

## Qué significan las etiquetas

| Etiqueta | Significa |
|---|---|
| `[converged]` | Varios modelos de otras empresas opinaron y cada objeción fue atendida |
| `[thin]` | Solo uno respondió |
| `[same-vendor]` | Revisó otro Claude, no otra empresa. Detecta descuidos, no puntos ciegos |
| `[unreviewed]` | No hubo revisión |
| `[quick]` | Pediste saltarla |

## Lo que Claude no hace sin tu palabra

Gastar dinero, publicar algo, escribirle a alguien, tocar contraseñas o ajustes, borrar algo. En
tus cuentas abiertas solo lee, salvo que le pidas otra cosa en esa sesión.

## Si ya tienes tu propia forma de trabajar

```text
desk adopt
```

Revisa tus reglas, agentes, plugins y herramientas conectadas, y propone cómo acomodarse a ellas:
usar tus carpetas de proyectos, tus propios agentes, y cualquier otra IA que ya pagues como
revisor adicional.

## Qué contar después de probarlo

- El primer momento en que algo no se entendió.
- Una revisión que mejoró una respuesta, o una que fue puro ruido.
- Algo que Desk hizo sin que se lo pidieras.
- Si abriste un segundo Desk por tu cuenta.
