"""Ayuda dinámica y orientación del flujo de trabajo (mejora UX v1.7.1).

Tres canales de ayuda que trabajan juntos para que el usuario nunca se
quede sin contexto:

1. Globos de ayuda (Tooltip): al detener el cursor sobre cualquier
   botón o control aparece una explicación breve Y la misma frase se
   fija en la barra de estado inferior.
2. Mensajes de menú (MENU_HINTS): al abrir cualquier menú superior, la
   barra de estado explica para qué sirve.
3. Motor de siguiente paso (next_hint): tras cada acción, la barra de
   estado sugiere de forma amable cuál es el paso siguiente natural,
   para que el flujo se descubra solo y no resulte abrumador.

El contenido es puro (sin Tk) para poder probarlo headless.
"""

from __future__ import annotations

import tkinter as tk
from typing import Any, Callable, Dict, Optional

# -- Ayuda por control (clave → texto orientador) ----------------------------
# Frases en segunda persona, con verbo y beneficio: "para qué me sirve
# esto" en menos de 12 palabras.
TOOLTIPS: Dict[str, str] = {
    "repeat": "Multiplicador de PLANTA TIPO (v3.32.0): «3» repite este "
              "nivel y sus locales tres veces al generar; las cotas de "
              "los niveles siguientes se recorren solas. "
              "1 = planta única.",
    "building_wizard": "Asistente de EDIFICACIÓN: te pide locales, "
                       "medidas, relaciones y requerimientos, y te "
                       "levanta el edificio completo con muros, puertas "
                       "y ventanas.",
    "wizard": "Asistente de diseño (local paso a paso): te pide los "
              "datos paso a paso y te arma el local con sus muros, "
              "puerta y ventana.",
    "asistente_local": "Asistente de local (MODIFICAR): cambia nombre "
                       "y uso, geometría, vanos, instalaciones y "
                       "mobiliario de un local existente, con "
                       "diagnóstico DNA.",
    "bld_climate": "El clima del lugar orienta ventanas, ventilación y "
                   "protección solar de tu edificación.",
    "bld_system": "Muros portantes, pórtico o mixto: decide qué muros "
                  "quedan marcados como estructurales.",
    "bld_orientation": "Hacia dónde mira la fachada principal: afecta "
                       "soleamiento y ventilación.",
    "bld_notes": "Notas libres sobre acabados, normativas o lo que no "
                 "quieras olvidar; quedan guardadas con la edificación.",
    "bld_usage": "El uso social sugiere el programa: locales, medidas y "
                 "relaciones típicas de viviendas, escuelas, "
                 "consultorios, POLICLÍNICO y HOSPITAL (en 3 niveles: "
                 "urgencias, quirófanos y hospitalización), comedores "
                 "y más.",
    "bld_viv_tip": "Tipología del catálogo maestro de viviendas (30 "
                   "tipologías VIV-01..30): con cualquier tipología el "
                   "asistente genera el PROGRAMA PARAMÉTRICO del §7 "
                   "(salas de 16-35 m², dormitorios de 9-16 m²…), las "
                   "relaciones del §8 y avisos de compatibilidad y "
                   "zonificación. «Programa clásico» mantiene los seis "
                   "locales de siempre.",
    "bld_viv_dorm": "Dormitorios de la vivienda (1-6): el programa "
                    "paramétrico genera el principal más los "
                    "secundarios con los rangos del §7 del catálogo.",
    "bld_viv_banos": "Baños de la vivienda (1-4): principal, social "
                     "(1,5-3 m²) y compartidos según cuántos pidas.",
    "bld_com_tip": "Tipología del documento COMERCIAL CC/OF (20 "
                   "tipologías CC-01..10 y OF-01..10): con «Centro "
                   "comercial» u «Oficinas» el asistente carga el "
                   "PROGRAMA MÍNIMO del §89-90 con medidas de los "
                   "cuadros MIN/REC, relaciones del §78 y avisos del "
                   "documento; «sin tipología concreta» usa el mismo "
                   "programa base.",
    "bld_edu_tam": "Tamaño del documento EDUCACIONAL (§4/§9/§48): con "
                   "Escuela primaria, Escuela secundaria, Círculo "
                   "infantil o Albergue carga el PROGRAMA MÍNIMO del "
                   "§106-109 por capacidad (NUM_AULAS = CEIL(alumnos / "
                   "alumnos por aula), un aula-higiene-descanso por "
                   "grupo, dormitorios colectivos de 8 plazas), con "
                   "medidas de los cuadros MIN/REC, relaciones del "
                   "§98-101 y avisos de seguridad infantil del §89; "
                   "«(programa básico)» conserva los programas "
                   "estáticos de siempre.",
    "tools_viv_alternativas": "ALTERNATIVAS COMPARABLES (catálogo "
                              "§62-63): con la misma entrada genera "
                              "A/B/C por nivel de acabado (Económica/"
                              "Estándar/Premium del §51) y 1/2/3/4 por "
                              "sistema constructivo (mampostería, "
                              "hormigón, steel framing, prefabricada) "
                              "con las métricas del §63: costo, plazo, "
                              "hormigón, acero, mampostería, madera, "
                              "consumo, mantenimiento, vida útil, "
                              "complejidad y disponibilidad. Solo "
                              "lectura.",
    "tools_viv_modulacion": "MODULACIÓN CONSTRUCTIVA (catálogo §56): "
                            "evalúa locales, muros, puertas y ventanas "
                            "contra el módulo 0.60/1.20/1.25/1.50 o "
                            "personalizado, con % de piezas en módulo, "
                            "residuo lineal acumulado y sugerencia al "
                            "múltiplo inferior/superior para reducir "
                            "desperdicios. Sugiere, no bloquea.",
    "tools_viv_solar": "ENERGÍA SOLAR (catálogo §38): dimensiona el "
                       "campo FOTOVOLTAICO, SOLAR TÉRMICO o HÍBRIDO "
                       "con tu consumo diario y las horas de sol pico: "
                       "número de paneles, potencia total, batería, "
                       "inversor y superficie de techo. La instalación "
                       "definitiva es REQUIERE_CALCULO_ESPECIALIZADO "
                       "(§81).",
    "tools_ccm_validar": "VALIDACIÓN CC/OF (documento comercial "
                         "v2.0): programa mínimo del §89-90, "
                         "relaciones del §78 con las prohibiciones "
                         "residuos/carga contra público, porcentajes "
                         "del §81, eficiencia del §82, "
                         "estacionamiento del §45, evacuación IBC "
                         "2024 del §17/§61, galería del §6 y control "
                         "dimensional de cada local. HVAC, rociadores, "
                         "CCTV y escaleras mecánicas quedan marcados "
                         "como REQUIERE_CALCULO_ESPECIALIZADO, sin "
                         "inventar números. Solo lectura.",
    "tools_edu_validar": "VALIDACIÓN EDUCACIONAL (documento de "
                         "escuelas y círculos infantiles): programa "
                         "mínimo del §106-109, relaciones del §98-101 "
                         "con los flujos limpio/sucio del §102, aulas "
                         "vs capacidad (§4/§111), dormitorios §49-51, "
                         "comedor (REGLA_08), escaleras §45, punto de "
                         "reunión §104-105, alturas libres §2 y "
                         "seguridad infantil §89. Climatización, "
                         "incendios, evacuación, CCTV y acústica "
                         "quedan marcados como "
                         "REQUIERE_CALCULO_ESPECIALIZADO, sin "
                         "inventar números. Solo lectura.",
    "val_html_save": "Guarda ESTE informe como un archivo HTML "
                     "autocontenido: se abre en el navegador, se "
                     "adjunta a un expediente o se imprime, sin "
                     "depender de ARQ_GEN.",
    "piscina_largo": "Largo del vaso en metros; el §45 trata la "
                     "piscina como sistema independiente.",
    "piscina_ancho": "Ancho del vaso en metros; con el largo da la "
                     "lámina de agua.",
    "piscina_prof_min": "Profundidad del extremo poco profundo; la "
                        "media dimensiona el volumen.",
    "piscina_prof_max": "Profundidad del extremo profundo; fuera de "
                        "0.8-2.5 m el informe avisa.",
    "piscina_altura": "Altura manométrica de la bomba; vacío usa la "
                      "referencia de 10 m.",
    "piscina_renovacion": "Horas de renovación total del agua; vacío "
                          "usa la referencia de 6 h.",
    "piscina_calc": "Dimensiona volumen, filtración, skimmers, bomba, "
                    "iluminación y seguridad con equipos en CUP.",
    "acu_menu": "Identifica fuentes de ruido contra dormitorios "
                "midiendo los muros del trazado y propone la "
                "solución del §46.",
    "dom_menu": "Plan domótico del §39: 8 sistemas con sus elementos "
                "contados sobre el modelo y equipos de referencia.",

    "bld_preset_combo": "Presets guardados en la carpeta «presets»: "
                        "configuraciones completas del asistente "
                        "listas para reutilizar.",
    "bld_preset_save": "Guarda la CONFIGURACIÓN actual del asistente "
                       "como preset JSON local (uso, tipología, vanos, "
                       "instalaciones...): no viajan los locales.",
    "bld_preset_load": "Aplica el preset elegido a este asistente: "
                       "luego pide el programa con «Cargar programa "
                       "del uso».",
    "bld_preset_del": "Elimina el .json del preset elegido; el "
                      "proyecto abierto no se toca.",
    "cmp_variants": "Matriz de TODAS las variantes: puntos, área, "
                    "coste PRECONS y coste por m2; la mejor "
                    "puntuada queda arriba.",
    "cmp_variants_csv": "Exporta la matriz a CSV con «;» para Excel, "
                        "listo para el expediente de decisión.",
    "bld_lot_w": "Ancho máximo disponible para la edificación "
                 "(0 = sin límite). Las variantes que no caben se "
                 "marcan y quedan al final.",
    "bld_lot_d": "Fondo máximo disponible para la edificación "
                 "(0 = sin límite). El motor usa estas medidas para "
                 "decidir si cada variante cabe.",
    "bld_construction": "Cómo se construyen los cerramientos: bloque y "
                        "losa, hormigón, prefabricado, acero, piedra, "
                        "adobe… queda guardado con la edificación.",
    "bld_shape": "Forma de la edificación en planta: rectangular, "
                 "cuadrada, en L, T, U, H, cruz, patio central o "
                 "articulada. Se sugiere según el uso social y guía el "
                 "motor de variantes del paso 6.",
    "bld_style": "Estilo arquitectónico (catorce: colonial, vernáculo "
                 "tropical, racionalista, high-tech, orgánico, "
                 "sostenible…): se sugiere según el uso social y activa "
                 "consejos de aleros, vanos y coherencia con la forma.",
    "bld_terrain": "Terreno regular o irregular: la pendiente obliga a "
                   "resolver la planta con DIFERENTES NIVELES DE PISO "
                   "(0,75 m o 1,50 m de desnivel) y cota propia en cada "
                   "local.",
    "bld_stairs": "Escaleras automáticas: se colocan solas entre niveles "
                  "y para salvar el desnivel del terreno; puedes "
                  "forzarlas o vetarlas (con aviso si son necesarias).",
    "bld_core": "Núcleo rígido en esquinas: caja de escalera, baños y "
                "ductos entre muros estructurales de refuerzo, en la "
                "esquina frontal de la planta. Automática (varios "
                "niveles o desnivel), siempre o nunca.",
    "bld_neufert": "Normativa Neufert: todas las medidas del asistente "
                   "siguen «El arte de proyectar en arquitectura» — "
                   "escalera con la fórmula de Blondel, pasillos y "
                   "puertas por uso (1,20 m donde pasa camilla), luz "
                   "de ventanas (1/8 del suelo), rampas al 8 %, alturas "
                   "libres y espesores de muro por tipología. Al cargar "
                   "un programa, el asistente sube pasillo y puerta a "
                   "lo que el libro pide; los avisos del resumen citan "
                   "la norma sin bloquear.",
    "bld_region": "Edición regional del libro: la base es la 5.ª ed. "
                  "en español y cada región (Cuba, México, Argentina, "
                  "Colombia) la ajusta — techos altos y luz 1/5 en el "
                  "trópico, mampostería confinada de 14 cm en México, "
                  "rampas y accesibilidad por código local. Cambiarla "
                  "re-aplica los valores del libro a tu proyecto.",
    "bld_dist": "Cómo se articulan los locales: Ortogonal (el trazado "
                "clásico), Articulada (fondos escalonados y chaflanes "
                "a 45°) u Orgánica (esquinas redondeadas, fachada en "
                "arco y pasillo serpenteante). Nunca reduce áreas ni "
                "toca paredes compartidas.",
    "bld_curv": "Cuánto curvan los gestos orgánicos: la flecha del "
                "arco de fachada y el radio de las esquinas "
                "redondeadas (0,3 a 4,0 m). Con la distribución "
                "ortogonal no se usa.",
    "bld_seed": "Semilla del gesto orgánico: la misma semilla "
                "reproduce exactamente la misma planta (útil para "
                "comparar opciones o volver a un favorito). Prueba "
                "varias y quédate con la que te guste.",
    "bld_eaves": "Alero recomendado contra el sol y la lluvia; 0,6 m es "
                 "lo habitual en clima cálido.",
    "bld_inst": "Módulos de instalaciones a prever: eléctrica, "
                "sanitaria, A/C, incendios, comunicaciones, gas o "
                "energía solar. Quedan en los requerimientos.",
    "bld_variants": "Variantes de planta puntuadas: adyacencias, luz, "
                    "compacidad, ventilación y clima. Elige una y mira "
                    "el dibujo antes de generar.",
    "bld_views": "Vistas técnicas de tu edificio: Planta (con tramas "
                 "de material, columnas y arcos de puertas), Elevación "
                 "(fachada cardinal), Corte (transversal o longitudinal, "
                 "con cimentación y cubierta) y Detalles constructivos. "
                 "«⤓ SVG» exporta la vista activa como vectorial, "
                 "«⤓ PNG» como imagen lista para informes y "
                 "«⤓ PDF» a A4 apaisado con cajetín y escala.",
    "bld_detalles": "Abre la biblioteca de detalles constructivos "
                    "pre-filtrada a la TIPOLOGÍA CONSTRUCTIVA que "
                    "elegiste en el paso 1: verás los cortes "
                    "recomendados para tu sistema (muros, entrepisos, "
                    "cubiertas…), exportables en SVG, PNG y PDF.",
    "dxf_file": "Plano DXF o DWG a importar: sus LINE en capas de muros "
                "y LWPOLYLINE cerradas en capas de locales se convierten "
                "en objetos del proyecto. Un .dwg se convierte antes a "
                "DXF con un conversor local (ODA File Converter o "
                "LibreDWG).",
    "dxf_conv": "Ruta de un conversor DWG→DXF (opcional). Vacío: se "
                "buscan LibreDWG (dwg2dxf) y ODA File Converter en el "
                "equipo, o el ejecutable guardado en ARQGEN_DWG2DXF.",
    "dxf_walls": "Capa exacta de muros (opcional). Vacío: se detectan "
                 "las capas cuyo nombre contiene muro/wall.",
    "dxf_spaces": "Capa exacta de locales (opcional). Vacío: se "
                  "detectan las capas con local/space/hab/ambiente.",
    "dxf_thick": "Espesor de los muros importados en metros "
                 "(0,05 a 2,0).",
    "dxf_level": "Nivel donde se crean los objetos del plano; si no "
                 "existe se crea con ese nombre.",
    "cat_search": "Busca renglones por código o descripción: «muro», "
                  "«hormigón», «pintura»… sin acentos ni mayúsculas.",
    "cat_section": "Limita la búsqueda a una sección del catálogo "
                   "(movimiento de tierra, cimentaciones, revestimientos…).",
    "cat_results": "Resultado de la búsqueda. Selecciona un renglón para "
                   "ver su precio oficial y su desglose.",
    "cat_qty": "Cantidad de obra del renglón elegido: el total usa el "
               "precio oficial CUP por unidad.",
    "cat_add_budget": "Añade el renglón seleccionado al presupuesto "
                      "PRECONS III del proyecto con la cantidad indicada.",
    "det_region": "La edición regional cambia la biblioteca: cada país "
                  "aporta sus detalles (block confinado, bahareque, "
                  "doble muro…) y retira los que no usa.",
    "det_cat": "Filtra la biblioteca por categoría: cimentaciones, "
               "muros, entrepisos, cubiertas, escaleras, humedades, "
               "carpintería y acabados.",
    "det_search": "Busca en la ficha del detalle: material («teja»), "
                  "norma («NSR-10») o solución («confinado»), sin "
                  "acentos ni mayúsculas.",
    "det_tree": "Detalles de la edición activa. Toca uno para ver su "
                "corte por capas, espesores y nota normativa; los * "
                "son propios de la región.",
    "det_text": "Ficha del detalle: capas con espesor y material, "
                "espesor total, usos, norma y avisos de obra.",
    "det_tipo": "Tipología constructiva del asistente de edificación: "
                "al elegir una, la lista acota a los detalles "
                "recomendados para ese sistema, adaptados a la "
                "edición regional activa.",
    "det_svg": "Exporta el esquema acotado del detalle en SVG "
               "vectorial: bandas de capas, leyenda de materiales y "
               "cajetín con la edición.",
    "det_png": "Exporta el esquema del detalle en PNG (imagen 2x): "
               "listo para informes, mensajería y presentaciones.",
    "det_pdf": "Exporta el detalle en PDF vectorial A4: listo para "
               "imprimir y entregar con el plano, con leyenda y "
               "cajetín.",
    "pb_tree": "Renglones del presupuesto con sus precios oficiales. "
               "Doble toque sobre una fila para re-fijar su cantidad "
               "con el valor del campo Cantidad.",
    "imp_file": "Libro Excel, CSV o JSON del catálogo: se detectan las "
                "hojas de secciones, renglones, materiales, equipos y "
                "mano de obra automáticamente.",
    "cat_calc": "Calcula el importe: cantidad × precio oficial del "
                "renglón seleccionado.",
    "guide": "Guía rápida: un recorrido de 4 pasos para dominar la pantalla.",
    "fit": "Encuadra todo el proyecto en el lienzo (tecla F).",
    "zoom_in": "Acerca la vista. También la rueda del ratón sobre el plano.",
    "zoom_out": "Aleja la vista. También la rueda del ratón sobre el plano.",
    "new_object": "Crea un objeto nuevo: local, muro, puerta, nivel… "
                  "según tu disciplina activa.",
    "edit": "Cambia un dato del objeto seleccionado (por ejemplo, el "
            "espesor de un muro).",
    "search_field": "Elige por qué buscar: código, nombre, tipo, nivel…",
    "search_entry": "Escribe aquí y pulsa Enter: verás los resultados en "
                    "el explorador de la izquierda.",
    "search_btn": "Busca en todo el proyecto (o en la disciplina activa).",
    "clear_btn": "Limpia la búsqueda y vuelve al árbol completo del proyecto.",
    "level_combo": "Muestra solo los objetos de un nivel de la edificación.",
    "props_edit": "Edita el campo marcado con ✎ del objeto seleccionado.",
    "state_btn": "Avanza el ciclo de vida del objeto: borrador → propuesto "
                 "→ aprobado…",
    "warnings_tab": "Hallazgos de validación: qué revisar antes de exportar.",
    "log_tab": "Diario de la aplicación (pestaña «Registro»): cada "
               "acción queda registrada aquí.",
    "calc_tab": "Historial de cálculos de cantidades y presupuesto.",
    "canvas": "Rueda: zoom · Mayús+rueda: mover · Clic derecho: menú "
              "(propiedades, editar, eliminar…) · Arrastrar con derecho: "
              "mover el plano · Clic: seleccionar · Doble clic: editar.",
    "hint_bar": "Recordatorio de los gestos del lienzo.",
    "save_btn": "Guarda ahora mismo todo el proyecto en SQLite. Con el "
                "autoguardado activo ni hace falta: se guarda solo tras "
                "cada cambio.",
    "theme_toggle": "Cambia entre modo oscuro y claro al instante; la "
                    "elección se recuerda para la próxima vez.",
    "autosave_toggle": "Activa o pausa el autoguardado: con él, cada "
                       "cambio se guarda solo (1,2 s de calma). La hora "
                       "del último guardado se ve en la barra inferior.",
    "cmd_line": "Línea de comandos (v3.38.0): alias (MU muro, M mover, "
                "Z zoom...), coordenadas 10,5 / @10,5 / @10<45 / 25 y "
                "=expresiones (2*3.5+pi). Enter vacío repite la última "
                "orden; las flechas recorren el historial y F2 lo abre "
                "en ventana.",
    "panel_explorer": "Muestra u oculta el explorador del proyecto "
                      "(Ctrl+1): la lista de disciplinas y objetos.",
    "panel_props": "Muestra u oculta el panel de propiedades (Ctrl+2): "
                   "los datos del objeto seleccionado.",
    "panel_bottom": "Muestra u oculta el panel inferior (Ctrl+3): "
                    "avisos, registro y estado de cálculos.",
    "help_mode": "Modo «¿Qué es esto?»: pulsas el botón y después "
                 "cualquier control para ver una explicación amable de "
                 "para qué sirve.",
    "ctx_menu": "Menú contextual del lienzo: acciones sobre lo que has "
                "pulsado, sin recorrer menús.",
    "tree_ctx": "Menú contextual del explorador: crear, editar o "
                "eliminar el objeto apuntado.",
    "welcome_new": "Crea un proyecto nuevo y empieza de cero.",
    "welcome_open": "Abre un proyecto .arqgen que ya tengas guardado.",
    "welcome_demo": "Carga un proyecto de ejemplo para explorar sin miedo "
                    "a romper nada.",
    "vista3d": "Vista 3D del edificio: arrastra para girar, cambia la "
               "elevación y el zoom, aísla niveles o sepáralos en "
               "explosión, y exporta un PNG determinista.",
    "calidad_coste": "Calidad de acabados de la estimación: cambia entre "
                     "Económica, Estándar y Premium y el coste PRECONS de "
                     "cada variante se recalcula al vivo (la obra gruesa "
                     "no cambia).",
    "importar_ifc": "Importación IFC de entrada: analiza un archivo IFC4 "
                    "(ISO-10303-21) y crea en tu proyecto los niveles, "
                    "muros, locales, puertas y ventanas; las escaleras "
                    "paramétricas exportadas por ARQ GEN se reconstruyen.",
    "cad_herramientas": "Panel de herramientas de edición tipo CAD: mover, "
                        "copiar, reflejar, girar, recortar, alargar, "
                        "chaflán, dividir, estirar y paralela sobre muros "
                        "y locales; todo queda en el diario y se puede "
                        "deshacer con Ctrl+Z.",
    "dibujo": "Panel de DIBUJO (v3.33.0): muros, espacios, zonas, "
              "puertas y ventanas a dos clics como ArchiCAD/AutoCAD, "
              "con espesor, altura y dimensiones configurables y las "
              "reglas del proyecto avisando en vivo.",
    "servicios": "Asistente de servicios completos por temática "
                 "(catálogo universal v3.0: 34 servicios en 8 "
                 "sectores — salud, educación, administración, "
                 "comercio y hostelería, deportivo, cultural, "
                 "residencial asistido y logística — con filtro por "
                 "sector): parámetros dinámicos, programa con grupos "
                 "y subtotales, validación funcional y, en "
                 "Documento, la ficha de cada local, la matriz de "
                 "instalaciones, las relaciones entre servicios, los "
                 "flujos y las 20 reglas de generación.",
    "desde_dibujo": "Desde dibujo (v3.34.0; explorador v3.36.0): el "
                    "camino al revés. Elija el contorno del área (un "
                    "espacio dibujado con el panel de Dibujo, un "
                    "rectángulo o una polilínea cerrada de un DXF), "
                    "defina el programa (servicio del catálogo con "
                    "filtro por sector, o usos del DNA) y el "
                    "asistente infiere forma y medidas, decide si los "
                    "locales entran en el área y sugiere el "
                    "crecimiento en altura (otros niveles) con el "
                    "recinto de la escalera según Blondel. El botón "
                    "«Explorar catálogo aquí» prueba el contorno "
                    "contra TODOS los servicios y lista los que caben "
                    "en un nivel primero.",
    "cad_dib_muro": "Dibujar MURO: dos clics (inicio y fin); espesor y "
                    "altura configurables en el panel. Con el imán "
                    "engancha a vértices y a la rejilla.",
    "cad_dib_espacio": "Dibujar ESPACIO: dos esquinas del rectángulo; "
                       "elige el uso (DNA) y el nombre en el panel y "
                       "el área se compara con el mínimo del uso.",
    "cad_dib_zona": "Dibujar ZONA: dos esquinas del área; los locales "
                    "dentro quedan asignados a la zona nueva.",
    "cad_dib_puerta": "Dibujar PUERTA: un clic sobre un muro y la "
                      "puerta queda centrada ahí; el ancho se compara "
                      "con el mínimo del uso que el muro limita.",
    "cad_dib_ventana": "Dibujar VENTANA: un clic sobre un muro; el "
                       "hueco se compara con el que pide el uso "
                       "(habitables 1/6 de superficie, húmedos 1/25).",
    "cad_mover": "Mover: clic sobre el muro o local, clic en el punto base "
                 "y clic en el destino. Los locales llevan consigo sus "
                 "muros exclusivos y reanclan sus instalaciones.",
    "cad_copiar": "Copiar: clic sobre el muro o local, clic en el punto "
                  "base y clic donde quieres la copia. El muro copia sus "
                  "vanos.",
    "cad_reflejar": "Reflejar: clic sobre el muro o local y dos puntos "
                    "del eje de simetría. Las puertas cambian de mano.",
    "cad_girar": "Girar: clic sobre el muro o local, clic en el centro de "
                 "giro y clic que define el ángulo (antihorario).",
    "cad_recortar": "Recortar: clic sobre el muro a recortar, clic sobre "
                    "el muro que hace de cuchilla y clic cerca del extremo "
                    "que quieres conservar.",
    "cad_alargar": "Alargar: clic sobre el muro, clic sobre el muro "
                   "objetivo y clic cerca del extremo a alargar.",
    "cad_chaflan": "Chaflán: clic sobre los dos muros, cerca de la "
                   "esquina. La distancia se fija en la paleta (m). Crea "
                   "el muro de unión y recorta ambos.",
    "cad_dividir": "Dividir: clic sobre el muro y clic en el punto de "
                   "corte; los vanos de la segunda mitad pasan al muro "
                   "nuevo.",
    "cad_estirar": "Estirar: clic sobre el muro, clic cerca del extremo a "
                   "mover y clic en la nueva posición.",
    "cad_paralela": "Paralela: clic sobre el muro original y clic al lado "
                    "de la copia; la distancia es la que hay hasta el "
                    "clic. La copia lleva sus vanos.",
    "cad_borrar": "Borrar: clic sobre el objeto a eliminar. El muro se "
                  "lleva sus vanos; todo es deshacible con Ctrl+Z.",
    # Teclado, puntero y editor de locales (v3.16.0)
    "puntero_aplicar": "Aplica el tamano, el grosor, el color y el paso "
                       "de imantacion del puntero; se recuerda entre "
                       "sesiones.",
    "editor_acceso": "Crea la puerta de acceso en el muro elegido, con "
                     "el ancho que pide el uso del local (o el que "
                     "escribas).",
    "editor_ventana": "Crea la ventana con el ancho que escribas o el "
                      "hueco que pide la ventilacion del uso (habitables "
                      "1/6 del suelo; humedos 1/25).",
    "editor_redimensionar": "Lleva el local a las dimensiones pedidas "
                            "moviendo sus muros exclusivos; los vanos "
                            "se re-proyectan y el mobiliario se "
                            "vuelve a colocar.",
    "editor_mobiliario": "Vuelve a amueblar SOLO este local con su uso "
                         "y la densidad elegida.",
    "editor_local_combo": "El local que vas a modificar: el diagnóstico "
                          "de la derecha y todos los botones actúan "
                          "sobre él.",
    "editor_lampara": "Tipo de lámpara para la iluminación de este "
                      "local (método de los lúmenes; el uso da los "
                      "lux si no los escribes).",
    "editor_identidad": "Cambia el nombre y el USO del local; el uso "
                        "trae el DNA (area minima, puerta de camilla) y "
                        "puede reamueblar el local.",
    "editor_mover": "Desplaza el local completo con sus muros "
                    "exclusivos y su mobiliario; los muros compartidos "
                    "se quedan (se avisa).",
    "editor_espesor": "Espesor nuevo para TODOS los muros exclusivos "
                      "del local.",
    "editor_cota": "Cota del piso del local (se usa en la vista 3D y "
                   "en la accesibilidad).",
    "editor_instalaciones": "Conecta el local a eléctrica (luminaria + "
                            "toma) y, si es húmedo, a agua y desagüe.",
    "editor_iluminar": "Dimensiona y coloca las luminarias de este "
                       "local; las del resto del proyecto se conservan.",
    "editor_alarmar": "Protege este local: PIR, contactos en sus vanos, "
                      "panel, teclado y sirena.",
    "editor_editar_vano": "Aplica ancho, alto, antepecho y posición al "
                          "vano elegido de la lista.",
    "editor_quitar_vano": "Da de baja el vano elegido (queda en el "
                          "deshacer).",
    "editor_local_ficha": "Exporta la FICHA IMPRIMIBLE del local "
                          "(PDF): identidad, DNA del uso, vanos, "
                          "mobiliario, instalaciones, planta dibujada "
                          "y diagnóstico.",
    "editor_local_validar": "VALIDACIÓN DIMENSIONAL del local "
                            "(documento hospitalario, sección 19): "
                            "superficie, ancho, altura, puertas y "
                            "pasillos contra las cotas del uso, con "
                            "el checklist completo y su tipo de cota "
                            "(A-F).",
    "mod_wizard": "Asistente de modificaciones: elige elemento, operación "
                  "y parámetros numéricos con vista previa, sin depender "
                  "del clic fino sobre el plano.",
    # Concepción de espacios (v3.15.0)
    "mobiliario": "Amueblar: coloca el mobiliario del catálogo en cada "
                  "local según su uso, con paso mínimo entre piezas. El "
                  "tema (doméstico/social) sale del uso social del "
                  "asistente.",
    "mobiliario_quitar": "Retira SOLO el mobiliario generado por el "
                         "motor; las piezas que hayas movido o editado "
                         "a mano se conservan.",
    "cubiertas": "Cubrir: genera la cubierta sobre el nivel superior "
                 "(plana, un agua, dos o cuatro aguas) con material, "
                 "pendiente y alero; «auto» la sugiere según el estilo "
                 "arquitectónico.",
    "cubiertas_quitar": "Retira la cubierta generada (la geometría "
                        "queda en el historial y es deshacible).",
    "accesibilidad_analizar": "Audita las barreras arquitectónicas: "
                              "anchos de puerta y pasillo, escaleras "
                              "(Blondel y barandilla), desniveles sin "
                              "rampa y círculo de giro en aseos.",
    "accesibilidad_aplicar": "Aplica soluciones: barandillas de escalera "
                             "a 0.90 m, rampas con pendiente normativa y "
                             "pasamanos doble (0.95 + 0.65 m) y barras de "
                             "apoyo junto a los inodoros.",
    "accesibilidad_quitar": "Retira las rampas y barandillas generadas; "
                            "lo editado a mano sigue en su sitio.",
    # Ascensores y fachada (v3.18.0)
    "ascensores": "Levantar hueco: coloca el ascensor con las tablas de "
                  "Neufert (capacidad, cabina, hueco, puerta, foso y "
                  "velocidad) dentro de un núcleo o escalera, o adosado "
                  "a la fachada que pidas.",
    "ascensores_quitar": "Retira SOLO los huecos generados por el "
                         "motor; cualquier ajuste manual se conserva.",
    "parasoles": "Poner parasoles: lamas horizontales al sur, aletas "
                 "verticales a este y oeste, según la orientación "
                 "medida del recinto; «auto» decide por ti y el tipo "
                 "explícito manda en todos los lados.",
    "parasoles_quitar": "Retira SOLO los parasoles generados; la piel "
                        "exterior no se toca.",
    "piel": "Envolver con piel: doble piel de vidrio, celosía de "
            "madera, malla metálica, baguettes de terracota, panel "
            "perforado, jardín vertical, GRC o policarbonato, con la "
            "cámara ventilada que pidas; «auto» la sugiere el estilo "
            "arquitectónico.",
    "piel_quitar": "Retira SOLO las pieles generadas; los parasoles "
                   "no se tocan.",
    "fachada_capa": "Muestra u oculta parasoles y pieles en la vista "
                    "3D (el hueco del ascensor siempre sale).",
    # Escaleras, aberturas, iluminación y alarmas (v3.19.0)
    "diseno_espacios": "Taller de diseño de espacios: nueve pestañas "
                       "para amueblar según el uso, cubrir según el "
                       "estilo, resolver barreras, levantar ascensor y "
                       "escalera según Neufert, vestir la fachada, "
                       "tipificar puertas y ventanas, proyectar la "
                       "iluminación y proteger los locales con alarmas. "
                       "Todo se regenera con la edificación.",
    "escaleras": "Levantar escalera: elige la tipología (recta, en L, "
                 "en U o caracol) y la fórmula de Blondel dimensiona "
                 "los peldaños; la planta y el 3D dibujan la escalera "
                 "dentro de un hueco o núcleo que la acoja.",
    "escaleras_quitar": "Retira SOLO las escaleras generadas; el hueco "
                        "del local se conserva.",
    "aberturas": "Aplicar tipología: da funcionamiento a todas las "
                 "puertas o ventanas del nivel (abatible, corredera, "
                 "oscilobatiente...) y el plano dibuja su símbolo de "
                 "arquitectura.",
    "aberturas_recuento": "Recuento de vanos por tipología (y los "
                          "que aún no tienen tipo).",
    "aberturas_quitar": "Limpia la tipología guardada; los vanos "
                        "siguen en sus muros.",
    "iluminacion": "Dimensionar y colocar: método de los lúmenes con "
                   "la lámpara elegida (LED, fluorescente, halógena... "
                   "y las luminarias entran en la red de alumbrado, en "
                   "retícula y con su potencia en atributos.",
    "iluminacion_comparativa": "Compara todas las tecnologías del "
                               "catálogo para el local de referencia: "
                               "cuántas lámparas y cuántos watios.",
    "iluminacion_quitar": "Retira SOLO las luminarias generadas; lo "
                          "cableado a mano se conserva.",
    "alarmas": "Proteger locales: PIR por sectores, contactos en los "
               "vanos del perímetro, panel, teclado y sirena en el "
               "local que elijas; la cobertura se valida con el motor "
               "de intrusión.",
    "alarmas_quitar": "Retira SOLO los dispositivos generados; lo "
                      "cableado a mano se conserva.",
}

