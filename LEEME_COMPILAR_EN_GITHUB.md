# ARQ GEN — Compilar automáticamente en GitHub (GitHub Actions)

Este paquete convierte tu repositorio **github.com/rogade05-eng/ArqGen-V3**
en una «fábrica de ejecutables»: cada vez que subas el código (push), GitHub
lo compila en sus servidores y te deja **ARQ_GEN.exe** listo para descargar.
No necesitas Python ni PyInstaller instalados en tu PC: todo ocurre en la
nube de GitHub, en un equipo Windows limpio, siguiendo el mismo pipeline de
siempre (pruebas → PyInstaller → selftest del ejecutable).

---

## 1. Qué hay que copiar (una sola vez)

Después de descomprimir el ZIP verás la carpeta `ARQ_GEN` con TODO el
programa (v3.47.0) más dos cosas nuevas para GitHub:

| Elemento                | Para qué sirve |
|-------------------------|----------------|
| `.github\workflows\compilar.yml` | La receta que GitHub ejecuta para compilar |
| `LEEME_COMPILAR_EN_GITHUB.md`    | Este manual |
| `.gitignore`                     | Evita subir basura (logs, compilaciones locales) |
| `ARQ_GEN.spec`                   | Ficha de compilación que usa PyInstaller |
| `requirements.txt` / `requirements-build.txt` | Dependencias que instala GitHub |

**Pasos en GitHub Desktop:**

1. Abre GitHub Desktop → selecciona el repositorio **ArqGen-V3**.
2. Menú **Repository → Show in Explorer** (se abre la carpeta local del repo).
3. Abre también la carpeta `ARQ_GEN` que salió del ZIP y **copia TODO su
   contenido** (Ctrl+E para seleccionar todo, Ctrl+C) y **pega** (Ctrl+V)
   dentro de la carpeta del repositorio. Windows preguntará qué hacer con
   los archivos repetidos: elige **Reemplazar** («Replace the files in the
   destination»).
   - **IMPORTANTE:** la carpeta `.github` debe copiarse también. En Windows
     es una carpeta normal y visible; si no la ves, activa
     **Vista → Mostrar → Elementos ocultos** y comprueba que se copió.
4. Vuelve a GitHub Desktop. A la izquierda aparecerán cientos de archivos
   nuevos (379 + los nuevos). Escribe en **Summary** por ejemplo:
   `ARQ GEN v3.47.0 completo + compilación automática en GitHub`.
5. Pulsa **Commit to main** y después **Push origin** y espera a que termine.

## 2. Dónde se compila y dónde está el .exe

1. Ve a **github.com/rogade05-eng/ArqGen-V3** y abre la pestaña **Actions**.
   - Si es la primera vez, quizá aparezca un botón verde:
     **«I understand my workflows, go ahead and enable them»** — púlsalo.
2. En la lista verás el run **«Compilar ARQ GEN (Windows)»** que arrancó
   solo con tu push. Ábrelo para ver el progreso paso a paso.
3. La compilación completa tarda normalmente **entre 15 y 40 minutos**
   (la suite de pruebas es la parte más larga; el empaquetado en sí son
   unos minutos). Puedes cerrar la página: sigue corriendo.
4. Cuando el run quede en **verde ✓**, en su página, abajo en la sección
   **Artifacts**, aparece **ARQ_GEN_Windows_x64** — púlsalo para descargar.
5. Descomprime el ZIP descargado: dentro hay una carpeta `ARQ_GEN` con
   **ARQ_GEN.exe**. Doble clic y listo. No requiere instalación ni Python.
   El ejecutable ya viene **verificado**: antes de subirse pasó su selftest
   interno (96 comprobaciones) sobre los recursos y el motor completos.

> El artefacto se conserva **90 días**. Si quieres un enlace permanente,
> haz un push de una etiqueta (ver sección 4) y GitHub crea un **Release**.

## 3. Compilar cuando tú quieras (sin subir código)

En la pestaña **Actions** → «Compilar ARQ GEN (Windows)» → botón
**Run workflow** → rama `main` → **Run workflow**.
Ahí hay una casilla para decidir si esa corrida ejecuta o no la suite de
pruebas (sáltala si solo quieres el .exe rápido).

## 4. Release permanente (opcional)

Si en algún momento quieres una descarga que no caduque nunca, etiqueta
una versión. Con Git desde la carpeta del repo (o desde la pestaña
Releases → «Draft a new release» eligiendo el commit):

```
git tag v3.47.0
git push origin v3.47.0
```

El workflow crea automáticamente un **Release** con el ZIP del ejecutable,
publicado en la pestaña **Releases** del repositorio.

## 5. Qué hace exactamente el workflow

