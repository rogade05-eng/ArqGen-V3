# Ejemplo de láminas SVG de una vivienda · ilustrativo

[Ver la vista previa de la planta amueblada](vista-previa-A-02.png) · [Descargar el paquete A3 (ZIP)](muestra-vivienda-A3.zip).

El ZIP contiene `A-01-emplazamiento.svg`, `A-02-planta-amueblada.svg`, `A-03-planta-cotas.svg`, `manifest.json`, `origen-v8.json` y advertencias. Las tres hojas se derivan del **mismo** candidato `cand-ab3376d8fef08f3b-22`, generado por el núcleo Rust WASM v8 versionado con `examples/rectangular.json` y las reglas **demo** `knowledge/generic-house.json`. La vista previa PNG es solo una rasterización local de A-02, no otra solución.

**SHA-256 ZIP:** `b74d3549b0125f74f1c1c29184bbe5c25408741ce135d62af8d9bd163a88a7b8`. **SHA-256 WASM preexistente:** `fe95bb201e1bcb92574e09bc196670062fdc75da3b13502f7e2cb56dc6ba0874`. Reproducir (tras `npm ci --prefix web`): `node scripts/generate-sample-sheets.mjs`. Una prueba exige identidad byte a byte entre el ZIP/SVG mostrados y los regenerados. La rasterización opcional usó `resvg` fuera del repositorio; no forma parte del motor.

**No son dibujos de obra:** no hay niveles/alturas, cortes, fachadas, hospital, hotel, norma cubana verificada, sitio legal ni caudal efectivo. Escala SVG nominal ISO A3; imprimir al 100 % y verificarla en cada equipo. El ancho/fondo dibujado y las superficies se refieren solo al croquis validado por reglas ilustrativas.