# Ayudas para los campos de los formularios de creación (FASE 90.1).
FIELD_HINTS: Dict[str, str] = {
    "name": "Un nombre claro te ayudará a encontrarlo después.",
    "elevation_m": "Altura del piso sobre el terreno, en metros (0 = planta "
                   "baja).",
    "height_m": "Altura libre del piso o del elemento, en metros.",
    "repeat": "Multiplicador de la planta: «3» repite este nivel y sus "
              "locales tres veces (planta tipo). 1 = planta única.",
    "space_type": "Clave del tipo de local (ROOM, KITCHEN, BATH…).",
    "boundary": "Contorno del local: pares «x,y» separados por espacios. "
                "Si lo dejas vacío se crea uno provisional.",
    "start": "Punto inicial del muro: «x, y» en metros.",
    "end": "Punto final del muro: «x, y» en metros.",
    "thickness_m": "Espesor del muro en metros (0.2 = 20 cm).",
    "width_m": "Dimension horizontal, en metros.",
    "offset_m": "Distancia desde el inicio del muro hasta el hueco.",
    "sill_height_m": "Altura del antepecho: de la planta a la base de la "
                     "ventana.",
    "wall_ref": "Elige el muro donde irá el hueco.",
    "level_ref": "Elige el nivel donde vivirá el objeto.",
    "kind": "Familia o tipo del elemento.",
    "shape": "Forma de la sección transversal.",
    "h_mm": "Dimensión h de la sección, en milímetros.",
    "b_mm": "Dimensión b de la sección, en milímetros.",
    "load_udl_kn_m": "Carga repartida uniforme sobre el elemento (kN/m).",
    "system": "Sistema de la red: agua, eléctrico, CCTV…",
    "description": "Opcional: una nota corta para saber qué hace esta "
                   "red.",
    "network_ref": "Red a la que se conecta el nodo.",
    "x": "Coordenada X en metros.",
    "y": "Coordenada Y en metros.",
    "fck_mpa": "Resistencia característica del hormigón (MPa).",
    "fy_mpa": "Límite elástico del acero (MPa).",
    "density_kn_m3": "Peso específico del material (kN/m³).",
}

