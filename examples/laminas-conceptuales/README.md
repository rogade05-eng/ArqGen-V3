# Ejemplo v2: cuatro láminas SVG de una vivienda · ilustrativo

[Vista A-01 · sitio](vista-previa-A-01.png) · [Vista A-02 · planta](vista-previa-A-02.png) · [Vista A-04 · perímetro y vanos](vista-previa-A-04.png) · **[Descargar el paquete A3 (ZIP)](muestra-vivienda-A3.zip)** · [Ver geometría de nivel 0 en planta](nivel-0-2d.json).

El ZIP contiene `A-01-emplazamiento.svg`, `A-02-planta-amueblada.svg`, `A-03-planta-cotas.svg`, `A-04-envolvente-2d.svg`, `nivel-0-2d.json`, `manifest.json`, `origen-v8.json` y advertencias. Las cuatro hojas se derivan del **mismo** candidato `cand-ab3376d8fef08f3b-22`, generado por el núcleo Rust WASM v8 versionado con `examples/rectangular.json` y las reglas **demo** `knowledge/generic-house.json`. Las vistas PNG son únicamente rasterizaciones locales de SVG del mismo candidato, no otras soluciones.

`nivel-0-2d.json` tiene 6 vértices/lados y 8 vanos dibujados (7 ventanas y entrada), contorno ≈43,07 m y área poligonal bruta ≈94,86 m² concordante con Rust. **`level.index: 0` no fija altura alguna; `elevation_m: null`**. No es un plano de fachadas/cortes: ventanas/puerta solo se sitúan en el borde **2D**.

**SHA-256 ZIP:** `95f28e4d2142db81306ba4696e7f7580d715833d77afb35c67c7485168d5d4bd`. **SHA-256 WASM preexistente:** `fe95bb201e1bcb92574e09bc196670062fdc75da3b13502f7e2cb56dc6ba0874`. Reproducir (tras `npm ci --prefix web`): `node scripts/generate-sample-sheets.mjs`. Una prueba exige identidad byte a byte entre ZIP/SVG/JSON entregados y regenerados. La rasterización usó `resvg` temporal fuera del repositorio; el motor no lo requiere.

**No son dibujos de obra:** no hay alturas ni otras plantas, cortes, fachadas, hotel, hospital, norma cubana verificada, sitio legal ni caudal efectivo. Escala SVG nominal ISO A3; imprimir al 100 % y verificarla en cada equipo. Áreas y longitudes se refieren **solo al croquis** de una candidata validada por reglas ilustrativas. Contrato vigente: [paquete v2](../../docs/CONTRATO_LAMINAS_SVG_V2.md).