| Paso | Qué hace | Si falla |
|------|----------|----------|
| 1. Checkout | Descarga tu código | — |
| 2. Python 3.13 | Prepara el intérprete con caché | — |
| 3. Dependencias | Instala ezdxf, openpyxl y PyInstaller | Run rojo (reintenta: Re-run) |
| 4. Acelerador Rust (FASE B) | Compila el crate `arqgen_core` con maturin e instálalo — **opcional**: si falla, el run sigue y el exe sale en modo Python puro (todo funciona, sin la aceleración) | Paso amarillo, run verde |
| 5. Suite de pruebas | Las 2.644 pruebas del motor | **No bloquea**: queda marcado en amarillo y el exe se compila igual (el log completo queda en el artefacto `logs_pruebas_ci`) |
| 6. PyInstaller | Empaqueta con `ARQ_GEN.spec` (el espejo exacto del 03_COMPILAR.bat, con la exclusión de bindings Qt que evita el error «multiple Qt bindings») | Run rojo — es el paso raro de fallar |
| 7. Selftest del exe | El propio `ARQ_GEN.exe` ejecuta sus **103 comprobaciones** internas y verifica recursos dentro del bundle (la 98 te dice si el exe lleva el acelerador Rust o va en modo Python; las 101-103 son la FASE C: catálogo/formas especiales/exportación por RPC) | Run rojo: el exe no se considera fiable y NO se sube |
| 8. Artefacto | Sube `ARQ_GEN_Windows_x64.zip` a la página del run | — |

Diseño deliberado: la **puerta de calidad que bloquea es el selftest del
ejecutable** (lo mismo que hace tu 03_COMPILAR.bat local en la etapa 3), no
la suite CI completa, para que un retoque de entorno en la nube nunca te
deje sin .exe.

## 6. Problemas frecuentes

- **«all actions must be pinned to a full-length commit SHA»:** tu
  repositorio (u organización) exige que cada action vaya fijada a un SHA
  de commit completo, no a etiquetas como `@v4`. Desde v3.48.0 los dos
  workflows de ARQ GEN ya van pinned (checkout v4.4.0, setup-python v5.6.0,
  upload-artifact v4.6.2, download-artifact v4.3.0, gh-release v2.6.2);
  si añades actions nuevas, fíjalas igual: copia el SHA de la página del
  release de la action y usa `uses: owner/action@<sha-completo>`.

- **La pestaña Actions no aparece o los runs no arrancan:** los repos
  **públicos** tienen Actions gratis e ilimitado. En los **privados** el
  plan gratuito da 2.000 minutos/mes y los equipos Windows consumen el
  doble de minutos. Para usarlo sin límites, pon el repositorio público
  (Settings → General → Danger Zone → Change visibility).
- **El run quedó verde pero con un paso amarillo:** normal si la suite de
  pruebas tuvo fallos en la nube. El exe está bien (pasó el selftest);
  el detalle está en el artefacto `logs_pruebas_ci`.
- **El paso amarillo del «Acelerador Rust FASE B»:** no es un error. Si el
  toolchain de Rust no cooperó en la nube, el exe se compila igual en modo
  Python puro (el selftest del exe lo declara en el resumen del run).
- **«ARQ_GEN_Windows_x64» no aparece:** solo aparece cuando el run ya
  terminó en verde. Refresca la página.
- **Windows marca el exe como desconocido:** es normal en exes sin
  firma digital; pulsa «Más información → Ejecutar de todas formas».
- **Quiero volver a compilar sin cambiar nada:** pestaña Actions → el run
  → **Re-run all jobs**.
- **No borres ni renombres la carpeta `.github`**: es la que le dice a
  GitHub cómo compilar.

## 7. Notas técnicas

- El runner es `windows-latest` (Windows Server, 64 bits) con Python 3.13,
  la misma versión recomendada por `00_VERIFICAR_ENTORNO.bat`.
- La compilación usa `ARQ_GEN.spec`, el espejo exacto de la etapa 2 del
  `03_COMPILAR.bat` cuya paridad vigila `tests/test_121_dwg_bundle.py`:
  mismos hiddenimports (ui + plugins.builtin), mismos datos (`resources`)
  y la exclusión de PySide6/PyQt5/PyQt6 que evita el aborto de PyInstaller
  por bindings Qt duplicados.
- El ejecutable resultante es idéntico en estructura al de tu PC:
  `dist\ARQ_GEN\ARQ_GEN.exe` en modo onedir con la carpeta `_internal`.
- Cada push a `main` lanza una compilación nueva; el archivo
  `.github/workflows/compilar.yml` se puede ajustar para cambiar ramas,
  tiempos o el nombre del artefacto.