# Mensajes que la barra de estado muestra al abrir cada menú superior.
MENU_HINTS: Dict[str, str] = {
    "Archivo": "Crear, abrir, guardar y exportar tu proyecto. Empieza por "
               "aquí si es tu primera vez.",
    "Editar": "Deshacer, rehacer, crear, editar y eliminar objetos.",
    "Ver": "Zoom, encuadre y cuadrícula del plano.",
    "Herramientas": "Asistentes de edificación y de local, el catálogo "
                    "PRECONS III con precios oficiales, validación, "
                    "cálculos y el informe.",
    "Ayuda": "Guía rápida, atajos de teclado e información de la app.",
}

# -- Guía rápida (recorrido de 4 pasos) ---------------------------------------
GUIDE_STEPS = (
    ("1 · Mira y navega",
     "El explorador de la izquierda agrupa el proyecto en 13 disciplinas. "
     "Pulsa sobre cualquier objeto y verás sus datos a la derecha y su "
     "figura en el plano central. ¿El plano está apretado? Arrastra los "
     "separadores entre paneles (y los bordes de cualquier ventana) para "
     "darle el espacio que quieras: la app recuerda cómo los dejas. Un "
     "doble clic sobre un separador colapsa su panel, y «Ver ▸ Restaurar "
     "disposición por defecto» (Ctrl+0) lo devuelve todo al estado de "
     "fábrica."),
    ("2 · Crea y edita",
     "El botón «🏠 Asistente de edificación» te guía en 5 pasos y "
     "levanta el edificio completo (locales, muros, puertas, ventanas y "
     "requerimientos). Para un solo local, «✨ Asistente de local». "
     "Todo queda en el diario (pestaña «Registro») y se puede deshacer "
     "con Ctrl+Z."),
    ("3 · Calcula",
     "En «Herramientas ▸ Recalcular todo» obtienes cantidades (QTO) y "
     "presupuesto. Para precios oficiales CUP abre «Herramientas ▸ "
     "Catálogo PRECONS III» y consulta cualquiera de los 15981 "
     "renglones. Los hallazgos de validación aparecen en «Avisos»."),
    ("4 · Comparte",
     "Cuando estés conforme, usa «Archivo ▸ Exportar» (DXF, XLSX, CSV, "
     "JSON, IFC) o genera el informe descriptivo en Markdown."),
)

# Sugerencia por defecto cuando no hay nada mejor que proponer.
DEFAULT_HINT = ("Todo listo. Si dudas, pulsa «Guía rápida» o abre "
                "Archivo ▸ Proyecto de demostración para explorar.")


def next_hint(*, spaces: int = 0, walls: int = 0, doors: int = 0,
              calculations: int = 0, warnings: int = -1,
              searching: bool = False) -> str:
    """Devuelve el siguiente paso sugerido según el estado del proyecto.

    Función pura: los parámetros resumen el proyecto y la respuesta es
    una frase amable y concreta. El orden replica el flujo natural de
    trabajo: modelar locales → muros → huecos → calcular → validar.
    """
    if searching:
        return ("Haz clic en un resultado para saltar a él, o pulsa "
                "Escape para volver al árbol completo.")
    if spaces == 0:
        return ("Paso siguiente: pulsa «🏠 Asistente de edificación» y te "
                "voy pidiendo locales, medidas y relaciones para "
                "levantar tu edificio completo (o «✨ Asistente de "
                "local» para uno solo).")
    if walls == 0:
        return ("Paso siguiente: añade muros con «+ Objeto ▸ WALL» para "
                "delimitar los espacios.")
    if doors == 0:
        return ("Paso siguiente: inserta puertas o ventanas sobre los "
                "muros con «+ Objeto».")
    if calculations == 0:
        return ("Paso siguiente: Herramientas ▸ Recalcular todo para "
                "obtener cantidades y presupuesto.")
    if warnings > 0:
        return ("Revisa la pestaña «Avisos»: hay hallazgos que conviene "
                "atender antes de exportar.")
    if warnings == 0:
        return ("Validación limpia. Ya puedes exportar con Archivo ▸ "
                "Exportar o generar el informe.")
    return DEFAULT_HINT


class Tooltip:
    """Globo de ayuda al pasar el cursor + eco en la barra de estado.

    - Al entrar el cursor: fija `text` en la barra de estado (si se
      pasó `status_var`) y, tras `delay` ms, muestra un globo oscuro
      junto al control.
    - Al salir o al pulsar: retira el globo y restaura la barra.
    """

    def __init__(self, widget: Any, text: str,
                 status_var: Optional[tk.StringVar] = None,
                 restore: Optional[Callable[[], str]] = None,
                 delay: int = 550) -> None:
        self.widget = widget
        self.text = text
        self.status_var = status_var
        self.restore = restore
        self.delay = max(120, int(delay))
        self._after_id: Optional[str] = None
        self._balloon: Optional[tk.Toplevel] = None
        widget.bind("<Enter>", self._on_enter, add="+")
        widget.bind("<Leave>", self._on_leave, add="+")
        widget.bind("<ButtonPress>", self._on_leave, add="+")

    # -- comportamiento --------------------------------------------------------
    def _on_enter(self, _event=None) -> None:
        if self.status_var is not None:
            self.status_var.set(self.text)
        self._after_id = self.widget.after(self.delay, self._show)

    def _on_leave(self, _event=None) -> None:
        if self._after_id is not None:
            try:
                self.widget.after_cancel(self._after_id)
            except Exception:  # noqa: BLE001 - widget ya destruido
                pass
            self._after_id = None
        self._hide()
        if self.status_var is not None and self.restore is not None:
            self.status_var.set(self.restore())

    def _show(self) -> None:
        if self._balloon is not None:
            return
        try:
            x = self.widget.winfo_rootx() + 12
            y = self.widget.winfo_rooty() + \
                self.widget.winfo_height() + 6
            balloon = tk.Toplevel(self.widget)
        except Exception:  # noqa: BLE001 - ventana cerrada entre medias
            return
        from ui import theme as _theme  # importación tardía: evita ciclos
        p = _theme.colors()
        balloon.wm_overrideredirect(True)
        balloon.wm_geometry(f"+{x}+{y}")
        label = tk.Label(
            balloon, text=self.text, justify="left", wraplength=340,
            background=p["tooltip_bg"], foreground=p["tooltip_text"],
            highlightthickness=1, highlightbackground=p["tooltip_border"],
            padx=10, pady=6, font=("TkTextFont", 9))
        label.pack()
        self._balloon = balloon

    def _hide(self) -> None:
        if self._balloon is not None:
            try:
                self._balloon.destroy()
            except Exception:  # noqa: BLE001 - ya destruido
                pass
            self._balloon = None


def attach_menu_hints(menu: tk.Menu, status_var: tk.StringVar) -> None:
    """Explica cada menú superior en la barra de estado al abrirlo.

    Usa el `postcommand` del submenú de cada cascada, que Tk dispara
    justo antes de desplegarlo: funciona igual en Windows, Linux y
    macOS.
    """
    for label, hint in MENU_HINTS.items():
        try:
            index = menu.index(label)
        except Exception:  # noqa: BLE001 - etiqueta ausente
            continue
        if index is None or menu.type(index) != "cascade":
            continue
        try:
            submenu = menu.nametowidget(menu.entrycget(index, "menu"))
        except Exception:  # noqa: BLE001 - cascada sin submenú
            continue
        submenu.configure(postcommand=lambda h=hint: status_var.set(h))


__all__ = [
    "TOOLTIPS", "FIELD_HINTS", "MENU_HINTS", "GUIDE_STEPS", "DEFAULT_HINT",
    "next_hint", "Tooltip", "attach_menu_hints",
]