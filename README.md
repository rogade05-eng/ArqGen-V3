# ARQ GEN

**Sistema profesional de escritorio para arquitectura, ingeniería, construcción y seguridad.**
Fases entregadas: **P0 — Fundación + P1 — Arquitectura + FASES 10–16 — Instalaciones completas + FASES 17–25 — Estructura, Seguridad y Coordinación + FASES 26–29 — QTO/Precios/Presupuesto + FASES 30–33 — PRECONS/SIECONS, BIM e IFC + FASES 34–43 — Documentación, Optimización, Auditoría, Versionado, Backup/Recovery, Plugins, Rendimiento y QA final + FASE 90 — Interfaz gráfica (spec 90-93) + IMPORTACIÓN §94 — pipeline completo de archivos externos (v1.7.0) + UX v1.7.1 — tema oscuro, ayuda dinámica y flujo guiado + v1.7.2 — asistente dinámico de diseño e interfaz 100% en español + v1.8.0 — asistente de EDIFICACIÓN completa (locales, relaciones espaciales y requerimientos) + v1.9.0 — CATÁLOGO PRECONS III real completo (RoPres 3.30, 15981 renglones + 4383 recursos oficiales) + v1.9.1 — importador NATIVO del libro oficial PRECONS III + v2.0.0 — EL SALTO: presupuesto por catálogo PRECONS III con precios oficiales, análisis de precio oficial directo en el motor, asistente de importación §94 en la GUI y exportadores PDF/SVG/PNG 100% stdlib + v2.1.0 — ASISTENTE DE GENERACIÓN DE EDIFICACIONES: uso social con locales sugeridos, dimensiones y tipología constructiva, paso bioclimático e instalaciones, y GENERADOR DE VARIANTES DE PLANTA puntuadas (lineal, doble crujía y patio central con espejo) + preview dibujado + v2.2.0 — TEMA HOSPITALARIO: usos Policlínico y Hospital con DNA técnico de salud (quirófano, urgencias, esterilización, hospitalización, laboratorio, imagenología, farmacia, enfermería), programa multi-nivel con niveles automáticos, puertas críticas por uso e instalaciones sugeridas (A/C y gas medicinal) + v3.4.0 — DWG DE ENTRADA por pasarela a conversores locales (ODA File Converter / LibreDWG / ARQGEN_DWG2DXF) integrado en el asistente §94 y en la CLI, y BUNDLE PYINSTALLER multiplataforma con spec espejo del .bat y verificación post-compilación (selftest del ejecutable + catálogo certificado desde el bundle) + v3.5.0 — BIBLIOTECA DE DETALLES CONSTRUCTIVOS por ediciones regionales: 18 soluciones universales en 8 categorías + México (RCDF/NTC), Colombia (NSR-10), Argentina (IRAM/CIRSOC) y Cuba (NC), cada una añadiendo sus detalles, reemplazando o retirando los que no aplica; navegador en la GUI, CLI `detalles` y exportación del esquema SVG acotado + v3.6.0 — DETALLE EN PDF/PNG y VÍNCULO CON LA TIPOLOGÍA CONSTRUCTIVA: el corte se exporta también en PDF vectorial A4 y PNG 2x deterministas, la base universal crece a 20 detalles (muro de piedra y muro de tierra/adobe) y cada tipología del asistente (las 10 de CONSTRUCTION_TYPES) enlaza con sus detalles recomendados, adaptados a la edición regional activa + v3.7.0 — VENTANAS Y PANELES AJUSTABLES: los separadores de la ventana principal son gruesos (10 px) y se arrastran para dar más espacio al plano, las posiciones se recuerdan entre sesiones, y las 12 ventanas de la app (catálogo, detalles, presupuesto, importadores, asistentes, guía y formularios) salen redimensionables con tamaño mínimo y geometría recordada al cerrar + v3.8.0 — LAYOUT RESTAURABLE + 3 EDICIONES REGIONALES + PDF DE DOCUMENTOS: «Restaurar disposición por defecto» (Ctrl+0) y doble clic sobre un separador que colapsa su panel (Tk 9 y Tk 8.6), las ediciones regionales de detalles de España (CTE), Perú (RNE) y Chile (DS 61/NCh) elevan la biblioteca a 7 ediciones, la memoria y el pliego incorporan la sección de detalles recomendados por la tipología del asistente, y cualquier documento sale también en PDF A4 determinista (CLI, servicio y GUI) + v3.8.1 — SELFTEST PORTABLE AL EJECUTABLE: los checks 49/50 omiten la verificación de texto del fuente al vuelo congelado (PyInstaller no embarca los .py) y declaran la omisión en su línea OK, con lo que la etapa 3 del post-build (`ARQ_GEN.exe selftest`) termina limpio + v3.9.0 — INTERFAZ COMPACTA, PLANO PRIMERO: logo de 22 px en la barra (el de 256 px solo en la barra de título), herramientas en dos filas para que el buscador y el filtro de niveles nunca se corten con la escala de Windows, separadores de fábrica 240/300/160 y panel de avisos más bajo + v3.9.1 — EL PANEL DE AVISOS YA NO SE COME LA VENTANA: migración one-shot de las preferencias heredadas que dejaban el panel inferior a media ventana (formato de prefs v2 con marca bottom_compact), separador inferior de fábrica 120 px, Notebook de 100 px y textos de 3 líneas + v3.10.0 — EDIFICACIÓN REGENERATIVA: editor del programa de locales que MUEVE, AÑADE, QUITA, REDIMENSIONA y lleva locales a otro nivel reconstruyendo el programa desde el proyecto, genera las 28 variantes puntuadas del motor para ELEGIR la que sustituye, y SUSTITUYE la edificación purgando lo generado sin dejar huérfanos (terminales de instalaciones, relaciones, vanos, muros y locales) mientras las instalaciones se recalculan sobre la geometría nueva y lo dibujado a mano se conserva + v3.11.0 — VISTA 3D AXONOMÉTRICA: el edificio generado se gira con el ratón (azimut envolvente y elevación sujeta), se aísla por nivel o se separa en «explosión», los muros se extruyen con su altura real y eliminación de caras traseras, los pisos se pintan por tipo de local, los vanos salen a su cota real sobre la cara visible del muro, cada nivel descansa sobre su plataforma y todo sale también en PNG determinista 100% stdlib — sin una dependencia nueva** + v3.12.0 — PRESUPUESTO VIVO SOBRE LAS VARIANTES: cada variante del motor de plantas sabe CUÁNTO CUESTA en renglones OFICIALES del catálogo PRECONS III (takeoff paramétrico del trazado — muros con vanos descontados y clasificación geométrica exterior/interior que funciona igual en L/T/U/H/cruz/articuladas —, losas por tipología constructiva, cimentación, escaleras, aparatos sanitarios por tipo de local y puntos eléctricos), el coste se ve junto a la puntuación en la regeneración y en el asistente, la CALIDAD DE ACABADOS (Económica/Estándar/Premium) recalcula al vivo sin regenerar nada y sin tocar la obra gruesa, el desglose por capítulos acompaña a cada variante y la comparativa sale en PNG determinista + v3.13.0 — SOMBRAS SOLARES, TERRENO 3D E IFC DE ENTRADA/SALIDA: posición solar verificable a mano (declinación de Cooper + ángulo horario), sombras proyectadas por rayos paralelos con recorte Sutherland-Hodgman fuera de la huella y arrugadas sobre la malla del terreno, brújula con el norte rojo y trayectoria solar del día en el diálogo 3D (latitud de 8 ciudades, equinoccios/solsticios y hora solar), malla de terreno determinista con pendiente, relieve con semilla y plataforma nivelada bajo la huella, y el IFC ya ENTRA por un parser SPF propio (unidades, colocaciones anidadas, extrusiones rectangulares/poligonales) que reconstruye niveles, muros, locales, puertas y ventanas fieles al milímetro — con tres bugs de SALIDA corregidos de paso (vanos en el origen, RelFillsElement invertido y representaciones sin lista) + v3.13.1 — CONSOLA A PRUEBA DE WINDOWS: el mensaje del check 55 deja de llevar la flecha «→» que la consola cp1252 no puede codificar y mataba el selftest del ejecutable después de 54 OK, stdout/stderr quedan en errors="replace" desde la entrada de la CLI y las 8 flechas de los print() de la CLI pasan a «->» + v3.14.0 — HERRAMIENTAS DE EDICIÓN TIPO CAD: paleta con iconos (mover, copiar, reflejar, girar, recortar, alargar, chaflán, dividir, estirar, paralela y borrar) sobre muros y locales con máquina de estados en el lienzo, motor sin Tk con auditoría/undo/QTO/instalaciones reancladas, vanos que se re-proyectan al recortar o dividir, locales que llevan sus muros exclusivos, lo editado a mano que sobrevive a la regeneración, y un asistente de modificaciones con vista previa antes/después + v3.15.0 — CONCEPCIÓN DE ESPACIOS: MOBILIARIO, CUBIERTAS Y ACCESIBILIDAD: los locales generados se AMUEBLAN según el tema y el uso social/doméstico (catálogo de 32 piezas con reglas por tipo de local, densidad compacta/estándar/amplia y paso mínimo entre muebles), la edificación se CUBRE según el estilo arquitectónico (plana transitable/no transitable, un agua, dos aguas y cuatro aguas con material, estructura, pendiente, alero, cumbrera y superficie real) y se RESUELVEN las barreras arquitectónicas (chequeos de puertas, pasillos, escaleras y desniveles + barandillas de escalera, rampas normativas con tramos y mesetas, pasamanos doble y barras de apoyo); cuatro entidades nuevas (FURNITURE/ROOF/RAMP/HANDRAIL) con migración 009, undo persistente, QTO, renglones PRECONS y regeneración completa** + v3.16.0 — TECLADO Y PUNTERO AUTOCAD, EDITOR DE LOCALES Y CUBIERTAS V2: teclado de trabajo estilo AutoCAD (F3 referencias, F7 rejilla, F8 orto, F9 imantar, F10 polar, ESC cancela, ESPACIO repite la última orden, alias M/CO/MI/RO/TR/EX/CHA/DIV/S/O/E/U/P letra a letra y Ctrl+Z/Y/C/X/V/S/O/N/A/P/0), MIRA configurable de punta a punta (tamaño %, grosor, color, persistido en prefs) con referencias a extremos (cuadro) y puntos medios (triángulo), pan con flechas y con P arrastrando, portapapeles Ctrl+C/X/V que duplica locales, navegación 3D con teclado (flechas, +/-, Home), EDITOR PROFUNDO del local (diagnóstico con avisos, puerta de acceso con el ancho del uso, ventana con el hueco que pide la ventilación —habitables 1/6 y húmedos 1/25 del suelo—, redimensionar que mueve SOLO los muros exclusivos re-proyectando vanos y re-colocando el mobiliario, y reamueblado puntual), y CUBIERTAS v2 (mansarda a la francesa con codo al 55 %, mariposa con el valle en el eje, dientes de sierra con vidrio vertical, fibrocemento y pendiente MÍNIMA por material con aviso) + v3.17.0 — COTA DE CUBIERTA Y VISTA EN PERSPECTIVA: la cubierta se IMPLANTA a la cota que el usuario pida (o sobre el top de los muros, corrigiendo el defecto heredado que la dejaba naciendo en el piso del nivel, enterrada) con aviso si queda baja, la explosión y el 3D la respetan, y la vista 3D gana la PROYECCIÓN EN PERSPECTIVA con punto de fuga (tecla P o casilla) sobre la axonométrica de siempre, con centro y distancia calculadas del FOV, plano cercano de seguridad y PNG determinista igual de válido** + v3.18.0 — ASCENSORES SEGÚN NEUFERT Y FACHADA: huecos de ascensor con las tablas del libro (pasajeros 450-2000 kg, hospital con camillas, montacargas y panorámico; cabina, hueco y puerta central; foso, paso libre y velocidad por recorrido; cantidad recomendada por ocupación) colocados dentro del núcleo o adosados a fachada, PARASOLES por orientación (sur horizontal, este/oeste vertical, mixto y lamas orientables, en aluminio/madera/corten/GRC/cerámica/textil, con área de sombra en QTO) y OCHO PIELES EXTERIORES contemporáneas (doble piel de vidrio, celosía, malla, terracota, panel perforado, jardín vertical, GRC y policarbonato) con cámara ventilada sugeridas por el estilo arquitectónico; entidades ELEVATOR/PARASOL/SKIN con migración 010, undo persistente, QTO, 3D con interruptor de capa y PNG determinista** + v3.19.0 — ESCALERAS, ABERTURAS, ILUMINACIÓN Y ALARMAS: escaleras por TIPOLOGÍA (recta, en L, en U/doble piso y caracol) dimensionadas con la fórmula de Blondel con mesetas cada 16 contrahuellas y planta real (contorno, huellas y peldaños en 2D y 3D) dentro del hueco de escalera o núcleo, TIPOS DE PUERTAS (abatible, doble hoja, corredera, plegable, vaivén, pivote) Y VENTANAS (practicable, oscilobatiente, abatible, proyectante, corredera, guillotina, fija, pivotante) con símbolo de planos por tipología, ILUMINACIÓN ARTIFICIAL por tipos de LÁMPARAS (12 del catálogo: LED bombilla/panel/downlight/lineal/tira/campana/proyector, fluorescente T8 y compacta, halógena, incandescente y sodio) con el método de los lúmenes y luminarias colocadas en la red de alumbrado con su potencia y flujo, y ALARMAS CONTRA INTRUSOS sobre los LOCALES QUE EL USUARIO ELIGE (PIR por sectores, contactos magnéticos en los vanos del perímetro, panel, teclado y sirena, con la cobertura validada por el motor de intrusión); entidad STAIR con migración 011, fórmulas QTO de escalera y 9 pestañas en el taller de diseño** + v3.19.1 — SELECCIONAR EN EL PLANO VUELVE A FUNCIONAR: la mira estilo AutoCAD ya no roba el clic (el picking recorre los objetos de arriba hacia abajo y salta los superpuestos de dibujo) y el mobiliario, las cubiertas, rampas, barandillas y escaleras son objetos seleccionables desde el lienzo, el árbol y el buscador + v3.20.0 — ASISTENTE DE LOCAL PARA MODIFICAR Y ESPECIALIDADES DE SALUD: el asistente de local ya no solo crea, ahora MODIFICA un local existente controlando todo lo que le es imputable (identidad con nombre y uso validado por el DNA, geometría con dimensiones, posición, espesor de sus muros y cota del piso, vanos para crear, retocar medidas o dar de baja, instalaciones de eléctrica y sanitaria, iluminación por lámparas y alarma del local, y mobiliario por densidad) con diagnóstico DNA permanente, y la red de salud suma las especialidades pedidas (tomografía, fluoroscopio, anatomía patológica, morgue, cuidados progresivos, laboratorio de microbiología, nodo informático, local PGD y almacenes) con su ficha técnica, programa hospitalario ampliado, lux por uso y equipamiento específico (100% funcional, sin módulos incompletos) + v3.26.0 — ESCUELAS Y CÍRCULOS INFANTILES: el documento del usuario («Especificaciones técnicas, funcionales y dimensionales - Escuelas primarias, secundarias, círculos infantiles y albergues escolares», 125 secciones) entra al programa como DATOS versionados (resources/knowledge/educacion_specs.json): 4 tipologías ED-01..04, capacidades paramétricas §4/§9/§48 con la fórmula NUM_AULAS = CEIL(alumnos / alumnos por aula), 82 cuadros de cotas MIN/REC con unidad y nota (aulas §5-§8, cuna §10, juego §12-13, patios §14, bibliotecas §22, laboratorios §23-24, talleres §25, gimnasios §30, dormitorios §49-51, comedores §36/§56, sanitarios §39-42…), relaciones espaciales del §98-101 en escala 0-3 con los flujos limpio/sucio prohibidos del §102, programas mínimos del §106-109 (20/21/22/23 ítems con exteriores marcados), reglas de validación §111-112, conflictos §115, climas §116, materiales §92-94, seguridad infantil §89, punto de reunión §104-105 y fuentes OMS/UNICEF del §124; el asistente de edificación estrena el uso «Escuela secundaria» y el PROGRAMA PARAMÉTRICO por tamaño/capacidad para los cuatro usos educativos (aulas por CEIL, un aula-higiene-descanso por grupo, dormitorios colectivos de 8 plazas y comedor por comensales), con metadata y round-trip; nuevo motor domain/educacion_specs.py con validar_local/validar_proyecto (programa, relaciones, flujos, capacidad, dormitorios, comedor, escaleras §45, punto de reunión, alturas §2 y seguridad infantil) con estados honestos y los 6 temas de cálculo marcados REQUIERE_CALCULO_ESPECIALIZADO; el DNA suma 17 tipos educativos con lux y equipos, el presupuesto vivo factura PC de aula, camilla, cuna, litera y compañía sin calidad, y la GUI estrena el combo de tamaño y «Validar escuela / círculo infantil / albergue» en Herramientas (100% funcional, sin módulos incompletos) + v3.21.0 — PASILLOS POR USO HOSPITALARIO, EQUIPOS MÉDICOS EN EL PRESUPUESTO VIVO Y FICHA IMPRIMIBLE DEL LOCAL: el ancho del pasillo del asistente de edificación atiende a los LOCALES del programa (el DNA de cada especialidad trae su pasillo_m —camillas 2,40 m, carros de morgue y almacén 2,00 m, laboratorio y desechos 1,80 m, nodo informático 1,50 m— y el pasillo sube al máximo pedido citando al local culpable en el aviso), los locales de salud FACTURAN SUS APARATOS en el presupuesto vivo (categoría «Equipos» con precios de referencia visibles —tomógrafo, arco C, lámpara escialítica, cabina de bioseguridad, cámara frigorífica, SAI…— que la calidad de acabados no toca), y el asistente de local exporta la FICHA IMPRIMIBLE del local en PDF (identidad, DNA con su ficha técnica, vanos, mobiliario, instalaciones, PLANTA dibujada con muros recortados y arcos de giro, y diagnóstico)**  + v3.22.0 — ESPECIFICACIONES TÉCNICAS HOSPITALARIAS Y VALIDACIÓN DIMENSIONAL: el documento del usuario («Especificaciones técnicas integrales para locales hospitalarias», 20 secciones) entra al programa como DATOS versionados (resources/knowledge/hospital_specs.json): las 60 fichas cualitativas de locales (función, relaciones, arquitectura, electricidad, iluminación, hidráulica, HVAC, gases, radiación, presión, higiene y equipamiento), el cuadro de cotas MIN/REC de 53 tipologías con su clasificación de cota tipo A-F (la cota de programación nunca se anuncia como normativa), la matriz de prioridad funcional, los flujos incompatibles, las cotas de puertas y mobiliario, el checklist de validación de la sección 19 y las fuentes (FGI, ASHRAE 170, IAEA, OMS, AusHFG, NFPA); nuevo motor domain/hospital_specs.py con validar_local/validar_proyecto que MIDEN cada local contra su uso (superficie, ancho, altura del nivel, puertas y pasillos) y adjuntan el checklist completo distinguiendo lo geométrico de lo pendiente de cálculo o fabricante; el DNA se amplía con 40 ESPECIALIDADES NUEVAS (sala de autopsias, preoperatorio, recuperación, resonancia, ecografía, UCI pediátrica y neonatal, aislamiento, biología molecular, banco de sangre, toma de muestras, sala de procedimientos, endoscopia, hemodiálisis, farmacia estéril, rehabilitación, hidroterapia, obstetricia/partos, neonatología, pediatría, odontología, oftalmología, dermatología, cardiología, hemodinamia, medicina nuclear, anatomía patológica forense, central de gases, cuarto eléctrico, grupo electrógeno, UPS, cuarto de bombas, lavandería, ropa limpia y sucia, cuarto de limpieza, administración, archivo clínico, admisión y almacén estéril) con lux, mobiliario y equipos de referencia en el presupuesto; el asistente de local estrena el botón «Validar cotas» y la ficha PDF imprime la ficha técnica del uso, las cotas de referencia, el control §19 con su checklist y las fuentes con la advertencia normativa** + v3.23.0 — CATÁLOGO MAESTRO DE VIVIENDAS: el documento del usuario («Especificación técnica programable: catálogo maestro de viviendas», 81 secciones) entra al programa como DATOS versionados (resources/knowledge/vivienda_catalogo.json): las 30 TIPOLOGÍAS VIV-01..30 (aislada a multigeneracional), los 25 sistemas constructivos TC y 20 estructurales EST, los 30 ESTILOS con sus reglas y la MATRIZ DE COMPATIBILIDAD estilo × sistema en escala 0-3 del §27 (pares literales del documento más matriz razonada según sus reglas de estilo; advierte, NUNCA bloquea), los rangos de programación del §7 (sala 16-35 m², dormitorio principal 14-25…), las relaciones del §8 (0-3 y la X de baño-comedor a evitar), la zonificación Z001-Z008, las 30 validaciones VIV001-030, los 15 conflictos del §65 con su validación equivalente, los niveles de acabado 1-5, la progresiva por 5 fases, las jurisdicciones y el MODO CUBA, y el principio de honestidad técnica del §81 (REQUIERE_CALCULO_ESPECIALIZADO); nuevo motor domain/vivienda_specs.py con validar_vivienda() que evalúa LAS 30 COMPROBACIONES sobre el proyecto con estados honestos (medido / pendiente configurable del §66 / requiere cálculo del §81); el asistente de edificación estrena TIPOLOGÍA DE VIVIENDA con PROGRAMA PARAMÉTRICO por dormitorios y baños con los rangos del §7, las relaciones del §8 como sugerencias con puerta, avisos de compatibilidad y de medianera/escalera/fases, metadata y round-trip; el presupuesto vivo pasa a 5 CALIDADES (Económica, Media, Estándar, Premium, Lujo) y la GUI estrena el menú «Validar vivienda» con el informe completo (100% funcional, sin módulos incompletos) + v3.24.0 — ESTUDIOS DE VIVIENDA: ALTERNATIVAS COMPARABLES, MODULACIÓN Y SOLAR FV: el catálogo maestro de viviendas pasa de consultar a ESTUDIAR con tres motores nuevos de solo lectura (domain/vivienda_estudios.py) alimentados por el catálogo v1.1 (bloques comparacion_sistemas y energia_solar, valores de referencia visibles y editables del §66): ALTERNATIVAS §62-63 que para la misma entrada generan SIETE alternativas (A/B/C por nivel de acabado 1/2/4 del §51 con el sistema del proyecto y 1/2/3/4 por sistema constructivo —mampostería confinada, hormigón aporticado, steel framing y modular prefabricado—) con las métricas de comparación del §63 (superficie real o del programa paramétrico, costo índice por m2 y % relativo, meses de construcción, hormigón m3, acero kg, mampostería m2, madera m3, consumo kWh/m2·año, mantenimiento %/año, vida útil, complejidad y disponibilidad MODO CUBA) y recomendación por costo menor con compatibilidad >= 2/3 del §27; MODULACIÓN §56 que evalúa locales, muros, puertas y ventanas contra los módulos 0.60/1.20/1.25/1.50 o personalizado con % de piezas en módulo, residuo lineal acumulado y sugerencia al múltiplo inferior/superior (sugiere, no bloquea); y ENERGÍA SOLAR §38 que dimensiona FOTOVOLTAICO/SOLAR_TERMICO/HIBRIDO con las salidas del documento (número de paneles, potencia total, batería por profundidad de descarga, inversor y superficie de techo; el térmico añade colectores y tanque por ocupante) dejando la instalación definitiva marcada REQUIERE_CALCULO_ESPECIALIZADO del §81; la GUI estrena los tres menús en Herramientas con tabla comparativa, selector de módulo y formulario paramétrico que acepta coma decimal y vacíos = valor de referencia, con tooltips propios (100% funcional, sin módulos incompletos) + v3.25.0 — CENTROS COMERCIALES Y OFICINAS: el documento del usuario («Especificaciones técnicas y dimensionales - Centros Comerciales y Edificios de Oficinas» v2.0, 104 secciones) entra al programa como DATOS versionados (resources/knowledge/comercial_specs.json): 20 tipologías CC-01..10 y OF-01..10, 59 cuadros de cotas MIN/REC con unidad y nota (galerías §6, locales §7, oficinas §10, sanitarios §25, comedores §27-29, estacionamiento §45, andén §47, bicicletas §75…), relaciones espaciales del §78 en escala 0-3 con las prohibiciones duras (residuos/carga/técnicos nunca contra público), programas mínimos del §89-90, porcentajes §81, eficiencia §82 (oficinas 75-90 %, comercial 65-85 %), conflictos §95 con prioridades P01-P12, normativa seleccionable §97 y fuentes §98 (IBC 2024); el asistente de edificación estrena los usos «Centro comercial» y «Oficinas (torre/corporativo)» con PROGRAMA MÍNIMO del §89-90 medido desde los cuadros (galería 30 m², ancla 500 m²), relaciones del §78 como sugerencias, combo de tipología con metadata y round-trip, y planta tipo automática en la torre; nuevo motor domain/comercial_specs.py con validar_local/validar_proyecto (programa, relaciones y prohibiciones, porcentajes, eficiencia, estacionamiento, evacuación IBC 2024 y galería) con estados honestos y los 8 temas de cálculo marcados REQUIERE_CALCULO_ESPECIALIZADO del §101; el DNA suma 18 tipos comerciales con lux y equipos, la iluminación los cubre, el presupuesto vivo factura CCTV, rack 19", torniquete, andén y compañía sin calidad, y la GUI estrena «Validar centro comercial / oficinas» en Herramientas (100% funcional, sin módulos incompletos) + v3.27.0 — INFORME DE VALIDACIÓN EN HTML AUTOCONTENIDO: los informes de validar_vivienda / comercial / educacional se exportan a UN solo archivo .html (exporters/informe_html.py) con CSS embebido, UTF-8 declarado, cero URLs externas y cero dependencias nuevas — se abre en el navegador, se adjunta al expediente o se imprime sin ARQ_GEN —, botón «Guardar HTML...» en los tres cuadros de validación, severidades y estados honestos impresos ((pendiente) y (REQUIERE_CALCULO_ESPECIALIZADO) no se esconden), chips de metadatos, badges de resumen, locales con fallos, secciones del documento (reglas, prioridades, conflictos, normativa, documentación), escapado total del contenido y error amable ARQ-EXP-060 si la ruta no deja escribir + v3.28.0 — PRESETS DE CONFIGURACIÓN DEL ASISTENTE: la configuración del asistente (43 campos de los pasos 1/4/5 y concepción de espacios: uso, tipología, tamaño ED, lote, forma, estilo, clima, región Neufert, vanos, pasillo, instalaciones, cubierta, mobiliario) se guarda y carga como JSON local en presets/ (o ARQ_GEN_PRESETS) con formato ARQ_GEN_PRESET v1 — el PROGRAMA no viaja: niveles, locales y relaciones se regeneran desde el uso —, los valores ilegales avisan y conservan, errores amables ARQ-PRE-001..006 (corruptos marcados «ilegible» en el listado), y fila Guardar/Cargar/Eliminar en el paso 1 con repaint de widgets; lo que otros cobran en plan Business aquí es local, gratis y auditable + v3.29.0 — COMPARADOR DE VARIANTES DE PLANTA: matriz N variantes x 9 columnas (nº, variante, esquema, cabe en lote, puntos, área m², coste PRECONS vivo, coste/m² y avisos) ordenada por puntuación con líder por coste/m2, texto cp1252 y CSV «;» utf-8-sig para Excel, botón «Comparar variantes» en el paso 6 junto al generador, sólo lectura, y sin coste adjunto lo DECLARA en vez de inventar (100% funcional, sin módulos incompletos) + v3.30.0 — SERVICIOS DE VIVIENDA: piscina §45 como SISTEMA INDEPENDIENTE (volumen, renovación y caudal de filtración, bomba por rendimiento, skimmers, impulsión, focos LED, checklist de seguridad y 7 equipos en CUP), acústica §46 que MIDE los muros compartidos fuente-dormitorio por solape colineal y el vano perimetral por sub-segmento, con soluciones de referencia (material, espesor, doble tabique, R_w tipo DB-HR, vidrio acústico de fachada y aislamiento de cubierta), y plan domótico §39 por SISTEMAS y ELEMENTOS con 16 conteos sobre el modelo, monitor doble con solar FV y RED/PANEL/ALIMENTACION como diseño; registro versionado ARQ_GEN_VIVIENDA_SERVICIOS, tres menús en Herramientas con Guardar HTML, tablas genéricas en el informe HTML y errores amables ARQ-PIS/ARQ-VSR (100% funcional, sin módulos incompletos) + v3.31.0 — P2: DXF R12 ASCII de máxima compatibilidad (LINE/ARC/TEXT clásicos sin LWPOLYLINE, modelspace con un bloque por nivel, AC1009; menú Archivo y CLI --r12; el R2010 intacto) y COSTE LIGADO AL CHECK: los tres informes de validación llevan la instantánea SOLO LECTURA del presupuesto PRECONS activo (directo, transporte, indirectos, beneficio, total y coste/m2) en el cuadro y en la sección «Coste del proyecto» del HTML, y sin presupuesto no se inventa nada (100% funcional, sin módulos incompletos) + v3.32.0 — P3: MULTIPLICADORES DE NIVELES / PLANTA TIPO REPETIDA: cada nivel del asistente lleva su «repeat» (1 = planta única, techo 50) y pides «×N» — niveles expandidos con nombres únicos (dedup ante colisión), locales duplicados por copia con relaciones globales intactas, cotas que se recorren solas, y build_plan y generate_variants que expanden solos para que plan, cantidades, coste y variantes salgan sobre el EDIFICIO entero; paso 2 con columna Repetir, entrada validada, botón «× Repetir seleccionado...» y resumen «N niveles · altura total» (100% funcional, sin módulos incompletos) + v3.33.0 — HERRAMIENTAS DE DIBUJO Y ASISTENTE DE SERVICIOS: en el lienzo, MUROS, ESPACIOS, ZONAS, PUERTAS y VENTANAS nacen a DOS CLICS como en ArchiCAD/AutoCAD (sección «Dibujar» de la paleta con espesor y altura del muro, uso del DNA, nombre, dimensiones de puerta y ventana con umbral; imán a vértices y rejilla con el puntero AutoCAD que ya tenías, vista previa del rectángulo y del muro con su espesor) — todo son ENTIDADES REALES por los caminos oficiales (auditoría, undo persistente, QTO, presupuesto, validación dimensional y DXF/IFC los ven solos) y las REGLAS DEL PROYECTO AVISAN sin bloquear (área bajo el mínimo del uso, puerta más estrecha que la del uso, ventana que no llega al hueco que pide el uso —habitables 1/6, húmedos 1/25—, zona sin locales); y el ASISTENTE DE SERVICIOS aparte (botón «Servicios» + menú Herramientas) crea SERVICIOS COMPLETOS POR TEMÁTICA cuando solo te interesa el servicio y no la edificación entera: catálogo versionado ARQ_GEN_SERVICIOS con 6 servicios y 46 locales (ANATOMÍA PATOLÓGICA completa: recepción de cadáveres, cámara mortuoria, necropsias, lavado de instrumental, histotecnología, sala de corte/macroscopía, archivo de bloques, oficina de patólogos, vestuarios y espera; laboratorio clínico, imagenología con salas de RX replicables y TAC, hemodiálisis con planta de tratamiento de agua, CEyE en un sentido y farmacia), PARÁMETROS DINÁMICOS por servicio (necropsias/día, piezas/día, puestos, quirófanos servidos, camas, conmutadores bool), PROGRAMA dimensionado (área base + área por parámetro acotada a mínimos/máximos, dimensiones sugeridas, flujo sucio/limpio/estéril, requisitos técnicos y adyacencias), VALIDACIÓN FUNCIONAL contra el DNA (áreas, críticos presentes, adyacencias a verificar, puertas recomendadas de los críticos, flujos y notas) y APLICAR AL NIVEL: zona SERVICE, pasillo CORRIDOR de 2,40 m con los locales a dos bandas, locales reales con su uso del DNA, relaciones adjacent_to y opción de trazar muros; proyecto sin niveles = edificio mínimo creado al vuelo (100% funcional, sin módulos incompletos) + v3.34.0 — DESDE DIBUJO: GENERACIÓN INVERSA: del contorno del área (espacio dibujado a dos clics, rectángulo o polilínea cerrada de un DXF) a la edificación o al servicio completo: inferencia de forma y medidas (área, caja, perímetro, vértices antihorarios; rectángulo/ortogonal/polígono), programa por servicio del catálogo o por usos del DNA con cantidades, verificación honesta de si los locales entran en el área (pasillo a dos bandas y comprobación local a local dentro del polígono), crecimiento en altura en niveles apilados con recinto de escalera según Blondel, y generación real de edificio, niveles, pasillo, locales, escalera, zona, relaciones y muros opcionales + v3.35.0 — SERVICIOS MÉDICOS: catálogo v2.0 del asistente de servicios con el documento «servicios médicos» (morgue, tomografía computarizada, UCI, cuidados intermedios y urgencias, y anatomía patológica enriquecida a 16 locales; grupos con subtotales, criticidad por niveles, puertas y circulación del catálogo, validación con prohibidas y separación limpio/sucio, y los documentos: ficha de local §30, matriz de instalaciones §22, relaciones entre servicios §17, flujos §18 y 20 reglas de generación §24) + v3.36.0 — CATÁLOGO UNIVERSAL DE SERVICIOS: el asistente crece de 11 a 34 servicios y ~400 locales con el campo sector (salud, educación, administración, comercio y hostelería, deportivo, cultural, residencial asistido y logística): 12 servicios de salud nuevos (consulta externa, bloque quirúrgico, hospitalización, maternidad, cardiología/hemodinamia, endoscopia, medicina nuclear, microbiología, banco de sangre, rehabilitación, salud mental, odontología) y 11 de otros usos (círculo infantil, primaria, secundaria, oficinas, restaurante, supermercado, hotel, centro deportivo, centro cultural, residencia de adultos, almacén logístico); filtro por sector en ambos asistentes y EXPLORADOR DEL CATÁLOGO en «Desde dibujo»: el contorno dibujado se prueba contra TODOS los servicios y lista los que caben en un nivel primero, con recintos-nave para locales de superficie grande) + v3.37.0 — DXF REAL: unidades $INSUNITS (milímetros, centímetros, pulgadas, pies...) escaladas a metros, cierre geométrico de las polilíneas del CAD (primero == último), contorno de planta de N lados descompuesto en N segmentos de muro, polilíneas abiertas de muros como un segmento por arista, textos vacíos contados y avisados, cierre automático de contornos casi cerrados en «Desde dibujo» y el flujo desde dibujo → servicio verificado con el plano real «AP Y MORGUE.dxf»: contorno ortogonal de 174.91 m2, explorador del catálogo, MORGUE crece a 2 niveles con escalera de Blondel y generación real del edificio) + v3.38.0 — DIBUJO Y NAVEGACIÓN ESTILO CAD CLÁSICO (lecciones de IngeCAD integradas por reimplementación propia: gramática de coordenadas por teclado 10,5 / @10,5 / @10<45 / 25 y =expresiones seguras; LÍNEA DE COMANDOS abajo con historial (flechas), autocompletado, Enter vacío que repite, F2 ventana de texto y QC calculadora; ZOOM VENTANA (Z) con marco, ZOOM ANTERIOR (ZP) con pila de 32 vistas, ZE encuadrar, rueda a 1.2 por muesca anclada al cursor y encuadre honesto del lienzo vacío; SELECCIÓN VENTANA/Cruce clásica azul/verde por arrastre con eco «N seleccionados»; familia de REFERENCIAS extremo/intersección/medio/centro con precedencia y marcadores amarillos (PER y más-cercano opt-in); REJILLA ANIDADA adaptativa con mayores cada 5 pasos y banda antiflip; MAYÚS = orto temporal; DYN (F12) con distancia y ángulo junto al cursor; aliases MU/ES/ZO/PU/VE de dibujo y coordenadas que BYPASS del snap). + v3.39.0 — DESDE DIBUJO REFORZADO (lecciones del asistente dinámico: validación previa del contorno con autointersecciones, apertura y dimensiones imposibles; checklist [OK]/[AVISO]/[ERROR] antes de generar; contratos PlanRequest/PlanResult; alternativas 1/3/5 con métricas comparables y puntuación explicada; decisiones registradas «¿por qué este local aquí?» sin IA; reemplazo del edificio previo con aviso; configuraciones y estado del asistente guardados en el proyecto; quick-spec en una línea sin IA; y patio exterior como opción experta) + v3.39.1 — HILO SEGURO SQLITE (hotfix del «ERROR AL IMPORTAR» del plano DXF/DWG: la conexión del proyecto se abre en el hilo principal y la importación corre en un hilo de fondo, así que sqlite3 rechazaba el cruce con «SQLite objects created in a thread can only be used in that same thread»; ahora check_same_thread=False y un candado reentrante que serializa execute/commit/rollback/close hacen que la MISMA conexión atienda a la GUI y a los hilos de fondo en cola ordenada) + v3.40.0 — ENCAJE ESTRICTO AL POLÍGONO (la parcela importada o dibujada se tesela en contenedores reales — franjas de barrido exactas para L/U/T, mayor rectángulo inscrito para inclinados — y el empaquetado ocurre DENTRO con verificación local a local: nada se sale del polígono, el ala de la L se aprovecha con locales, los locales más profundos que cualquier franja usan la unión de dos contenedores contiguos, los niveles sin pasillo se declaran, el informe muestra estrategia, contenedores y aprovechamiento %, y el camino histórico de caja envolvente queda como opción experta) + v3.41.0 — PROGRAMA ADAPTABLE (el cambio de uso en edificaciones existentes: SELECCIÓN de qué locales de cada temática y uso social se aplican en el proyecto con aviso documentado de los excluidos, y AJUSTE DIMENSIONAL por niveles — mínimo solo hasta la norma, medio hasta un 15 % bajo ella y estricto hasta un 35 % con lados desde 1,50 m — mediante una escalera de reducción iterativa que re-empaqueta hasta entrar, declara local a local la reducción y los locales BAJO LA NORMATIVA, y avisa ARQ-DDI-010 cuando ni el máximo entra) + v3.42.0 — PASILLOS Y FILTROS (calibrado con el plano real AP + morgue del hospital pediátrico y su dibujo de la solución esperada: el empaquetado RESERVA PRIMERO el pasillo distribuidor del contenedor y los locales lo sirven cambiando FONDO por ANCHO conservando su área, las filas se RELLENAN hasta los bordes con los techos del catálogo, el orden de colocación sigue el FLUJO del servicio — sucio al fondo, público en la entrada — con el FILTRO sanitario como barrera entre zonas y aviso cuando un nivel mezcla flujos sin filtro, y la COMPACTACIÓN con ajuste medio/estricto baja de niveles hasta teselar en una planta como el dibujo de referencia) + v3.43.0 — VIVIENDA SOCIAL (los 4 planos de referencia del usuario: DNA de vivienda con Sala de 9 m2, Comedor de 6 y LAVADERO DOMÉSTICO separado del hospitalario; «1 nivel» como TOPE DURO que COMPACTA con la escalera de reducción antes de crecer y lanza ARQ-DDI-011 nombrando lo que no cabe; modo SALA DISTRIBUIDORA sin pasillo para casas de <= 60 m2; CHAFLANES a 45 grados hacia la sala con el triángulo absorbido y documentado; y MOBILIARIO automático doméstico en los locales generados) + v3.43.1 — PATIO DOMÉSTICO Y CHAFLANES (defectos descubiertos sondeando el motor con las 9 imágenes de referencia nuevas: el «patio» del quick-spec ya no es el ESCOLAR de 100-300 m2 que devoraba el 64 % de la villa 50x100 y lanzaba ARQ-DDI-011 en la de 50x90, sino el DOMÉSTICO de 4-9 m2; y los chaflanes a 45 grados disparan también SIN selección de locales midiendo contra el mínimo del DNA — el caso Z de 48 m2 ya no depende de una colisión accidental de códigos; test_178 + check 87) + v3.44.0 — TODO TERRENO: LO QUE LAS IMÁGENES PEDÍAN Y EL MOTOR NO TENÍA (Fase A: VESTIDOR W.I.C en el DNA y palabras lobby/foyer/vestidor/wic/closet en el quick, umbral del modo sala distribuidora PARAMETRIZABLE para villas grandes con lobby y chaflanes que se abren hacia el lobby; Fase B: CHAFLÁN PROPIO DE FACHADA (bay window) — la esquina del local que cae en el contorno se corta a 45 grados con cateto 0.6 m y la pérdida la absorbe el propio local, como las unidades de hotel de las imágenes; Fase C: MULTI-ALA Y MULTI-UNIDAD — ajustar_zonas reparte UN programa entre N contornos con hubs al ala principal y repartir_rejilla repite la MISMA unidad con corredor central (edificio tipo), ambas se aplican como UN edificio con aplicar_zonas; Fase D: GEOMETRÍA CURVA/RADIAL — plan_radial genera N sectores alrededor de un núcleo circular con corredor anular y arcos por cuerdas (torres y hospitales radiantes); Fase E: ELEVACIONES PARAMÉTRICAS — 4 pieles (paños, ventana corrida, brise, perforada) con PNG y DXF R12 por capas; GUI: chaflán propio + distribuidora hasta m2 + botones Elevaciones y Planta radial; test_179-183 + checks 88-91) + v3.45.0 — TORRE EN Y REAL CON NÚCLEO CENTRAL Y MÁS PIELES: plan_y genera la Y de las imágenes de referencia (núcleo circular con el vestíbulo, 3 alas a 120 grados —2 barra doble, 4 X— con corredor por ala y locales a ambos lados, cabecera transversal opcional, contorno Y real por cuerdas, ARQ-DDI-012 si las alas solapan junto al núcleo) aplicable como edificio con los corredores por ala y el mobiliario omitido, y el catálogo de pieles de elevacion pasa de 4 a 12 (hexagonal, diagrid, celosia, gradiente, fins, cortina, bandas y parametrica) con PNG y DXF R12 intactos; GUI con botón Torre en Y; test_184-185 + checks 92-93) + v3.46.0 — EXPORTAR TODO A BIM: paquete IFC4 + DXF R2010 + DXF R12 + JSON + CSV + XLSX + SVG en una carpeta con un clic, botón «Exportar BIM (IFC+DXF)» en el asistente Desde dibujo, alturas IFC reales de los espacios y el fix del ARQ-DOM-048 que bloqueaba los muros de la torre en Y y la radial (2559 pruebas, 94 checks) + v3.47.0 — HOSPITAL EN X REAL Y Y DESIGUAL: plan_x con dos barras cruzadas, hub central en el cruce (el vestíbulo reparte los 4 corredores) y contorno unión de 12 vértices totalmente ortogonal; largos_alas desiguales en plan_y (la estrella radial del hospital oncológico); NIVELES de planta tipo en plan_x/plan_y/plan_radial (sótano científico + plantas típicas); botón «Hospital en X (v3.47)» en la GUI (2579 pruebas, 96 checks) + v3.48.0 — FASE A TAURI: sidecar JSON-RPC (app/rpc_server.py + CLI rpc), esqueleto Tauri 2 con puente stdin/stdout y CI con actions pinned por SHA + v3.49.0 — FASE B RUST: acelerador opt-in (geometría de encaje 1:1 en PyO3 ~49x más rápida y XLSX nativo con fallback openpyxl) sin cambiar el determinismo del motor (2613 pruebas, 100 checks) + v3.50.0 — FASE C: UI WEB COMPLETA en Tauri (sidecar con 13 métodos RPC, catálogo DNA, las 6 formas, sesión LRU, exportación real desde la web, shell con carpeta de descargas; suite 2.644 / selftest 103)

Versión 3.50.0 · Python 3.13 · Windows · 100% offline tras instalar dependencias

---


## Novedades v3.50.0 — FASE C: LA UI WEB COMPLETA SOBRE TAURI (el canal FASE A se convierte en interfaz)

Autorizada la FASE C del plan Tauri: la pestaña web ya no es una demo, es la INTERFAZ COMPLETA del flujo generativo. El motor Python queda intacto; lo que cambia es cómo se le habla.

- SIDECAR AMPLIADO (app/rpc_server.py, 13 métodos JSON-RPC): `catalogo` (los 116 usos del DNA para el selector de fichas), `generar_radial` / `generar_y` / `generar_x` / `generar_zonas` / `generar_rejilla` (las 6 formas de generar), `aplicar_exportar` (aplica el plan a un proyecto headless y escribe IFC/DXF/DXF_R12/JSON/CSV/XLSX/SVG reales + instantánea), `proyecto_abrir` (vista previa de snapshots) y SESIÓN LRU (8 análisis íntegros por id, la web solo viaja ligera). Los errores de dominio llegan como -32602 con `data.codigo` (ARQ-DDI-012...) y `data.accion` para pintarlos en la UI. El contrato FASE A queda intacto (rect siempre, determinismo vigente sin el id).
- UI WEB COMPLETA (src/, vanilla sin npm): 7 vistas — Inicio (estado del motor, acelerador Rust/Python), Programa (quick-spec o fichas con catálogo DNA), Contorno (presets rect/L/T/U + vértices a mano con medidas y vista previa), Forma (encaje simple con ajuste ideal/mínimo/medio/estricto + patio, radial, torre Y con alas desiguales, hospital X con ángulo, multi-ala con roles, rejilla 3x2), Resultado (planta SVG poligonal por niveles/alas con la paleta de flujos, KPIs con métricas explicadas §25/26, tabla de locales, chaflanes y avisos), Exportar (carpeta, formatos, muros, mobiliario, tabla de archivos resultantes) y Proyecto (lector de instantáneas con recuentos). Estado de formulario en localStorage.
- SHELL TAURI (src-tauri/): nuevo comando `carpeta_descargas` (el path resolver es núcleo de Tauri 2, sin plugins) para proponer el destino de exportación; ventana 1360x900 «ARQ GEN (Fase C)»; conf v3.50.0.
- QA: selftest 103 checks (+3: catálogo/radial por RPC, exportación real IFC+DXF+XLSX desde la sesión, compuestos multi-ala y rejilla aplicados y exportados) y suite 2.644 pruebas (test_191 FASE C: 31 nuevas — contrato de las 6 formas, determinismo, sesión LRU, errores con data, exportación real en disco, sidecar POR PROCESO y empaquetado del frontend); el humo del frontend se ensayó en navegador headless sin un solo error de consola.
- CI: la política SHA-pinned se mantiene íntegra; el resumen del run de GitHub informa el check FASE C del exe.

## Novedades v3.49.0 — FASE B RUST: PUERTOS SELECTIVOS CON PARIDAD 1:1

Aprobada la FASE B del plan Tauri (tras la FASE A): las piezas calientes corren ahora también en Rust SIN cambiar el modo por defecto. El crate `rust/arqgen_core` (PyO3, compilado con maturin) nace como acelerador del motor Python y es el mismo núcleo que el futuro shell Tauri montará dentro del binario Rust:

- **Geometría de encaje en Rust**: puerto 1:1 de `domain/encaje.py` (es_ortogonal, seccion_en, contenedores_ortogonales, rectangulo_inscrito, area_poligono, comparten_banda) — `_seccion_en` se invocaba O(niveles² × 7) veces en el «Desde dibujo»: **medido 49× más rápido** (1.245 ms → 25,7 ms en contorno de 40 vértices). Mismo orden de operaciones, redondeo `round(x,4)` estilo Python (half-to-even) y sorts estables por área redondeada: paridad exigida a 1e-9.
- **XLSX nativo en Rust**: `rust_xlsxwriter` no existe como binding PyPI, así que el equivalente funcional vive en el crate (`xlsx_escribir`): OOXML con cabecera azul 2F5496 + fuente blanca en negrita centrada, pane congelado A2 y anchos — legible por openpyxl y con paridad de celdas vigiada contra el escritor clásico, que queda como fallback transparente.
- **Política opt-in**: por defecto el motor es Python puro (determinismo v3.48.0 intacto); se activa con `ARQ_GEN_ACELERADOR=rust` o `usar_rust=True`. Sin crate instalado nada se rompe: el switch cae a Python sin explotar. Puente en `core/acelerador.py` (única pieza que sabe si el módulo existe).
- **QA**: tests/test_190 (15 pruebas: piezas, nivel alto con estrategia/avisos, XLSX con formato, política opt-in, benchmark informativo), selftest checks 98-100 (paridad del encaje, XLSX re-leído con formato, política y versión) → **2.613 pruebas y 100 checks verdes**.
- **CI**: compilar.yml ganó el paso opcional «Acelerador Rust FASE B» (maturin en el runner Windows + wheel instalado antes de PyInstaller, continue-on-error: si Rust falla el exe sale en modo Python y el run sigue verde); el resumen informa el modo real del exe. Sin actions nuevas: la política SHA-pinning sigue cumplida. Detalles en `LEEME_FASE_B_RUST.md`.

## Novedades v3.48.0 — FASE A TAURI: EL MOTOR HABLA JSON-RPC (SIDECAR)

El usuario aprobó la FASE A del «ARQ GEN TAURI.txt» v3.0 (Tauri 2 + núcleo Rust + Python sidecar) y además el repo de GitHub exige actions pinned a SHA completo. v3.48.0 entrega el canal completo y el esqueleto:

- **Sidecar JSON-RPC 2.0 (app/rpc_server.py, nuevo)**: el motor se convierte en proceso esclavo del shell Tauri — 1 petición por línea de stdin, 1 respuesta por línea de stdout, UTF-8 puro, stderr solo diagnóstico. Métodos: `ping` (latido con versión), `version`, `selftest` (los 97 checks), `generar_quick` (quick-spec + contorno + ajuste + chaflanes → planta recortada al contrato de la UI: niveles, totales, reparto con locales poligonales, chaflanes y avisos) y `generar_edificacion` (fichas hospitalarias/colectivas). Errores JSON-RPC completos: -32700/-32600/-32601/-32602/-32603; un fallo NO tumba el canal. CLI: `ARQ_GEN.exe rpc` arranca el servidor lean (sin bootstrap del catálogo).
- **Esqueleto Tauri 2 (src-tauri/, nuevo)**: `Cargo.toml` + `tauri.conf.json` (frontendDist estático `../src`, withGlobalTauri, bundle con el motor como recursos `engine/`, instalador NSIS) y `src/main.rs` que resuelve el binario del motor (resource_dir → exe → env ARQ_ENGINE_PATH), lo lanza con stdin/stdout en pipe (sin ventana de consola en Windows) y expone `invoke('rpc', {method, params})` a la web. Frontend de prueba (`src/`, vanilla HTML/JS/CSS sin build): estado del motor, quick-spec editable, contornos presets, chaflanes, y PLANTA SVG por nivel con la paleta de flujos del motor.
- **CI Tauri (.github/workflows/compilar_tauri.yml, nuevo)**: compila el sidecar con PyInstaller, valida el canal RPC real (ping por proceso), monta el ejecutable Windows + instalador NSIS con Tauri — actions 100% pinned a SHA completo (checkout v4.4.0, setup-python v5.6.0, upload-artifact v4.6.2, download-artifact v4.3.0, gh-release v2.6.2) por la política del repo; compilar.yml también quedó pinned.
- **QA**: suite test_189 (19 pruebas: protocolo in-process + proceso real por `main.py rpc` + contrato CLI), selftest check 97 (ping, -32601 y generar_quick con polígonos) → **2.598 pruebas y 97 checks verdes**.

## Novedades v3.47.0 — HOSPITAL EN X REAL, ESTRELLA DESIGUAL Y PLANTA TIPO EN N NIVELES

El usuario envió dos hospitales de referencia más (el oncológico radial de Mohamed Rabea con núcleo circular y zonas por planta, y el hospital en X con hub central y patios triangulares entre brazos) y pidió «seguir incluyendo estos contornos y circulación interna y ubicación de espacios interiores». v3.47.0 entrega los dos patrones completos, con circulación y espacios:

- **plan_x — HOSPITAL EN X REAL (domain/radial.py)**: dos barras perpendiculares de `largo_barra` × `ancho_barra` que se CRUZAN por el centro; el cruce es el **HUB central** que ocupa el VESTÍBULO/ENTRADA del programa (como la recepción de la referencia) y reparte el acceso a los **4 corredores** (uno por brazo, campo `ala`), con locales a ambos lados (8 filas, colocación global greedy igual que la Y). `angulo` rota la X entera (45° = X diagonal de la referencia, 0° = cruz en +). **Contorno = UNIÓN real de las dos barras** (12 vértices: 8 esquinas de puntas + 4 entrantes del cruce), 100% ortogonal y SIN aristas degeneradas: el trazado de muros y el BIM funcionan a la primera (regresión del ARQ-DOM-048 cubierta).
- **Estrella radial desigual (largos_alas)**: `plan_y` acepta `largos_alas=[18, 13, 20, 11]` — alas de longitudes distintas alrededor del núcleo circular, el patrón del hospital oncológico; presupuesto, filas, cabeceras y contorno Y real se calculan por ala; los corredores resultan de largos desiguales y todo cierra exacto.
- **NIVELES de planta tipo (1-20)**: `plan_x`, `plan_y` y `plan_radial` aceptan `niveles=N` — la planta tipo se repite en N plantas (sótano de servicios / planta científica / plantas típicas del hospital de referencia); `aplicar_plan` crea las N plantas con sus espacios y muros, las métricas dividen por niveles (ocupación honesta) y el BIM sale con N storeys. Aviso explícito de reservar escaleras.
- **GUI**: botón «Hospital en X (v3.47)» (largo, ancho, corredor, cabecera, rotación y niveles) y la Torre en Y ahora pide «Largos de alas separados por coma» y «Niveles de planta tipo».
- **Errores explicables**: ARQ-DDI-012 (brazo corto, barra/ancho/corredor fuera de rango, cabecera que no deja filas, niveles fuera de 1-20, hub sin vestíbulo, largos_alas incompleto) y ARQ-DDI-011 (el programa no cabe en las filas de los brazos).

### QA de la versión

- **tests/test_187_plan_x.py** (17 pruebas): X a 45° y cruz en + con contorno unión de 12 vértices sin aristas degeneradas, hub = cruce con el vestíbulo (área = ancho²), 4 corredores con relaciones por brazo, mínimos del DNA y filas cerradas, sin solape por centroides, determinismo, planta tipo en 3 niveles (plantas idénticas, altura total = N·h, ocupación honesta), 8 errores explicables, aplicar_plan con muros en 3 niveles. **tests/test_188_y_desigual_niveles.py** (13 pruebas): estrella desigual con corredores de largos [7, 9, 14, 16], contorno que cierra exacto, cabeceras por ala, retrocompatibilidad (sin largos = uniforme), niveles en plan_y y plan_radial, aplicar_plan con 2 plantas. **Selftest: checks 95 y 96** (X con 3 plantas tipo; estrella desigual + radial de 2 niveles). Suite completa: **2579 pruebas** en Xvfb, 0 fallos.

---

## Novedades v3.46.0 — EXPORTAR TODO LO GENERADO A BIM (IFC) + DXF

Petición literal del usuario: «no tengo una manera de exportar todo lo generado a un formato BIM ó IFC, ó dxf». La sonda end-to-end (los 5 caminos de generación v3.43–v3.45 aplicados a un proyecto real y exportados con ExportService) probó que el pipeline DXF/IFC ya existía y era sano (0 referencias colgantes, chaflanes con hasta 10 vértices y la Y con 138 por perfil), pero también destapó UN BUG que bloqueaba el BIM completo y DOS carencias de usabilidad. v3.46.0 corrige los tres:

### El bug que bloqueaba el BIM (ARQ-DOM-048)

- **Torre en Y y radial con «Trazar muros» marcado no se podían generar**: el contorno Y lleva la esquina de cada ala en el MISMO punto que el extremo de su arco (longitud EXACTAMENTE 0.0 en 5 costuras) y `create_wall` rechaza muros de longitud nula — abortaba TODO el edificio y con él cualquier exportación BIM. Corregido en la fuente (`domain/radial.py`: `_dedup_poligonal` limpia el contorno Y y el cierre del círculo radial) y con cinturón de seguridad en `aplicar_plan`/`aplicar_zonas` (aristas < 0.1 mm omitidas y documentadas en avisos, para cualquier plan presente o futuro). La Y estándar queda con 39 vértices limpios y traza 248 muros; la radial, 2018.

### Fase B — paquete «Exportar TODO» (services/export_service.py)

- **`ExportService.exportar_todo(ctx, carpeta, nombre_base, formatos)`**: escribe en UNA carpeta, con UNA llamada, IFC4 (BIM) + DXF R2010 + DXF R12 + JSON + CSV + XLSX + SVG. Cada formato se intenta por separado: si uno no puede (proyecto sin geometría aún), queda en `errores` con su mensaje y los demás siguen — nunca más un aborto en cascada.

### Fase C — GUI: el gesto único y el aviso amable

- **Archivo → Exportar → «Exportar TODO (BIM + planos)…»**: pide carpeta y muestra el resumen con tamaño de cada archivo y los formatos no exportados (si los hubiera).
- **Botón «Exportar BIM (IFC+DXF)» en el asistente Desde dibujo** (junto a «Generar»): sirve para TODO lo generado (viviendas, patios, chaflanes, alas, rejilla, radial, torre en Y) porque exporta el PROYECTO. Si aún no se pulsó «Generar», avisa «Todavía no hay edificación en el proyecto: pulse Generar» en lugar del error ARQ-EXP-031 seco.

### Fase D — alturas BIM reales (exporters/ifc_exporter.py)

- Los **IfcSpace** heredan la altura de su **IfcBuildingStorey** (antes 3.0 m fijos): un nivel de 3.2 m ya llega con 3.2 m a usBIM/BIMvision/Solibri Anywhere/Revit.

### QA de la versión

- **tests/test_186_exportar_bim_todo.py** (10 pruebas): Y y radial con muros (regresión DOM-048), contorno Y sin costuras, dedupe unitario, paquete completo de 7 archivos, degradación en proyecto vacío, zonas = 2 storeys, altura IFC del nivel y GUI cableada. **Selftest: check 94** (paquete de 7 formatos sobre una torre en Y con muros). Suite completa: **2559 pruebas** en Xvfb, 0 fallos.


## Novedades v3.45.0 — TORRE EN Y REAL CON NÚCLEO CENTRAL Y MÁS PIELES DE FACHADA

El usuario pidió las dos formas que quedaban fuera del catálogo: las **formas multi-ala complejas** (la Y REAL con núcleo central de la residencia 24dab94 y del hospital oncológico 04ed0b de la rama Ejemplos) y **más pieles de fachada** para las torres de las imágenes (malla hexagonal, diagrid, celosía, perforación paramétrica...). v3.45.0 entrega ambas en dos fases, con 29 pruebas nuevas y 2 checks nuevos (93 en total):

### Fase A — plan_y: la TORRE EN Y REAL (domain/radial.py)

- **Núcleo circular central** con el VESTÍBULO del programa (como el lobby de las torres), Disco de radio paramétrico; la escalera se reserva con el asistente de Escaleras.
- **N alas radiantes** (3 = la Y a 120 grados; 2 = barra doble; 4 = torre X; 2-8 admitidos) con **corredor por ala** (pasillos múltiples con el campo `ala`) y **locales a ambos lados** del corredor, rotados al ángulo de su ala.
- **Contorno Y REAL**: arcos por cuerdas entre los hombros de las alas + brazos rectangulares; no una caja: la planta se ve como el plano de referencia (44 vértices en la Y estándar).
- **Reparto determinista**: el programa se escala hasta llenar las filas (nunca por debajo del mínimo del DNA) y cada local va a la fila con MÁS HUECO restante (bin-packing 1D de 2·n filas): se llena una ala antes de abrir la siguiente y los dos lados van pareja; el ÚLTIMO local de cada fila crece hasta cerrar exacto con la cabecera o el frente.
- **Cabecera transversal opcional** (`cabecera_m`): el tramo final del ala como sala de ancho completo con el uso mayor del programa (la cabeza del hospital en Y).
- **Errores explicables**: ARQ-DDI-012 si las alas se solapan junto al disco (el mensaje da el radio mínimo: `(ancho_ala/2)/sin(π/n_alas)`), si el núcleo no lleva vestíbulo, o si n_alas/ala/corredor/cabecera salen de rango; ARQ-DDI-011 si el programa no cabe en las filas.
- **aplicar_plan** crea UN edificio: cada local queda adyacente al CORREDOR DE SU ALA (mapa por `ala`), el mobiliario automático se omite (geometría radiante) y el DXF/metricas funcionan tal cual. Mejora transversal: `_locales_dentro` prueba las piezas SOLO-poligonal por su centroide (las métricas de plan_radial v3.44 ahora salen honestas al 100% de cumplimiento) y `texto_inferencia` tolera las formas sin caja (radial/Y).

### Fase B — 12 pieles de fachada (domain/elevaciones.py)

El catálogo pasa de 4 a **12 pieles deterministas**, todas con render PNG y DXF R12 por capas FACH_* intactos:

| Piel (v3.45) | Patrón |
|---|---|
| `hexagonal` | malla de celdas hexagonales planas (6 líneas por celda), filas desplazadas |
| `diagrid` | retícula diagonal cruzada por planta (estructura diamante), malla pura |
| `celosia` | lamas verticales finas + 2 horizontales por planta (breeze block), malla pura |
| `gradiente` | perforación circular con radio DECRECIENTE con la altura (densidad de asoleamiento) |
| `fins` | aletas verticales profundas (doble línea a 0.12 m) con vidrio corrido |
| `cortina` | muro cortina: montantes finos a todo el alto + banda opaca (spandrel) |
| `bandas` | banda opaca inferior + vidrio corrido con parteluces alternos |
| `parametrica` | paneles facetados con ancho aparente variable (efecto de torsión) |

La puerta de acceso se dibuja solo en las pieles con paños (`panos`, `brise`, `fins`); las de malla corrida no la llevan (documentado en el módulo).

### GUI, pruebas y QA

- **GUI**: nuevo botón «Torre en Y (v3.45)» en el asistente Desde dibujo (pide radio del núcleo, alas, largo, ancho, corredor y cabecera; centro = centroide del contorno) y el prompt de Elevaciones muestra las 12 pieles.
- **Tests**: `test_184_torre_y.py` (16) y `test_185_pieles_extra.py` (13): geometría por franja des-rotada, sin solape (ningún centroide dentro de otra pieza), mínimos del DNA, determinismo, cabeceras, 011/012, aplicar_plan sin mobiliario, métricas honestas, celdas de 6 líneas, malla pura, radio decreciente, montantes irregulares, PNG/DXF.
- **Selftest**: checks 92 (torre en Y) y 93 (pieles nuevas) → **93 checks**.
- **Suite completa**: 2539 pruebas (2467 de v3.44.0 + 29 nuevas de test_184/test_185 más los ajustes de pines y test_126 a 93 checks) bajo Xvfb :98 con 0 fallos y 1 skip preexistente.

---

## Novedades v3.44.0 — TODO TERRENO: RADIAL, ALAS, FACHADAS Y LO QUE FALTABA EN VIVIENDA

Las imágenes de referencia de la rama Ejemplos pidieron cuatro cosas que el motor no tenía; esta versión las entrega TODAS, en 5 fases con la suite verde en cada paso.

**Fase A — LOBBY Y VESTIDOR (vocabulario completo de vivienda).** El DNA trae VESTIDOR (W.I.C: mínimo 2.0 m2, preferible 4.0, lado 1.2, junto al dormitorio) sin tocar el vestidor de PERSONAL (DRESSING_ROOM, 6-12 m2). La especificación rápida reconoce «vestidor/vestidores», «wic», «closet», «lobby/lobbys» y «foyer». El umbral del MODO SALA DISTRIBUIDORA es parametrizable (`distribuidora_max_m2`): una villa de 100 m2 con lobby va SIN pasillo pidiendo tope 120. Y sin sala, el HUB de los chaflanes es el LOBBY: las unidades con hall cortan esquinas hacia el vestíbulo.

**Fase B — CHAFLÁN PROPIO DE FACHADA (bay window).** Las unidades de hotel de las imágenes cortan la esquina del PROPIO recinto a 45 grados en fachada. Ahora `chaflan_propio` lo hace: la esquina del local que cae EN EL CONTORNO se corta con cateto 0.6 m (nunca por debajo del mínimo del DNA, tope 2 cortes opuestos por local y 6 por nivel) y la pérdida la absorbe el propio local con poligonal real de 6 vértices. En auto (None) dispara SOLO en niveles sin sala/lobby; False lo desactiva; True lo fuerza además de los cortes hacia la sala. APLICAR_PLAN crea el espacio con la poligonal.

**Fase C — MULTI-ALA Y MULTI-UNIDAD.** `ajustar_zonas` reparte UN programa entre N contornos (alas) con reparto determinista por déficit de área: los hubs públicos (vestíbulo/entrada/sala) van al ala principal y un ala que no admite su parte lanza ARQ-DDI-012 nombrando su rol. `repartir_rejilla` divide un contorno rectangular en 2 bandas con CORREDOR CENTRAL y repite la MISMA unidad en cada celda (la planta tipo del edificio plurifamiliar ruso). `aplicar_zonas` crea UN edificio: cada ala es un nivel con sufijo de rol y en la rejilla TODAS las celdas comparten la planta con su corredor.

**Fase D — GEOMETRÍA CURVA/RADIAL.** `plan_radial` genera la planta de N sectores alrededor de un NÚCLEO circular (el vestíbulo ocupa el disco central) con CORREDOR ANULAR opcional: torres y hospitales radiantes. Los arcos van por cuerdas configurables (el modelo sigue siendo de poligonales: aplicar_plan, DXF y renders funcionan tal cual). El anillo manda: el programa no cabe -> ARQ-DDI-011; si sobra, los locales crecen proporcionalmente SIN bajar del mínimo del DNA; un local con borde interior estrecho queda documentado. APLICAR_PLAN omite el mobiliario automático en plantas radiales (geometría curva) con aviso.

**Fase E — ELEVACIONES PARAMÉTRICAS.** El módulo `elevaciones` (independiente del de parasoles v3.18, intacto) genera las fachadas de cada lado del contorno con 4 pieles deterministas: «panos» (ventana por paño + antepecho + puerta), «ventana_corrida» (banda con parteluces), «brise» (lamas verticales a todo el alto) y «perforada» (malla de círculos). Salida PNG (matplotlib) y DXF R12 con capas FACH_MURO/FACH_VENTANA/FACH_LAMAS/FACH_PERFORACION/FACH_TEXTO.

**GUI.** El marco experto del asistente añade «Chaflán propio de fachada (v3.44)», «Distribuidora hasta (m2)» y los botones «Elevaciones (v3.44)» (DXF+PNG donde el usuario elija) y «Planta radial (v3.44)» (radio, sectores, corredor y núcleo; el análisis queda listo para Generar).

Cobertura: DNA del vestidor con el DRESSING_ROOM intacto, quick con plurales, umbral parametrizable (100 m2 con 120 -> distribuidora; sin parámetro -> 60), round-trip del PlanRequest, chaflán hacia el lobby, bay window en auto/forzado/desactivado con poligonales de 6 vértices y cap de cortes, aplicar con poligonal, zonas con totales/hubs/determinismo/errores 012, rejilla 3x2 con corredor central y planta compartida al aplicar, radial con anillo lleno/núcleo/corredor/cuerdas/determinismo/errores 011-012 y aplicar sin mobiliario, elevaciones con 4 pieles/puerta/determinismo/PNG/DXF releído con ezdxf. Suite en **2467 pruebas** y **91 checks**.

---

## Novedades v3.43.1 — PATIO DOMÉSTICO Y CHAFLANES: LOS DEFECTOS QUE LAS 9 IMÁGENES DE REFERENCIA DESCUBRIERON

Revisión del usuario con 9 imágenes nuevas (fachadas y pieles, formas
de los edificios, distribución interna) y las 3 de PLANTA sondeadas
contra el motor (villa pakistaní 50x90, villa 50x100 y suite de hotel
de 51 m2). Dos defectos reales quedaron al descubierto; esta versión
los cierra.

**Patio doméstico.** El «patio» del quick-spec apuntaba al PATIO
ESCOLAR (mín 100, pref 300 m2, lado 10 m): la villa 50x90 con «2
patios» lanzaba ARQ-DDI-011 SIEMPRE y en la villa 50x100 el patio se
comía el 64 % de la planta (un hueco de 14,8 x 20,3 m en medio de la
casa). Ahora existe el **PATIO_DOMESTICO** (mín 4, pref 9 m2, lado
2,0 m, ámbito vivienda, junto al LAVADERO del DNA) y el quick lo trae
con «patio» o «2 patios»; el patio escolar queda para los programas
de educación por la tabla de usos. La villa 50x90 con 2 patios entra
en 1 nivel y la 50x100 deja el patio en una franja de servicio.

**Chaflanes que disparan de verdad.** El corte a 45 grados de
v3.43.0 medía el margen contra los renglones del programa que el
empaquetado YA HABÍA CRECIDO: margen 0, ningún corte (la suite de 51
m2 y las villas salían ortogonales); el caso Z de 48 m2 disparaba por
casualidad — sus 2 dormitorios colisionaban en el dict de pisos por
código. Ahora el piso es el **MÍNIMO DEL DNA del propio local**
(area_min): el corte nunca deja al local por debajo de la norma
(dormitorio de 14 m2 ideal -> 13,59 tras perder 0,41 hacia la sala,
siempre >= 9,0) y los chaflanes aparecen también SIN selección de
locales. La poligonal de 5 vértices, la sala absorbiendo el triángulo
y la pérdida documentada se mantienen; el informe sigue llevando su
sección CHAFLANES A 45 GRADOS.

Lo que las imágenes mostraron y el motor ya hacía: sala distribuidora
fiel en la suite de 51 m2 (95,5 % sin pasillo), encaje estricto en 1
nivel para las villas grandes y el mobiliario doméstico automático.
Lo que sigue en el horizonte (fase aparte): fachadas paramétricas
(perforado, malla hexagonal), multi-ala hospitalaria y lobby
distribuidor para casas grandes.

`tests/test_178_patio_domestico_chaflanes.py` (17 pruebas): el DNA
del patio (doméstico presente, escolar intacto), el quick (patio y
2 patios), las villas de las imágenes (1 nivel, patio pequeño, sin
«Patio escolar», mínimos del DNA respetados, chaflanes), la suite de
51 m2 cortando SIN selección con poligonales sanas, el corte sin
bajar de norma, el Z con selección como regresión, chaflanes
desactivables, informe y renglones del usuario intactos. Suite en
**2453 pruebas** y **87 checks**.

---

## Novedades v3.43.0 — VIVIENDA SOCIAL: LOS 4 PLANOS DE REFERENCIA SALEN EN 1 PLANTA

Petición del usuario con sus planos de referencia (estudio de 25 m2
del «plan85», casa de 48 m2 en Z, casa cubana de 6.00 x 8.40 del
expediente técnico y casa de 10 x 11 con garaje): «revisa si el
programa puede generar soluciones como estas... y resuelve lo que no
puede hacer todavía». La revisión v3.42 encontró seis huecos; esta
versión los cierra.

**DNA de vivienda (los mínimos que la casa necesita).** La Sala baja
de 12 a **9 m2** (lado 2,70 m), el Comedor de 8 a **6 m2**, y existe
el **LAVADERO DOMÉSTICO** (2-4 m2, lado 1,20 m) SEPARADO de la
lavandería hospitalaria de 20-40 m2 que se llevaba el plan de 48 m2
entero. El quick-spec mapea «lavadero» al doméstico y «lavandería» al
hospitalario; el garaje del quick se llama «Garaje».

**«1 nivel» como TOPE DURO.** Una vivienda (programa con
dormitorios) se topa a 1 nivel POR DEFECTO y el empaquetado COMPACTA
con la escalera de reducción v3.41 ANTES de crecer: la cadena ideal
-> mínimo -> medio -> estricto corre dentro del tope y el primer
empaquetado que entre gana, documentado en AJUSTE DIMENSIONAL. Si ni
el estricto entra, ARQ-DDI-011 (nuevo) NOMBRA los locales que quedan
fuera del tope: «quedan 1 local(es) fuera del tope pedido (Lavadero
doméstico)» — la decisión honesta es excluirlos con la selección
v3.41 o pedir «2 niveles» en la especificación. La casa cubana de
6 x 8,4 sale en UNA planta con 2 dormitorios de 9+ m2 y lados de
3 m, como su expediente.

**Modo SALA DISTRIBUIDORA (sin pasillo).** En casas de <= 60 m2 (el
criterio es el ÁREA DEL CONTORNO, no los ideales inflados del DNA)
el nivel se arma SIN pasillo: la sala reparte el acceso entre
locales, como en los planos de referencia; en la de 10 x 11 (110 m2)
el pasillo sigue apareciendo. Documentado en avisos y en el informe.

**Chaflanes a 45 grados.** Como el corte diagonal del estudio de
25 m2 y la sala central del plano árabe: la esquina del local que da
a la SALA se corta con un triángulo rectángulo isósceles (cateto
0,90 m o el que el margen permita, sin bajar nunca del área ya
ajustada) y el triángulo pasa a la SALA: su poligonal lo absorbe y
el área se traslada. El local queda con poligonal de 5 vértices, la
sala con 6+, sin aristas nulas, y cada corte queda documentado con
su pérdida. Desactivables con «Chaflanes a 45° (v3.43)» del marco
experto; en servicios nunca actúan.

**Mobiliario automático.** `aplicar_plan` amuebla la vivienda
generada con el motor v3.15 en ámbito DOMÉSTICO (cama individual o
de matrimonio según el área, mesitas, sofá, mesa de comedor,
hornillas, inodoro, lavabo, ducha...): 18 piezas en la casa de
referencia, con pasos verificados y QTO recalculado. Los servicios
(morgue, quirófanos...) no se tocan; desactivable con «Amueblar
locales (v3.43)».

`tests/test_177_vivienda_social.py` (37 pruebas): el DNA nuevo, el
tope duro con ARQ-DDI-011 nombrando, la sala distribuidora, los
chaflanes con poligonales sanas, los 4 casos de referencia
(25 m2 entero; 6 x 8,4 con dormitorios normativos; 10 x 11 con
garaje; 48 m2 en Z al 100 % y el lavadero excluido de forma
honesta), informe, contratos round-trip, aplicar_plan con muebles y
poligonales, y 3 ganchos de ventana. Suite en **2436 pruebas** y
**86 checks**.

---

## Novedades v3.42.0 — PASILLOS Y FILTROS: EL PLANO REAL AP + MORGUE QUEDA TÉSELADO COMO EL DIBUJO DE REFERENCIA

Petición del usuario con su caso de referencia: «mira estos dos
DXF, uno es el contorno y el otro es un ejemplo de cómo debería
quedar... es un servicio pequeño de anatomía patológica y morgue de
un hospital pediátrico, la mortalidad es baja; quiero lograr
resultados así, que aprovechen todo el espacio y se distribuyan de
manera óptima con sus pasillos y filtros».

**El pasillo se reserva primero y los locales lo sirven.** El
empaquetado v3.42 reserva la banda del pasillo distribuidor del
contenedor ANTES de repartir locales; cada local adapta sus
dimensiones cambiando FONDO por ANCHO CONSERVANDO SU ÁREA (la misma
adaptación dimensional del cambio de uso v3.41) para dar fondo al
corredor. El ancho del pasillo se adapta al contenedor (2,40 m de
salud, o 1,50/1,20 m cuando la franja es estrecha) y cada nivel
lleva el suyo. Los locales más profundos que cualquier franja siguen
teniendo su zona compuesta de v3.40.

**Teselado completo: nada se queda vacío.** Las filas de satélites se
RELLENAN hasta los bordes del contenedor usando el techo
`area_max` del catálogo (un local crece antes que dejar un hueco
que nadie usa); el crecimiento queda documentado local a local
(ideal -> final) y los recintos-nave siguen adaptándose solos.

**El orden sigue el flujo del servicio y el FILTRO hace de
barrera.** La colocación ordena por flujo — sucio al fondo,
restringido detrás del filtro, limpio después y público en la
entrada — y el local FILTRO sanitario (space_type FILTER, flujo
restringido, presente en morgue, anatomía patológica, UCI,
cuidados intermedios, quirófanos, hemodiálisis y CEYE) se coloca
justo antes de la zona sucia como barrera higiénica, como en el
dibujo de referencia. Si un nivel mezcla flujos y el programa no
lleva filtro (o se excluyó), el informe lo avisa sin inventarlo.

**Compactación a menos niveles.** Con ajuste medio o estricto la
escalera de reducción v3.41 prueba ahora también a BAJAR DE
NIVELES re-empaquetando en planta completa: la morgue del caso
real (18 locales, 203,4 m2) pasa de 3 niveles con áreas ideales a
**1 nivel teselado con pasillo y filtro, todo dentro del polígono
en «Z» de 174,91 m2 y aprovechamiento del 95 %+**, exactamente el
carácter del dibujo esperado. La compactación nunca acepta
geometría fuera del contorno y el mínimo normativo sigue sin
violarse.

El informe añade las secciones «CIRCULACIÓN Y FILTROS» (pasillo por
nivel, filtro como barrera o el aviso de ausencia) y «TESELADO
COMPLETO» (crecimientos documentados), `explicar_local` menciona la
adaptación fondo/ancho, y `aplicar_plan` genera los espacios
CORRIDOR y FILTER reales con sus relaciones al pasillo.

`tests/test_176_pasillos_filtros.py` (27 pruebas): el local FILTRO
en el catálogo y el DNA, orden por flujo estable con el filtro
barrera, pasillo adaptado que conserva áreas y rellena
contenedores sin reducir nunca un local, compactación que baja de
niveles en el caso real (el mínimo no viola la norma, el medio
documenta lo que rebasa y la compactación rechaza lo que se saldría
del polígono), el plano real a 1 nivel con 18 locales + pasillo +
filtro y aprovechamiento >= 95 %, informe, `explicar_local`,
aplicar_plan con CORRIDOR/FILTER, contratos round-trip y 3 ganchos
de ventana. Suite en **2399 pruebas** y **85 checks**.

---

## Novedades v3.41.0 — PROGRAMA ADAPTABLE: ELIGE LOS LOCALES Y AJUSTA SUS DIMENSIONES HASTA ENTRAR

Petición del usuario, la realidad del arquitecto en Cuba: «además de
adaptarse al polígono importado, debe ajustar las dimensiones de los
locales del programa social elegido hasta entrar en dicho polígono,
así como elegir los locales a aplicar; locales y edificaciones ya
construidas a los que hay que hacerles cambios de uso, la mayoría de
las veces se violan algunas regulaciones, pero hay que trabajar con
lo que se tiene; muy pocas veces se puede demoler a gran escala».

**Selección de locales (el programa se adapta al edificio).** El
botón «Locales del programa...» del asistente «Desde dibujo» abre la
lista completa del programa elegido (del catálogo v3.0 o de la
edificación por usos del DNA), AGRUPADA POR TEMÁTICA (el grupo del
catálogo o «General»), con casillas para decidir qué locales se
aplican en ESTE proyecto. Los desmarcados se excluyen del programa y
la exclusión queda DOCUMENTADA en los avisos del informe (nada
silencioso); los recuentos, áreas por grupo y la validación funcional
se recalculan. Las copias de un mismo código entran o salen juntas.
La selección viaja en el contrato `PlanRequest.seleccion`, se guarda
con las CONFIGURACIONES y se restaura con ellas.

**Ajuste dimensional por niveles (la norma se puede rebasar, y se
declara).** Cada local del programa lleva ahora su mínimo normativo
(`area_min` del catálogo o `minimum_area` del DNA). Junto al botón,
el selector «Ajuste de dimensiones» ofrece cuatro niveles:

- **Ideal (sin reducción)**: el programa tal cual (comportamiento
  histórico; si no entra, error de siempre).
- **Mínimo (solo lo que la norma permite)**: si el programa no entra,
  una ESCALERA DE REDUCCIÓN re-empaqueta con áreas progresivamente
  menores (0.95, 0.90, ...) hasta el mínimo normativo de cada local —
  NUNCA lo viola. Si aun así no entra: ARQ-DDI-010 con sugerencia
  de excluir locales o ampliar el contorno.
- **Medio (hasta 15 % bajo la norma)**: la escalera puede llegar a
  `norma x 0,85` (piso absoluto 4 m2, lados desde 2 m).
- **Estricto (hasta 35 % bajo la norma)**: el más agresivo, para
  trabajar con lo que se tiene: `norma x 0,65` (piso 2,5 m2, lados
  desde 1,50 m).

El primer empaquetado que entre gana y el análisis lleva
`ajuste_programa`: reducción local a local (área ideal -> final,
porcentaje, y si quedó BAJO LA NORMATIVA). El informe añade la
sección «AJUSTE DIMENSIONAL (nivel)» con cada rebaja y el aviso
«se rebasa el mínimo normativo en N local(es): decisión del
proyectista, documentada aquí» — el instrumento honesto para el
cambio de uso: la rebaja existe, se ve y se firma. Los recintos-nave
no se reducen (ya se adaptan solos al contenedor) y un programa que
cabe tal cual jamás se reduce. El nivel y la selección se aplican
también en «Comparar alternativas» y viajan en `PlanRequest.ajuste`.

`tests/test_175_programa_adaptable.py` (34 pruebas): selección con
exclusión documentada y grupos recalculados, la norma en los
renglones del catálogo y del DNA, pisos y dimensionado por nivel,
naves intactas, escalera completa (ideal no cabe; mínimo no viola y
se agota con ARQ-DDI-010; medio agotado; estricto entra declarando
la rebaja), selección + ajuste combinados, informe, contratos con
round-trip, plan_de y alternativas, generación real dentro del
polígono y 6 ganchos de ventana. Suite en **2372 pruebas** y
**84 checks**.

---

## Novedades v3.40.0 — ENCAJE ESTRICTO AL POLÍGONO: NADA SE SALE Y LA FORMA SE APROVECHA

Queja del usuario tras usar el asistente «Desde dibujo» en una parcela
real: «el diseño se sale del polígono que importé y no aprovecha todos
los espacios». Diagnóstico honesto: el empaquetado histórico trabaja
sobre la CAJA ENVOLVENTE del contorno y, cuando un local caía fuera
del polígono dibujado, se limitaba a AVISAR («retóquelo con las
herramientas CAD»). En parcelas en L, U o T eso garantizaba diseños
fuera de línea y huecos desaprovechados.

**Motor nuevo (domain/encaje.py, cero dependencias y cero IA).** La
parcela se tesela en CONTENEDORES reales donde pueden vivir locales
ortogonales:

- **Rectángulo alineado**: un contenedor (camino rápido, igual que
  siempre).
- **Polígono ortogonal (L, U, T, cruz...)**: descomposición EXACTA por
  franjas horizontales de barrido fusionadas — entre dos cotas y
  consecutivas de vértices la sección del polígono es constante, así
  que las franjas teselan la parcela sin huecos ni solapes (la L de
  prueba: 2 contenedores que cubren sus 160 m2; la U: 3). El codo de
  la L o las patas de la U quedan DENTRO de contenedores y reciben
  locales en vez de ser hueco perdido.
- **Polígono con aristas inclinadas**: el mayor rectángulo inscrito
  axis-alineado (candidatos refinados y sección común en las cotas
  cerradas de la banda), con aviso honesto de que el resto de la
  parcela no admite locales ortogonales.

**Empaquetado con contención verificada (domain/desde_dibujo.py).** El
contenedor mayor lleva el pasillo a dos bandas (con escalera de
Blondel y patio experto como antes, ahora DENTRO del contenedor) y los
contenedores conectados (arista compartida >= 1,2 m, para que todo sea
alcanzable) reciben locales en filas con las dos orientaciones. Tres
redes de seguridad honestas:

- **Zonas compuestas**: un local más profundo que cualquier franja
  sola (la «Sala de necropsias» 5,68 x 7,39 m del plano real AP Y
  MORGUE) ocupa la UNIÓN de dos contenedores contiguos, validada
  dentro del polígono, y el hueco se resta del empaquetado.
- **Nivel sin pasillo**: si el pasillo no cabe (locales más profundos
  que pasillo + fondo del contenedor) el nivel se reempaqueta por
  filas SIN pasillo, se avisa y el área completa de la parcela se
  aprovecha; el acceso queda entre locales.
- **Errores que dicen la verdad**: si un local no cabe en ningún
  contenedor ni en la unión de dos contiguos, el mensaje muestra las
  medidas del contenedor mayor.

La contención se VERIFICA local a local contra el polígono real
(`rect_dentro`), ya no contra la caja; el mismo criterio corrige las
métricas (antes un local fuera de la parcela pero dentro de su caja
contaba como «dentro»). Nuevos totales: `area_aprovechada` y
`aprovechamiento_pct` sobre el área del polígono; el informe del
diálogo declara estrategia, contenedores y aprovechamiento; «¿Por
qué?» explica cada local de contenedor o zona compuesta. El encaje
estricto es el comportamiento por defecto; en el marco experto vive el
interruptor «Encajar estrictamente en el polígono» y el camino
histórico de caja envolvente queda disponible (`encaje_estricto=False`
o desmarcando la casilla) con su aviso de siempre.

Con el plano real del usuario (AP Y MORGUE, 174,91 m2): la morgue
sigue creciendo a 2 niveles (9 + 8 locales) pero ahora TODOS los
locales quedan dentro de la parcela dibujada; anatomía patológica
reserva «Sala de necropsias» y «Sala de corte» como zonas compuestas y
también queda enteramente dentro. `tests/test_174_encaje_poligono.py`
(30 pruebas): teselas exactas de L/U/T, rombo inscrito, parcela
desplazada del origen, franjas diminutas descartadas, contención dura
local a local, aprovechamiento, niveles sin pasillo, contratos con
`encaje_estricto`, generación real dentro del polígono y 3 ganchos de
ventana. Suite en **2337 pruebas** y **83 checks**.

## Novedades v3.39.1 — HILO SEGURO SQLITE (HOTFIX: «ERROR AL IMPORTAR» RESUELTO)

Reporte del usuario al pulsar «Importar al proyecto» en el asistente de
planos DXF/DWG:

```
ERROR AL IMPORTAR
Error SQL: SQLite objects created in a thread can only be used in that
same thread. The object was created in thread id 17124 and this is
thread id 10716.
```

**Causa raíz.** La conexión SQLite del proyecto se abre UNA sola vez en
el hilo principal (al abrir o crear el archivo `.arqgen`) y vive durante
toda la sesión en `ProjectContext.session`. Pero el diálogo de
importación §94 ejecuta el trabajo pesado en un **hilo de fondo**
(`_run_async`: el hilo lee el plano y aplica `ArchitectureService`
mientras la GUI mantiene la barra de progreso viva). Con el ajuste por
defecto de `sqlite3.connect` ese cruce aborta SIEMPRE: el módulo rechaza
usar una conexión creada en otro hilo. Las pruebas no lo vieron porque
el diálogo GUI se ejercita con `self._dxf_sync = True` (camino
síncrono), de modo que el camino real multihilo quedó sin cubrir desde
la v3.3.0.

**Arreglo (persistence/sqlite/connection.py).** Tres piezas pequeñas y
quirúrgicas, sin tocar domain ni la UI:

- `ConnectionManager.connect()` crea la conexión con
  `check_same_thread=False` y `timeout=30.0`: la MISMA conexión puede
  recibir trabajo del hilo de la GUI y del hilo de fondo.
- Nuevo candado reentrante `_DB_LOCK` (module-level): `Session.execute`,
  `commit`, `rollback`, `close` y `ConnectionManager.integrity_check`
  lo adquieren antes de tocar la conexión. El efecto es una cola
  ordenada de transacciones, exactamente la misma serialización natural
  de un programa de un solo hilo: en una app de escritorio monousuario
  no hay dos escritores legítimos simultáneos.
- Es reentrante a propósito: una operación de repositorio que ejecuta y
  confirma en la misma llamada no se bloquea consigo misma. Y
  `close()` también espera al candado, así que cerrar la ventana con
  una importación de fondo en marcha deja terminar la transacción antes
  de soltar el archivo.

**Cobertura nueva.** `tests/test_173_hilo_sqlite.py` (7 pruebas)
reproduce el camino REAL que fallaba: proyecto creado en el hilo
principal e importación `DxfImporter().apply(...)` completa desde un
hilo ajeno (antes: ProgrammingError; ahora: 4 muros creados y
persistidos), settings con commit/rollback desde hilo ajeno, creación
arquitectónica con auditoría y eventos desde hilo ajeno, ocho hilos
escribiendo configuraciones a la vez con barrera (el candado los pone
en cola y los 8 valores sobreviven), y la capa pura
ConnectionManager/Session usada desde otro hilo con integrity_check.
Selftest: check 82 conductual (proyecto + dos hilos concurrentes +
continuación del hilo principal sobre la misma conexión). Suite en
**2307 pruebas** y **82 checks**.

## Novedades v3.39.0 — DESDE DIBUJO REFORZADO: EL ASISTENTE DINÁMICO, APLICADO AL FLUJO INVERSO

Del análisis del spec «Asistente dinámico de generación arquitectónica» se
adoptó lo que mejora el asistente «Desde dibujo» y se descartó lo que no
aplica al flujo inverso (el contorno ya viene dado). Novedades:

- **VALIDACIÓN PREVIA DEL CONTORNO** (`validar_contorno`): autointersecciones
  (lazo), área cero, dimensiones imposibles (< 0,5 m2), área muy pequeña o
  gigante (¿unidades?), contornos muy alargados y vértices casi colineales,
  cada hallazgo con severidad **ERROR / ADVERTENCIA / RECOMENDACIÓN**; el
  informe sale en «Analizar contorno».
- **CHECKLIST ANTES DE GENERAR** (spec §24): bloque [OK]/[AVISO]/[ERROR]
  consolidado (contorno, programa, crecimiento con escalera, dentro del
  contorno, niveles pedidos y patio pedido) que precede al ajuste.
- **CONTRATOS PlanRequest / PlanResult** (spec §37-§39): la intención del
  asistente viaja serializable (contorno, programa, opciones expertas y pesos
  de diseño) y el resultado vuelve con checklist, métricas y decisiones.
- **ALTERNATIVAS 1/3/5** (spec §25/§26): el mismo programa probado «tal cual»,
  «girada 90 grados» y «compacta» con métricas comparables (construida, útil,
  circulación %, ocupación %, cumplimiento %) y PUNTUACIÓN explicada con los
  pesos del diseño; se elige la alternativa y se genera esa.
- **¿POR QUÉ?** (spec §32/§33): decisiones registradas del empaquetado
  (niveles, escalera de Blondel, patio y banda de cada local) y
  «¿por qué este local aquí?» respondido con reglas, sin IA.
- **REEMPLAZO DEL EDIFICIO PREVIO** (spec §27/§28): al generar sobre un
  proyecto que ya tiene un edificio del asistente, pregunta REEMPLAZAR (lo
  elimina con sus niveles y espacios, vía CommandBus) o crear OTRO; se
  acabó el segundo edificio silencioso.
- **CONFIGURACIONES Y ESTADO GUARDABLES** (spec §29/§30): fotografías
  «CONFIGURACIÓN 01...» de la petición dentro del proyecto (tope 10,
  numeración sin repeticiones), restaurables desde el diálogo, y el estado
  del asistente se guarda solo al generar para retomar donde se dejó.
- **QUICK-SPEC EN UNA LÍNEA** (spec §42, sin IA): «3 dormitorios, 2 baños,
  garaje y 2 niveles» escribe la tabla de usos (diccionario + regex, con
  acentos, plurales y números en palabra); lo no reconocido se declara.
- **PATIO EXPERTO**: reserva un patio exterior (tipo DNA PATIO, ancho
  configurable) al final del pasillo en cada nivel, descontado del ancho
  para locales y con su decisión registrada; si no cabe, avisa y lo ignora.
- **MODOS BÁSICO / PROFESIONAL / EXPERTO** (spec §10): cada modo muestra solo
  lo que toca (el experto añade espesores de muros, patio y niveles deseados).
- **Pruebas**: `tests/test_172_desde_dibujo_v39.py` (65: validación, checklist,
  contratos, métricas, alternativas con giro, decisiones, quick-spec, patio,
  reemplazo real, configuraciones y 10 ganchos de ventana) y selftest check 81
  conductual (lazo, quick-spec, alternativas, patio, reemplazo real en
  proyecto temporal y configuraciones); suite en **2300 pruebas** y **81 checks**.

## Novedades v3.38.0 — DIBUJO Y NAVEGACIÓN ESTILO CAD CLÁSICO (LECCIONES DE INGECAD, REIMPLEMENTADAS)

El análisis de IngeCAD (github.com/ingelibre/ingecad, GPL-3.0: ideas
integradas por REIMPLEMENTACIÓN propia, sin copiar código) deja en ARQ
GEN el músculo de trabajo diario del CAD clásico:

- **Gramática de coordenadas por teclado** (`ui/coords_entrada.py`):
  `10,5` absoluto, `@10,5` relativo al último punto, `10<45` y
  `@10<45` polares, `25` distancia directa hacia el cursor,
  `#10,5` fuerza absoluto y cualquier campo acepta EXPRESIONES
  (`2*3.5`, `2*(3+4)/7`, `2*pi`) evaluadas por AST sin nombres ni
  llamadas (la misma disciplina que las reglas; errores amables
  ARQ-CRD-001..004). El punto tecleado BYPASS del snap, como el
  clásico: el teclado no se imanta.
- **Línea de comandos** (`ui/linea_comandos.py` + barra inferior):
  abajo, donde siempre. Escribe `mu` y arma el muro, `10,5` y lo
  dibuja. Enter sin texto repite la última orden, ↑/↓ recorren el
  historial (200 entradas, duplicados adyacentes colapsados, el
  borrador no se pierde), autocompletado por prefijo, `=expr`
  devuelve el valor y **F2** abre la ventana de texto con el
  historial completo.
- **Navegación clásica** (`ui/navegacion.py`): **Z** zoom por
  ventana con marco azul (dos clics), **ZP** zoom anterior con pila
  acotada a 32 vistas que guarda zoom/pan/encuadre, **ZE** encuadrar
  todo, rueda a **1.2 por muesca** anclada al cursor y, sin nada que
  encuadrar, el lienzo vacío enmarca el rectángulo honesto de
  ±50 m (nunca el caos).
- **Selección ventana/cruce**: arrastra en vacío y el marco aparece
  AZUL (izq→der: objetos completamente dentro) o VERDE discontinuo
  (der→izq: los que tocan), con los colores clásicos; eco
  «N seleccionado(s)», Esc limpia, y el resaltado multiple acata.
- **Referencias (osnap) con la familia clásica** (`ui/cursor_acad.py`):
  EXTREMO (cuadrado), INTERSECCIÓN (X), PUNTO MEDIO (triángulo) y
  CENTRO de locales (círculo) activos de fábrica; PERPENDICULAR
  (ángulo recto) y MÁS CERCANO (pajarita) opt-in porque imantan la
  recta entera. Precedencia de AutoCAD (un extremo le gana a una
  intersección cercana, y esta a un medio), marcadores amarillos
  clásicos y Mayús mantenido = orto temporal.
- **Rejilla anidada adaptativa**: niveles ×5 con celda mínima de
  25 px en pantalla, línea MAYOR cada 5 pasos, banda antiflip para
  que una muesca de rueda no oscile entre niveles, y el paso de
  imantación coincide con la rejilla dibujada.
- **DYN (F12)**: mientras dibuja, una etiqueta junto al cursor con
  «d 3.42 < 45» (distancia y ángulo del tramo vivo), conmutables
  como los demás modos.
- **Aliases nuevos**: MU/ES/ZO/PU/VE (dibujo), Z/ZE/ZP/QC
  (navegación y calculadora). P+ESPACIO sigue siendo pan y PU es
  puerta (la misma resolución de acad.pgp); el buffer letra a letra
  respeta los prefijos largos.
- **Tests**: `tests/test_171_ingecad_nav.py` (63: 40 sin display +
  13 ganchos de ventana + versiones) y selftest check 80 con la
  gramática, la línea, la pila, la rejilla y las referencias de
  forma conductual; suite en **2235 pruebas** y **80 checks**.

## Novedades v3.37.0 — DXF REAL: IMPORTACIÓN ROBUSTA Y FLUJO «DESDE DIBUJO → SERVICIO» CON PLANOS DE CAD VERDADEROS

El plano real «AP Y MORGUE.dxf» (una LWPOLYLINE abierta de 9 vértices con el primero repetido al final en capa 'MURO', 2 MTEXT vacíos en 'A-TEXTO' y $INSUNITS=4 milímetros) dejaba el análisis en cero candidatos («LWPOLYLINE de muro no rectangular ignorada»). El lector §94 y el asistente «Desde dibujo» sobreviven ahora a los planos de CAD verdaderos:

- **Unidades $INSUNITS a metros** (`UNIDADES_DXF` + `escala_unidades_dxf`): milímetros (0.001), centímetros, pulgadas, pies, yardas, kilómetros... El plano del usuario (17 681 × 15 007 unidades) se analiza como una planta de 17.68 × 15.01 m y no como 17 km; el informe del diálogo declara «Unidades del plano: milímetros (escala 0.001 a metros; coordenadas convertidas)».
- **Cierre geométrico** (`_cierre_geometrico`): el flag `closed` del CAD suele quedar en False aunque la polilínea repita el primer punto al final; el bucle real se honra (tolerancia relativa 1e-6 de la diagonal) y el vértice de cierre duplicado se limpia antes de procesar.
- **Contorno de planta descompuesto en muros**: una polilínea cerrada de N lados en capa de muros se convierte en N segmentos de muro (la rectangular de 4 lados sigue dando su eje central como siempre); las polilíneas ABIERTAS de muros dan un segmento por arista (el trazo habitual por ejes); los arcos (bulge) se trazan por cuerdas rectas con aviso honesto.
- **Textos vacíos avisados**: los MTEXT/TEXT con texto vacío (restos de plantillas CAD) se cuentan como `textos_vacios` y avisan por capa en vez de descartarse en silencio (explica por qué una capa de texto daba «texts: 0»).
- **`contornos_dxf` robusto**: acepta el cierre geométrico, CIERRA SOLO las polilíneas casi cerradas (hueco ≤ máx(2 cm, 1 por mil de la diagonal)) marcándolas `cerrada_auto` con su `hueco_m` — el combobox de «Desde dibujo» muestra «· cerrada automáticamente» —, escala las coordenadas a metros según $INSUNITS y usa `is_closed` para POLYLINE (atributo estable en ezdxf: el `.closed` de antes fallaba en silencio con polilíneas 2D leídas del archivo, un latente de v3.34.0 que la nueva prueba destapó).
- **Extremo a extremo con el plano real**: contorno ortogonal de 8 vértices y 174.91 m2 → explorar catálogo (34 servicios: FARMACIA cabe en 1 nivel; MORGUE 199.4 m2 crece a 2 niveles con escalera de Blondel; ANATOMÍA PATOLÓGICA a 3; ALMACÉN LOGÍSTICO no entra, ARQ-DDI-003) → `aplicar_plan` genera el edificio real (2 plantas, 17 locales + 2 pasillos + 2 escaleras, zona SERVICE, relaciones adjacent_to y auditoría GENERAR_DESDE_DIBUJO), y el importador §94 crea los 8 muros del contorno en metros con la importación auditada y deshacible.
- **Pruebas**: `tests/test_170_dxf_real.py` (41: réplica 1:1 de la estructura del plano real, unidades, cierre geométrico, descomposición, cuerdas, textos vacíos, contornos con cierre automático y el flujo completo hasta el edificio; +5 ganchos de ventana con display) y selftest check 79 con la misma réplica conductual; suite en **2172 pruebas** y **79 checks**.

## Novedades v3.36.0 — CATÁLOGO UNIVERSAL DE SERVICIOS (V3.0) Y EXPLORADOR «DESDE DIBUJO»

El asistente de servicios deja de ser médico y pasa a ser UNIVERSAL: el catálogo `servicios_specs.json` sube a **v3.0** con el campo `sector` y **34 servicios / ~400 locales / 97 parámetros / 90 checks / 8 sectores**. El flujo «desde dibujo → servicio» se cierra con un **explorador** que prueba el contorno dibujado contra TODOS los servicios.

- **12 servicios de SALUD nuevos** (con grupos, criticidad, puertas de camilla, circulación, instalaciones, acabados y relaciones del esquema v2.0): `CONSULTA_EXTERNA` (consultorios repetidos, toma de muestras opcional), `QUIROFANOS` (bloque quirúrgico con preanestesia, recuperación post-anestésica, esterilización en el bloque, ropa limpia/sucia y circuitos separados), `HOSPITALIZACION` (habitaciones WARD por parámetro, aislamiento con presión negativa, estación de enfermería), `MATERNIDAD` (dilación, salas de parto críticas, cesárea opcional, neonatos y NICU condicionada), `CARDIOLOGIA_HEMODINAMIA` (CATH_LAB con control con vista y radioprotección), `ENDOSCOPIA` (lavado de endoscopios con circuito sucio-limpio), `MEDICINA_NUCLEAR` (gammacámara con blindaje, radiofarmacia, dosimetría, aislamiento para terapias), `LABORATORIO_MICROBIOLOGIA` (microbiología + PCR con flujo unidireccional, autoclave de paso), `BANCO_DE_SANGRE` (donación, fraccionamiento, cadena de frío vigilada), `REHABILITACION_FISIOTERAPIA` (gimnasio terapéutico, cabinas, hidroterapia opcional), `SALUD_MENTAL` (talleres, convivencia, patio controlado) y `ODONTOLOGIA` (sillones, radiología dental, esterilización central).
- **11 servicios de OTROS SECTORES**: `CIRCULO_INFANTIL` (sala cuna, aulas con higiene infantil propia, juego interior/exterior, comedor y cocina), `ESCUELA_PRIMARIA` (aulas por parámetro, biblioteca, computación, multiusos, patio), `ESCUELA_SECUNDARIA` (+ laboratorio de ciencias, taller, arte, música con acústica), `OFICINAS` (open office a 6 m2/puesto, salas de reunión repetidas, servidores/UPS, cafetería y bicis opcionales), `RESTAURANTE` (sala a 1.8 m2/comensal, cocina con flujo de producción, cámara fría), `SUPERMERCADO` (sala de ventas paramétrica, almacén con muelles, carnicería con cámara), `HOTEL` (habitaciones repetidas, lobby, restaurante/lavandería opcionales), `CENTRO_DEPORTIVO` (gimnasio, multiusos, vestuarios por módulos), `CENTRO_CULTURAL` (galería, arte, música, multiusos, biblioteca), `RESIDENCIA_ADULTOS` (habitaciones con llamada, enfermería central, comedor, patio terapéutico) y `ALMACEN_LOGISTICO` (nave paramétrica en m2, muelles de 20 m2).
- **Dominio**: `Servicio.sector` + `ETIQUETAS_SECTORES` + `servicios_por_sector()` (agrupado y ordenado, SALUD primero) y `resumen_catalogo` con sectores; vocabulario de instalaciones ampliado con `vapor`.
- **EXPLORADOR DEL CATÁLOGO** (`domain/desde_dibujo.py`): `explorar_catalogo()` arma el programa por defecto de CADA servicio y lo ajusta al contorno con `ajustar()` (34 barridos en ~1 s, sin excepciones: los imposibles quedan al final con su código), y `texto_exploracion()` reporta «CABE EN 1 NIVEL / crece a N niveles / NO ENTRA» en cp1252.
- **Recintos-nave** en el empaquetador: un local cuya fachada requerida (área/fondo capado) excede el ancho del contorno va SOLO en su nivel como rectángulo proporcional profundo junto al pasillo (sala de ventas, nave de almacén); para los demás locales el comportamiento v3.34.0 es idéntico (identidad verificada).
- **GUI**: filtro «Sector:» (Todos + 8 etiquetas) en el asistente de Servicios y en el panel de servicio de «Desde dibujo»; botón **«Explorar catálogo aquí»** que prueba el contorno actual contra los 34 servicios y muestra el listado ordenado; tooltips ampliados.
- **Validación en origen** (constructor v3.0): space_types contra el DNA, adyacencias por código, relaciones obligatorias/deseables contra nombres reales, condiciones y repeticiones contra parámetros, vocabulario de instalaciones, áreas por defecto contra mínimos DNA y cp1252 en cada cadena.

## Novedades v3.35.0 — SERVICIOS MÉDICOS: CATÁLOGO V2.0 Y DOCUMENTOS DEL SERVICIO

- **El documento entra al programa**: el asistente de servicios
  v3.33.0 se perfecciona con el documento «servicios médicos»
  (especificaciones técnicas y programa arquitectónico de servicios
  hospitalarios especializados). El catálogo
  `resources/knowledge/servicios_specs.json` pasa de versión 1.0 a
  **2.0**: 11 servicios y 140 locales (antes 6 y 46), todo validado
  contra el DNA y con referencias internas verificadas.
- **Cinco servicios nuevos**: MORGUE (17 locales con el módulo de
  cámara 1,00 × 2,40 m y la sala de autopsias 25-40 m²),
  TOMOGRAFIA_COMPUTARIZADA (14: área pública, de paciente y técnica,
  con la sala CT 25-35 m² que se repite por equipo y la nota honesta
  de radioprotección: blindaje por cálculo del especialista, sin
  espesor universal), UCI (18 con cubículos de 16-20 m² por puesto,
  aislamiento opcional y cabecera completa), CUIDADOS_INTERMEDIOS
  (15, habitaciones de 14-18 m² por puesto) y URGENCIAS (24 locales:
  bahía de ambulancias, triage junto al acceso, consultorios,
  reanimación 20-30 m²/puesto, trauma, observación, procedimientos,
  yesos, limpia/sucia y personal).
- **Anatomía patológica enriquecida** de 10 a 16 locales (secretaría,
  reuniones, microscopía, almacén de reactivos, limpieza y residuos)
  y con el metadato completo del documento en cada local.
- **Metadatos nuevos por local** (todos opcionales y tolerantes):
  GRUPO funcional (áreas del servicio, sección 2-7), CRITICIDAD por
  niveles 1-3 (sección 25), PUERTA_ANCHO (camilla/carro 1,20-1,50 m)
  y CIRCULACION_MIN del documento, INSTALACIONES con vocabulario
  canónico (gases, electricidad normal/emergencia, UPS, puesta a
  tierra, datos, llamada, CCTV, iluminación general/tarea/
  emergencia, HVAC, extracción, presión...), ACABADOS
  (piso/paredes/techo), EQUIPAMIENTO como generador de espacio
  (sección 21), RELACIONES obligatorias/deseables/prohibidas y
  OBSERVACIONES.
- **Programa con grupos y subtotales** (sección 20): el área total
  del servicio se desglosa por componente (accesos, asistencial,
  limpia, sucia, apoyo, personal, familiares...) en la tabla, en la
  línea de totales y en el texto; «no utilizar un único porcentaje
  universal de circulación» se traduce en subtotales reales.
- **Validación ampliada**: PUERTAS usa el ancho del catálogo (y el
  DNA para los críticos), CIRCULACION compara la mínima pedida con
  el pasillo de 2,40 m del asistente, CRITICIDAD resume los niveles
  presentes, PROHIBIDAS hace eco de las relaciones prohibidas (regla
  05) y SEPARACION avisa cuando conviven circuitos limpio y sucio
  (regla 06). Los cinco servicios nuevos y la AP enriquecida
  cumplen TODAS las áreas mínimas del DNA con sus defectos.
- **Documentos del servicio** en el selector «Documento:» del
  asistente: FICHA DE LOCAL (sección 30: superficies, puerta,
  circulación, criticidad, instalaciones, acabados, equipamiento,
  requisitos, relaciones y observación), MATRIZ DE INSTALACIONES
  (sección 22, con Radioprotección MUY ALTA en tomografía),
  RELACIONES ENTRE SERVICIOS (sección 17: Urgencias con UCI MUY ALTA,
  Morgue con Anatomía Patológica MUY ALTA...), FLUJOS HOSPITALARIOS
  (sección 18: los del servicio más los cuatro canónicos con
  «->» cp1252) y las 20 REGLAS DE GENERACIÓN AUTOMÁTICA DE PLANTAS
  (sección 24). La tabla del asistente gana la columna GRUPO y
  barra de desplazamiento.
- **Desde dibujo hereda el catálogo**: el modo
  servicio del asistente «Desde dibujo» (v3.34.0) genera ya los 11
  servicios con todo el detalle; cero cambios necesarios ahí.
- Nuevos errores amables: ARQ-SRV-007 (local inexistente para la
  ficha). Textos 100% cp1252 sin flechas Unicode.
- tests/test_168_servicios_medicos.py (NUEVO, 44): catálogo v2.0
  (11 servicios, versión y reglas globales, flujos sin «→»,
  enriquecimiento de la AP con la ficha §30 literal, matriz,
  relaciones entre servicios, vocabulario de instalaciones,
  criticidad, puertas de camilla, tolerancia de `from_dict`),
  programas médicos (morgue 17/26,4 m² con 6 cámaras, TAC con salas
  repetidas y espera por persona, UCI 25 renglones con cabecera,
  intermedios 24, urgencias 30 con reanimación/observación por
  puestos y grupos coherentes), validación ampliada (puertas del
  catálogo, circulación cubierta, criticidad, prohibidas, separación
  limpio/sucio y el contra-caso de farmacia, ARQ-SRV-007), los cinco
  documentos en cp1252 y los ganchos de ventana (columna grupo,
  selector de documento, ficha con y sin selección, totales por
  grupos). test_166 actualizado a la AP de 16 locales (17 espacios
  aplicados, 16 relaciones); check 75 del selftest a 16; test_126
  76→77 checks con el marcador «servicios médicos»; check 77 nuevo
  (fuente + conductual: catálogo, urgencias con grupos, ficha y
  matriz).

## Novedades v3.34.0 — DESDE DIBUJO: GENERACIÓN INVERSA

- **El camino al revés** (`domain/desde_dibujo.py` + asistente en la
  ventana): en vez de definir el programa y obtener la edificación,
  se PARTE del dibujo de un área o espacio —importado de un DXF,
  dibujado a dos clics con el panel de Dibujo v3.33.0 o dado por un
  rectángulo— y el asistente dinámico genera la edificación o el
  servicio completo, según sea el caso.
- **Inferencia de forma y medidas**: vértices normalizados
  (antihorario, sin duplicados ni cierre duplado), área por
  shoelace, caja envolvente, perímetro, centroide y clasificación
  honesta: rectángulo alineado, rectángulo girado, ortogonal (en L,
  en T...) o polígono general. Errores amables ARQ-DDI-001..005.
- **El programa según el tipo y el uso social**: modo SERVICIO (el
  catálogo v3.33.0 con sus parámetros dinámicos: anatomía
  patológica, hemodiálisis...) o modo EDIFICACIÓN (usos del DNA con
  cantidad y área opcional; sin área se usa la preferida o el
  mínimo del uso, y si el uso no está en el DNA lo dice).
- **¿Entran o no entran?** empaquetado con pasillo de distribución
  de 2,40 m a dos bandas (criterio v3.33.0, con bandas simples si
  la profundidad no da más) y VERIFICACIÓN HONESTA: cada
  rectángulo se comprueba DENTRO del polígono dibujado (centro
  dentro y borde sin cruzar aristas), no basta la caja envolvente.
  Si algo queda fuera, lo avisa y propone retocar con las
  herramientas CAD.
- **Crecimiento en altura**: si el programa no cabe en un nivel, se
  reparte en N niveles apilados sobre el mismo contorno (techo 50,
  como los multiplicadores v3.32.0) y cada nivel reserva el
  recinto de la escalera dimensionado con Blondel (en U hasta dos
  tramos; recta a partir de tres), con el aviso para rematarla con
  el asistente de Escaleras.
- **Generación real por los caminos oficiales**: edificio nuevo con
  un nivel por planta (cotas apiladas), pasillo CORRIDOR, locales
  con su uso del DNA, recinto STAIR, zona (SERVICE en modo
  servicio, PUBLIC en edificación), relaciones adjacent_to con el
  pasillo y opción de trazar muros del contorno (0,20 m) y de cada
  local (0,15 m, aristas compartidas duplicadas como siempre se
  avisa). Auditoría GENERAR_DESDE_DIBUJO, evento
  DOCUMENT_CHANGED, QTO, presupuesto, checks, DXF e informes lo
  ven todo. Opción de eliminar el espacio de boceto al generar.
- **DXF de entrada**: `contornos_dxf` enumera las polilíneas
  CERRADAS del archivo (LWPOLYLINE y POLYLINE, cualquier capa),
  ordenadas de mayor a menor área; el usuario elige cuál es el
  contorno. El resto del dibujo se ignora a propósito. ezdxf ya
  era dependencia (importador §94): cero dependencias nuevas.

## Novedades v3.33.0 — HERRAMIENTAS DE DIBUJO + ASISTENTE DE SERVICIOS

- **Dibujar como en ArchiCAD/AutoCAD** (`ui/dibujo_cad.py` + paleta):
  la paleta de herramientas estrena la sección **«Dibujar»** con cinco
  herramientas: **Muro** (dos clics, espesor y altura configurables —
  vacío = la del nivel—, con vista previa de su espesor real),
  **Espacio** (dos esquinas; uso del DNA y nombre opcionales, con
  vista previa del rectángulo), **Zona** (dos esquinas y los locales
  dentro quedan ASIGNADOS a la zona), **Puerta** y **Ventana** (un
  clic sobre el muro y el vano queda CENTRADO en el clic, sujeto al
  muro). El imán de siempre funciona: vértices (F3), rejilla (F7),
  orto (F8) y imantación (F9) desde el puntero AutoCAD v3.16.0.
- **Entidades REALES, impacto automático**: todo pasa por
  ArchitectureService (create_wall/create_space/create_zone/
  set_space_zone/create_opening), con auditoría CREATE_ENTITY,
  eventos, invalidación de QTO y undo persistente. Por eso lo
  dibujado entra SOLO en cantidades, presupuesto, explorador,
  validación dimensional y exportaciones DXF/IFC: dibujar ES
  construir en el proyecto, no dibujar al margen.
- **Las reglas del proyecto avisan (nunca bloquean)**: espacio con
  área bajo el mínimo del uso, puerta más estrecha que la del uso
  (DNA neufert.puerta_m), ventana que no aporta el hueco que pide el
  uso (habitables 1/6 de la superficie, húmedos 1/25 —mismo criterio
  del editor de locales—), muro fino o más alto que su nivel, zona
  sin locales. Errores amables ARQ-DIB-001..005.
- **Asistente de SERVICIOS aparte** (botón «Servicios» en la barra y
  menú Herramientas): para cuando solo te interesa EL SERVICIO y no
  la edificación completa. Eliges temática del catálogo versionado
  `resources/knowledge/servicios_specs.json` (formato
  ARQ_GEN_SERVICIOS): **Anatomía Patológica** completa (recepción de
  cadáveres, cámara mortuoria, sala de necropsias, lavado de
  instrumental, histotecnología, sala de corte/macroscopía, archivo
  de bloques y láminas, oficina de patólogos, vestuarios con duchas,
  espera del público), **Laboratorio Clínico** (toma, bancadas,
  microbiología BSL-2), **Imagenología** (salas de RX REPLICABLES
  por parámetro, mamografía, TAC con cuarto de mando),
  **Hemodiálisis** (puestos de 8 m², monitoreo, tratamiento de agua),
  **CEyE** (circuito en un sentido con barrera sanitaria) y
  **Farmacia** (almacén por camas, cámara fría, estéril opcional).
- **Parámetros dinámicos y programa dimensionado**: cada servicio
  declara sus parámetros (necropsias/día, piezas/día, puestos,
  quirófanos servidos, camas, conmutadores) y el motor
  `domain/servicios_engine.py` compone el programa: área base + área
  por parámetro, acotada a los mínimos/máximos del catálogo con
  aviso, dimensiones sugeridas, flujo (sucio/limpio/estéril),
  requisitos técnicos, adyacencias y localizaciones críticas
  marcadas. Los parámetros basura se degradan con aviso (nunca
  explotan).
- **Validación funcional honesta**: AREAS contra el mínimo del uso
  del DNA, CRITICOS presentes (avisa si un crítico condicional
  quedó fuera, p.ej. TAC o farmacia estéril), ADYACENCIAS a
  verificar, PUERTAS recomendadas del DNA para los críticos, flujos
  y notas del catálogo.
- **Aplicar al nivel crea el servicio de verdad**: zona SERVICE,
  pasillo CORRIDOR de 2,40 m (salud con camillas) con los locales a
  dos bandas, espacios reales con su uso del DNA y en la zona,
  relaciones adjacent_to con el pasillo y opción de trazar los
  muros de cada local (avisa de las aristas duplicadas). En un
  proyecto SIN niveles se crea el edificio mínimo con su nivel al
  vuelo: el servicio puede nacer solo.
- Regresiones nuevas (`tests/test_165_dibujo_cad.py`, 34 pruebas:
  geometría, imantación headless, las cinco herramientas con sus
  reglas, resúmenes cp1252 y ganchos de la ventana con paleta real;
  `tests/test_166_servicios.py`, 27 pruebas: catálogo sano, programa
  escalado/acotado/condicionado/repetido, validación funcional,
  aplicación con zona/pasillo/relaciones/muros y textos cp1252) y
  check 75 del selftest.

## Novedades v3.32.0 — P3: MULTIPLICADORES DE NIVELES / PLANTA TIPO REPETIDA

- **Cada nivel lleva su multiplicador** (`ui/building_wizard.py`):
  `LevelSpec.repeat` (1 = planta única, comportamiento previo intacto;
  techo 50). Diseñas la planta tipo UNA vez y pides «×N»: niveles,
  locales, muros, puertas, ventanas y cotas salen multiplicados y
  coherentes. `repeat_de()` sanea cualquier valor sin lanzar (0,
  negativos o texto se degradan a 1).
- **Expansión determinista**: `niveles_expandidos()` duplica cada
  nivel con nombres únicos («Planta Tipo», «Planta Tipo 2»,
  «Planta Tipo 3»… y dedup «_2» ante colisión); `expandir_datos()`
  duplica los locales de la planta en cada copia apuntando su
  «level_ref» a la copia, mientras las relaciones espaciales siguen
  GLOBALES (van por nombre de local) y no se duplican. Con todos los
  multiplicadores a 1 ambas son IDENTIDAD y devuelven el mismo objeto.
- **Cotas que se recorren solas**: `level_elevations()` corre sobre
  los niveles ya expandidos — una planta tipo ×3 de 3 m empuja las
  cotas a 0/3/6/9 y lo que venga después.
- **Todo el pipeline multiplicado**: `build_plan()` y
  `generate_variants()` expanden solos, así que el plan declarativo
  (edificio con `floors` reales, LEVEL/SPACE/WALL/DOOR/WINDOW por
  copia, pasillo y núcleo rígido con el nombre de su copia) y la
  puntuación de variantes (área, muros, coste PRECONS vivo) salen
  sobre el EDIFICIO entero, no sobre una planta. El DXF/IFC y las
  cantidades heredan la multiplicación por el modelo, sin tocar
  exportadores.
- **Paso 2 del asistente**: columna «Repetir», entrada de
  multiplicador al añadir nivel (con aviso amable si no es entero
  1..50), botón «× Repetir seleccionado...» para cambiarlo en caliente
  y línea de resumen «N niveles · altura total X m»; tooltip «repeat»
  en la ayuda dinámica.
- Regresión nueva (`tests/test_164_niveles_multiplicador.py`, 22
  pruebas: identidad, nombres únicos con colisión, locales
  duplicados, relaciones intactas, cotas, plan ×3 con 12 espacios y
  núcleo por copia, pasillos por copia, torre ×50, variantes idénticas
  al edificio escrito a mano y plan con variante) y check 74 del
  selftest.

## Novedades v3.31.0 — P2: DXF R12 ASCII Y COSTE LIGADO AL CHECK

- **DXF R12 de máxima compatibilidad** (`exporters/dxf_exporter.py`):
  el mismo plano que el R2010 pero en entidades CLÁSICAS — LINE/ARC/
  TEXT, sin LWPOLYLINE que R12 no conoce — todo al modelspace con un
  bloque desplazado por nivel rotulado «PLANTA_<NOMBRE>»; lo abren
  AutoCAD R12, CNC y visores antiguos. El R2010 queda intacto y la
  versión equivocada responde con error amable ARQ-EXP-061.
- **Entradas**: menú Archivo → «Exportar DXF R12 (compatibilidad)...»
  y CLI `export --format dxf --r12`.
- **Coste ligado al check** (`services/coste_informe.py`): los TRES
  informes de validación (vivienda §54, comercial CC/OF y educacional
  ED) llevan la instantánea del presupuesto PRECONS III activo —
  costo directo, transporte, indirectos, beneficio, TOTAL y coste
  por m² sobre los locales del modelo — en el cuadro de texto y como
  sección «Coste del proyecto» del HTML autocontenido. La instantánea
  es SOLO LECTURA (usa `latest()`, nunca `ensure_active()`): sin
  presupuesto con renglones NO se inventa nada y el informe sale sin
  la sección. El coste es informativo y jamás bloquea una validación.
- Regresión nueva (`tests/test_163_dxf_r12_coste.py`, 15 pruebas:
  AC1009 sin LWPOLYLINE, ASCII puro, dos niveles en modelspace, R2010
  intacto, servicio con opción version, flag CLI, y la instantánea
  con el renglón oficial 011111 x 500 = 13 405.00 CUP directos) y
  check 73 del selftest.

## Novedades v3.30.0 — SERVICIOS DE VIVIENDA: PISCINA §45, ACÚSTICA §46 Y DOMÓTICA §39

- **Piscina §45 como SISTEMA INDEPENDIENTE**
  (`domain/vivienda_servicios.py`): volumen por profundidad media,
  renovación total (6 h de referencia, configurable) con su caudal de
  filtración, bomba estimada por rendimiento hidráulico
  (P = 1000·9.81·Q·H/η), skimmers (1/35 m²), impulsión (1/25 m²),
  focos LED submarinos (1/20 m²), checklist de seguridad (cierre de
  1.20 m, alarma de inmersión, profundidades pintadas, rescate),
  equipotencialidad y drenaje marcados, y 7 equipos de referencia en
  CUP con total.
- **Acústica §46 midiendo el trazado**: fuentes (cocina, baños,
  equipos) contra dormitorios con MUROS COMPARTIDOS detectados por
  solape colineal (funciona con muros largos que sirven a varios
  locales), vano perimetral probado por SUB-SEGMENTO alrededor del
  punto medio del vano (detecta la puerta de acceso aunque esté en un
  muro largo), espesor medido en mm por par, soluciones de referencia
  (material, espesor, doble tabique, R_w tipo DB-HR con la nota de
  que la norma local manda), medianera según tipología, vidrio
  acústico de fachada según tráfico y aislamiento de cubierta; el R_w
  final queda en REQUIERE_CALCULO_ESPECIALIZADO.
- **Domótica §39**: plan para los 8 sistemas (ILUMINACION, SEGURIDAD,
  CLIMATIZACION, PERSIANAS, RIEGO, ENERGIA, AGUA, ACCESO) con 16
  reglas de conteo sobre el modelo (pasillos y escaleras, habitables,
  puertas exteriores, ventanas de la planta de acceso, zonas verdes,
  locales húmedos), monitor doble si hay solar FV y equipos de
  referencia en CUP con total; RED, PANEL y ALIMENTACION quedan como
  diseño del instalador.
- **Datos versionados** (`resources/knowledge/vivienda_servicios.json`
  v1.0.0, formato ARQ_GEN_VIVIENDA_SERVICIOS): valores de REFERENCIA
  declarados con su nota y su fuente; errores amables ARQ-VSR-001/002
  y ARQ-PIS-001/002.
- **GUI**: tres menús en Herramientas — «Piscina (catálogo §45)...» con
  formulario que acepta coma decimal, valores vacíos = referencia y
  Guardar HTML del informe, «Acústica de la vivienda (catálogo
  §46)...» y «Plan domótico (catálogo §39)...» con «Guardar HTML...» —
  con tooltips propios.
- **Informe HTML**: secciones de TABLAS genéricas (pares acústicos,
  soluciones del §46, equipos de piscina y plan domótico) reutilizables
  por cualquier dominio.
- Regresión nueva (`tests/test_162_vivienda_servicios.py`, 24 pruebas)
  y check 72 del selftest (fuente + conductual con valores calculados
  a mano: 48 m³, 8 m³/h, 0.40 kW y 209 800 CUP).

## Novedades v3.29.0 — COMPARADOR DE VARIANTES DE PLANTA

- **Matriz N x 9 columnas** (`ui/variant_budget.py`): nº, variante,
  esquema, cabe en lote, puntos, área m², coste PRECONS vivo, coste/m²
  y avisos, con una fila por variante del motor (28 en la vivienda
  clásica) ordenada por puntuación — la mejor arriba.
- **Líderes declarados**: mejor puntuación y menor coste/m² (con el
  takeoff vivo ya adjuntado); si el coste no está calculado, el
  comparador LO DECLARA en vez de inventar (misma honradez de siempre).
- **Salidas**: texto cp1252 para consola/cuadros y CSV «;» utf-8-sig
  para Excel (menú Guardar CSV del diálogo).
- **GUI**: botón «Comparar variantes» en el paso 6 del asistente, junto
  a «Generar variantes», con tooltips `cmp_variants` y
  `cmp_variants_csv`; comparar es SOLO LECTURA.
- Regresión nueva (`tests/test_161_comparador_variantes.py`, 17
  pruebas: matriz real, orden por puntos, área desde layouts, honradez
  sin coste, cabe Sí/No, suma de avisos, coste y coste/m² con takeoff
  de juguete, líder correcto, texto cp1252, CSV parseable y
  determinista, variantes de escuela secundaria y marcadores).

## Novedades v3.28.0 — PRESETS DE CONFIGURACIÓN DEL ASISTENTE

- **La configuración viaja en JSON local** (`ui/presets.py`): 43
  campos de los pasos 1/4/5 y concepción de espacios (uso, tipología,
  tamaño ED, lote, forma, estilo, clima, región Neufert, vanos,
  pasillo, instalaciones, cubierta, mobiliario...) con formato
  `ARQ_GEN_PRESET` v1 en `presets/` junto al programa (o donde apunte
  `ARQ_GEN_PRESETS`).
- **El PROGRAMA no viaja**: niveles, locales y relaciones se
  regeneran desde el uso, así el preset sigue válido cuando el motor
  mejora; los valores ilegales de otro origen AVISAN y conservan lo
  actual en vez de romper el asistente.
- **Errores amables ARQ-PRE-001..006**: nombre ilegal, datos raros,
  escritura fallida, preset ausente, JSON corrupto (el listado lo
  marca «ilegible» y sigue) y formato/versión desconocidos.
- **GUI**: fila «Preset de configuración» en el paso 1 con combo y
  botones Guardar / Cargar / Eliminar (tooltips `bld_preset_combo`,
  `bld_preset_save`, `bld_preset_load`, `bld_preset_del`); al cargar
  se repintan los widgets del asistente desde la data.
- Regresión nueva (`tests/test_160_presets.py`, 18 pruebas: foto de
  data, ciclo completo, enteros con coma decimal, avisos de valores
  ilegales, resumen por uso cp1252, slug seguro, errores 001..006,
  carpeta por env/base/defecto y marcadores).

## Novedades v3.27.0 — INFORME DE VALIDACIÓN EN HTML AUTOCONTENIDO

- **El informe sale del programa** (`exporters/informe_html.py`): los
  mismos datos de «Validar vivienda / comercial / educacional» se
  exportan a UN solo archivo .html con CSS embebido, UTF-8 declarado,
  cero URLs externas y cero dependencias nuevas — se abre en el
  navegador, se adjunta al expediente o se imprime sin ARQ_GEN.
- **Honradez visual intacta**: cada comprobación conserva su severidad
  (OK/FALLA/AVISO/INFO) y su estado — «(pendiente)» y
  «(REQUIERE_CALCULO_ESPECIALIZADO)» se IMPRIMEN, no se esconden; el
  pie repite que el informe no sustituye el cálculo especializado.
- **Genérico y seguro**: sirve para los tres dominios (hallazgos como
  dicts o como objetos), con chips de metadatos, resumen de badges,
  locales con fallos, secciones del documento (reglas, prioridades,
  conflictos, normativa, documentación), escapado total del contenido
  y error amable ARQ-EXP-060 si la ruta no deja escribir.
- **GUI**: botón «Guardar HTML...» en los tres cuadros de validación
  (tooltip `val_html_save`); se exporta EXACTAMENTE el informe
  mostrado.
- Regresión nueva (`tests/test_159_informe_html.py`, 12 pruebas:
  HTML5 autocontenido, escapado, chips, badges, estados honestos,
  locales, secciones, pie con versión, informe vacío, escritura y
  ARQ-EXP-060).

## Novedades v3.26.0 — ESCUELAS Y CÍRCULOS INFANTILES

- **El documento como datos** (`resources/knowledge/educacion_specs.json`,
  nuevo): «Especificaciones técnicas, funcionales y dimensionales -
  Escuelas primarias, secundarias, círculos infantiles y albergues
  escolares» (125 secciones) integrado versionado: 4 tipologías
  ED-01..04 (§0), capacidades paramétricas del §4/§9/§48 (escuelas de
  60 a 1.200 alumnos con `NUM_AULAS = CEIL(alumnos / alumnos por
  aula)` y 20-25 alumnos/aula, 6 grupos de edad del círculo infantil,
  albergues de 20 a 300+ plazas con comedor al 50 % simultáneo del
  §56), 82 cuadros de cotas MIN/REC con unidad y nota (aulas de
  primaria 40 m² §5 y secundaria 45 m² §6, aula flexible §7, aula
  infantil §8, sala de cuna §10, juego interior/exterior §12-13,
  patio §14, porches §15, circulaciones §16, biblioteca §22,
  laboratorios §23-24, taller §25, arte §27, música §28, actos §29,
  gimnasio 12×18 y 6-9 m §30, cancha §31, vestuarios §32, enfermería
  §34, aislamiento §35, comedor §36, cocina §37, sanitarios §39-42,
  almacenamiento §43, limpieza §44, escaleras §45, rampas §46,
  ascensores §47, dormitorios individuales 9-14 m² / 2 plazas 14-20 /
  colectivos 4-6 m² por persona §49-51, comedor y cocina de albergue
  §56-57, lavandería §58, baños colectivos §59, monitores §62,
  accesos §65, cercas §66, transporte §69, estacionamiento §70,
  bicicletero §71, técnicos §72, residuos §73, iluminación natural
  §76, punto de reunión 0,5-1,0 m²/persona §104-105), relaciones
  espaciales del §98-101 en escala 0-3 (aula-higiene-juego-descanso,
  acceso-control-administración, dormitorios-baños-duchas…) CON los
  flujos limpio/sucio prohibidos del §102 (estudiantes-carga,
  cocina-basura, ropa limpia-sucia y residuos contra público a nivel
  0), programas mínimos del §106-109 (20 ítems primaria, 21
  secundaria, 22 círculo infantil y 23 albergue, con los espacios
  exteriores marcados), reglas de validación del §111-112 (incluida
  la condicional «SI ALUMNOS > 300 ENTONCES NUM_AULAS >=
  CEIL(ALUMNOS/25)»), 18 conflictos del §115, climas del §116,
  materiales de pisos/paredes/techos con espesores del §92-94,
  seguridad infantil del §89, normativa seleccionable y fuentes
  OMS/UNICEF del §124.
- **Asistente** (`ui/building_wizard.py`): uso social nuevo «Escuela
  secundaria» con su programa básico, y PROGRAMA PARAMÉTRICO por
  tamaño/capacidad para los cuatro usos educativos (combo «Tamaño /
  capacidad (documento ED)»): primaria/secundaria generan las aulas
  con la fórmula del §4 a 25/30 por aula, el círculo infantil genera
  un aula + higiene + descanso por grupo (§9) con sala de cunas,
  y el albergue genera dormitorios colectivos de 8 plazas (§48/§51);
  el comedor sale dimensionado por capacidad (50 % simultáneo × 1,40
  m² del §36/§56), las medidas vienen de los cuadros MIN/REC y del
  DNA, las relaciones del §98-101 se sugieren con puerta en las
  prioritarias y los flujos del §102 nunca se trazan. «(programa
  básico)» conserva los programas estáticos de siempre. Metadata
  educacional (familia, tamaño, alumnos/grupos/plazas) con
  round-trip, avisos de seguridad infantil §89, recorridos §98,
  dormitorios-ruido §90, gimnasio §30 y comedor §36.
- **Validación honesta** (`domain/educacion_specs.py`, nuevo):
  `validar_local` controla superficie contra cuadro y DNA (E01,
  con los m² por usuario del documento), ancho (E02), altura libre
  del nivel (E03, §2), puertas (E04 con la nota 0,914 m de
  evacuación), pasillos (E05) y profundidad de aula (E06, §76:
  6-10 m orientativos, máx 10-12). `validar_proyecto` evalúa el
  edificio: EM01 programa mínimo §106-109 (con los exteriores como
  pendientes del terreno), EM02 relaciones prioritarias §98-101,
  EM03 prohibiciones de flujo §102, EM04 aulas vs capacidad
  (REGLA_01/11), EM05 dormitorios por m²/persona (§49-51), EM06
  comedor por comensales (REGLA_08), EM07 escaleras §45, EM08
  punto de reunión §104-105 (`AREA_REUNION = POBLACION × 0,5-1,0`),
  EM09 alturas libres §2, EM10 seguridad infantil §89 (pendiente de
  verificación) y RC01-06 para los temas que el documento remite a
  cálculo (climatización §78, incendios §83-84, evacuación §85,
  CCTV §87, acústica §90-91, electricidad-hidráulica §74/§79-81),
  todo con estados honestos medido/pendiente/requiere cálculo.
- **DNA, iluminación y presupuesto**: 17 tipos educativos nuevos en
  `space_dna.json` (aula infantil, sala de cuna, dormitorio
  colectivo, juego interior/exterior, patio, sala de profesores,
  laboratorio de computación, taller tecnológico, arte, música,
  gimnasio, enfermería, estudio, monitores, higiene de círculo
  infantil y convivencia) con sus lux en `LUX_POR_USO` (§75: no un
  único lux para todo el establecimiento) y equipos de referencia
  sin calidad en el presupuesto vivo (PC de aula, banco de taller,
  lote de gimnasia, camilla, cuna, mesa de cambio, litera, piano).
- **GUI** (`ui/app_window.py`, `ui/help.py`): combo de tamaño en el
  paso 1 del asistente, menú «Validar escuela / círculo infantil /
  albergue (documento ED)…» en Herramientas con el informe completo
  (comprobaciones, reglas §111-112, prioridades, conflictos §115 y
  fuentes), tooltips `bld_edu_tam` y `tools_edu_validar`.
- Regresión nueva (`tests/test_158_educacion_specs.py`, 30 pruebas:
  documento v1.0 completo y cacheado, errores ARQ-EDU-001/002,
  capacidades y fórmula, mínimos de cuadros, relaciones con flujos y
  override del aula infantil, programas §106-109, reglas/conflictos/
  seguridad/fuentes, tamaños paramétricos, los cuatro programas
  paramétricos, programa básico intacto, validación/parseo,
  metadata y avisos, round-trip, validación honesta con proyecto
  generado, local escaso, capacidad insuficiente, flujo prohibido,
  albergue por huellas, texto cp1252, equipos y GUI).

## Novedades v3.25.0 — CENTROS COMERCIALES Y OFICINAS

- **El documento como datos** (`resources/knowledge/comercial_specs.json`,
  nuevo): «Especificaciones técnicas y dimensionales - Centros
  Comerciales y Edificios de Oficinas» v2.0 (104 secciones) integrado
  versionado: 20 tipologías CC-01..CC-10 / OF-01..OF-10 (§1), 59
  cuadros de cotas MIN/REC con unidad y nota (galerías §6, locales
  §7, escaparates §8, oficinas §10, planta abierta §11, coworking
  §12, reuniones/conferencias §13, sanitarios §25, comedores §27-29,
  cuartos técnicos §32, ductos §33, estacionamiento §45, rampas
  vehiculares §46, andén §47, residuos §48, bicicletas §75…),
  relaciones espaciales del §78 en escala 0-3 CON las prohibiciones
  duras (residuos/carga/técnicos nunca contra público), programas
  mínimos del §89-90, porcentajes de áreas del §81, eficiencia de
  planta del §82 (oficinas 75-90 %, comercial 65-85 %), conflictos
  del §95 con las prioridades P01-P12 del §104, normativa
  seleccionable del §97 y fuentes del §98 (IBC 2024).
- **Asistente** (`ui/building_wizard.py`): dos usos sociales nuevos,
  «Centro comercial» y «Oficinas (torre/corporativo)», que cargan el
  PROGRAMA MÍNIMO del §89-90 con medidas derivadas de los cuadros
  MIN/REC y del DNA (la galería nace de 30 m² con 6,00 m de ancho, el
  local de venta con su frente, el ancla con sus 500 m²), relaciones
  del §78 como sugerencias (nivel 3 con puerta, 1-2 adyacentes, 0 no
  se genera), combo de tipología CC/OF del §1 con metadata y
  round-trip, planta tipo automática en la torre/corporativo/mixto
  (OF-03/OF-04/OF-10: el bloque de trabajo sube a la Planta 1),
  instalaciones sugeridas y avisos propios (§85 uso mixto, §22
  escaleras mecánicas pendientes de fabricante, evacuación IBC por
  ocupación). El DNA suma 18 tipos comerciales con área, ancho, lux,
  mobiliario y equipos (neufert), y la iluminación los cubre
  (venta 300, trabajo 500, circulación comercial 250 lx).
- **Validación** (`domain/comercial_specs.py`, nuevo):
  `validar_local` controla UN local contra su cuadro (C01 superficie
  con las gamas recomendadas, C02 ancho, C03 altura libre del nivel,
  C04 puertas con el mínimo IBC de evacuación §61, C05 pasillos) y
  `validar_proyecto` evalúa el edificio entero (CM01 programa mínimo,
  CM02 relaciones prioritarias trazadas, CM03 prohibiciones del §78,
  CM04 porcentajes §81, CM05 eficiencia §82, CM06 estacionamiento
  §45, CM07 evacuación IBC 2024 §17/§61, CM08 galería §6, RC01-RC08
  los temas de cálculo) con estados honestos medido / pendiente /
  REQUIERE_CALCULO_ESPECIALIZADO (§101): HVAC, rociadores, detección,
  CCTV, escaleras mecánicas, extintores y drenaje quedan marcados
  sin inventar números.
- **GUI** (`ui/app_window.py`): menú Herramientas + «Validar centro
  comercial / oficinas»… con el informe completo (cabecera de familia
  y tipología, comprobaciones, locales con fallos, prioridades,
  conflictos, normativa y fuentes) y tooltips propios. **Presupuesto
  vivo** (`ui/variant_budget.py`): equipos de referencia CC/OF sin
  calidad (cámara CCTV, monitor, rack 19″, torniquete, nivelador y
  sello de andén, parillero, campana industrial) — la categoría
  «Equipos» no la escala el nivel de acabados.

## Novedades v3.24.0 — ESTUDIOS DE VIVIENDA: ALTERNATIVAS, MODULACIÓN Y SOLAR

- **Alternativas comparables §62-63** (`domain/vivienda_estudios.py`,
  nuevo): para la misma entrada (tipología + dormitorios + baños +
  estilo + sistema) el estudio genera SIETE alternativas — A/B/C por
  nivel de acabado (Económica/Estándar/Premium, niveles 1/2/4 del
  §51, con el sistema del proyecto) y 1/2/3/4 por sistema
  constructivo (mampostería confinada, hormigón aporticado, steel
  framing y modular prefabricado al nivel estándar) — cada una con
  las métricas de comparación del §63: superficie de referencia (la
  REAL de los locales del proyecto, o el programa paramétrico del
  §7), costo índice por m² y % relativo frente a la B, meses de
  construcción, hormigón m³, acero kg, mampostería m², madera m³,
  consumo kWh/m²·año, mantenimiento %/año, vida útil, complejidad
  1-3 y disponibilidad (MODO CUBA). Los datos viven en el bloque
  `comparacion_sistemas` del catálogo (v1.1): valores de REFERENCIA
  visibles y editables (§66), no precios oficiales — la misma
  honradez de FACTOR_CALIDAD. La recomendación elige el costo menor
  con compatibilidad >= 2/3 con el estilo (§27: avisa, no bloquea).
- **Modulación constructiva §56** (`domain/vivienda_estudios.py`):
  evalúa los locales, muros, puertas y ventanas del proyecto contra
  el módulo elegido (MODULO_0.60, MODULO_1.20, MODULO_1.25,
  MODULO_1.50 o personalizado) para reducir desperdicios: % de
  piezas en módulo, residuo lineal acumulado y, para cada pieza
  fuera de módulo, la sugerencia al múltiplo inferior y superior
  (un muro de 4.30 m con módulo 1.20 pide 3.60 o 4.80). El informe
  SUGIERE, no bloquea.
- **Energía solar §38** (`domain/vivienda_estudios.py`): dimensiona
  el sistema FOTOVOLTAICO, SOLAR_TERMICO o HIBRIDO con las entradas
  del documento (consumo diario, horas de sol pico, potencia del
  panel, eficiencia, pérdidas, autonomía, ocupantes) y devuelve las
  salidas exactas del catálogo: número de paneles, potencia total,
  capacidad de batería (por profundidad de descarga), potencia del
  inversor y superficie de techo requerida; el térmico añade
  colectores y tanque por ocupante. Los parámetros de referencia
  viven en el bloque `energia_solar` del catálogo (HSP 5.0 por
  defecto, configurable §66/§71) y cualquier parámetro vacío toma
  su valor. La instalación definitiva queda marcada
  REQUIERE_CALCULO_ESPECIALIZADO (§81).
- **GUI: tres estudios en Herramientas** (`ui/app_window.py` +
  `ui/help.py`): «Alternativas de vivienda (catálogo §62-63)» con la
  tabla comparativa y la recomendada, «Modulación constructiva
  (catálogo §56)» con selector de módulo y evaluación al vuelo, y
  «Solar fotovoltaica (catálogo §38)» con formulario paramétrico
  (acepta coma decimal y vacíos = valor de referencia). Todo de
  solo lectura, con tooltips propios y mensajes amables.

## Novedades v3.23.0 — CATÁLOGO MAESTRO DE VIVIENDAS

- **El documento entra al programa como DATOS, no como texto**
  (`resources/knowledge/vivienda_catalogo.json`, nuevo): las 30
  tipologías VIV-01..30 con las reglas y configuraciones de las
  desarrolladas (aislada con sus UFA001-005, pareada, adosada,
  multifamiliar, dúplex y patio), los 25 sistemas constructivos con
  sus variables (mampostería, confinada, aporticado, acero, madera,
  steel framing, prefabricados...), los 20 sistemas estructurales,
  los 30 estilos con sus 48 reglas (colonial: patios, galerías,
  grandes vanos...), la matriz de compatibilidad estilo × sistema
  (escala 0-3 del §27: incompatible/posible/compatible/altamente
  compatible — 13 pares literales del documento más los razonados
  según sus reglas de estilo; advierte, nunca bloquea), los 21
  rangos de locales del §7, las 17 relaciones del §8 con la X de
  baño-comedor, la zonificación Z001-Z008 del §9, las 30
  validaciones VIV001-030 del §54, los 15 conflictos del §65 con su
  validación equivalente, la modulación, los niveles de acabado
  1-5, la progresiva por 5 fases, multigeneracional, accesible, las
  jurisdicciones del §69 con el MODO CUBA del §70, los criterios
  tropicales y de huracanes, y el principio de seguridad técnica
  del §81: las dimensiones estructurales definitivas quedan
  marcadas REQUIERE_CALCULO_ESPECIALIZADO.
- **Validación de vivienda VIV001-030 (sección 54)**
  (`domain/vivienda_specs.py`, nuevo): `validar_vivienda()` evalúa
  las 30 comprobaciones sobre el proyecto abierto — huella y
  ocupación contra la parcela, estacionamiento, luz y ventilación
  de dormitorios y baños, extracción de cocina, escalera dentro de
  Blondel, puertas accesibles, módulos eléctrico y sanitario,
  cubierta con drenaje, estructura definida, compatibilidad
  estilo-sistema, sistema contra el clima, superficies sumadas,
  locales con categoría y servidos, mobiliario ubicado, puertas
  colgadas de muro y ventanas en fachada, habitaciones con acceso —
  y cada hallazgo declara su estado con honestidad: MEDIDO (la
  geometría lo decide), PENDIENTE (parámetro urbano configurable
  del §66) o REQUIERE_CALCULO_ESPECIALIZADO (puesta a tierra, suelo
  antes de cimentación, cargas — §81). Solo lectura: no crea
  entidades ni toca el undo. El menú Herramientas estrena «Validar
  vivienda» con el informe completo y su resumen.
- **Programa paramétrico de vivienda en el asistente**
  (`ui/building_wizard.py`): el paso 1 añade «Tipología de vivienda
  (catálogo)» con las 30 etiquetas + el programa clásico de siempre
  (intacto para los proyectos existentes), y los contadores de
  DORMITORIOS (1-6) y BAÑOS (1-4). Al cargar el programa del uso:
  ZONA SOCIAL (vestíbulo, sala, comedor, cocina), PRIVADA
  (dormitorio principal + secundarios y sus baños — principal,
  social de 1,5-3 m², compartidos) y SERVICIO (lavandería,
  despensa), con las medidas tomadas de los rangos del §7, los
  EXTRAS de la tipología (garaje de la aislada, suite de abuelos,
  cuarto técnico de la progresiva...), las RELACIONES del §8
  convertidas en sugerencias (nivel 3 = comunicado con puerta; la
  X de baño-comedor no se genera, se avisa), DÚPLEX y TRÍPLEX
  partidos en planta social y planta privada creando la Planta
  Alta, metadata con tipología/dormitorios/baños y round-trip al
  regenerar. `vivienda_advisories()` añade al resumen la
  compatibilidad 0-3 del par elegido, la medianera de la pareada,
  la escalera del dúplex, las fases de la progresiva y los retiros
  de la aislada.
- **Calidades del presupuesto vivo 1-5 (§51)**
  (`ui/variant_budget.py`): la escala Económica/Estándar/Premium
  crece a CINCO niveles alineados con el catálogo — Económica
  0,85, Media 0,95, Estándar 1,00, Premium 1,30 y Lujo 1,60 sobre
  el coste directo de acabados; la obra gruesa sigue a 1,0 y los
  equipos quedan fuera — con las tres calidades históricas
  conservando nombre y factor para no romper proyectos ni pruebas.

## Novedades v3.22.0 — ESPECIFICACIONES TÉCNICAS HOSPITALARIAS Y VALIDACIÓN DIMENSIONAL

- **El documento entra al programa como DATOS, no como texto**
  (`resources/knowledge/hospital_specs.json`, nuevo): las 60 FICHAS
  cualitativas de locales (función, relaciones, arquitectura,
  electricidad, iluminación, hidráulica, HVAC, gases medicinales,
  radiación, presión, higiene, equipamiento y seguridad), el CUADRO
  DE COTAS MIN/REC de 53 tipologías (del quirófano FGI 6,10 × 6,10 m
  a la cámara frigorífica de 0,90 × 2,30 m por cuerpo), la matriz de
  prioridad funcional (crítica/alta/media/baja), los flujos
  incompatibles, las cotas de puertas y mobiliario, el checklist de
  la sección 19, la clasificación de cotas TIPO A-F y las fuentes
  (FGI, ASHRAE/ASHE 170, IAEA, OMS, AusHFG, NFPA). La regla del
  documento se respeta en el programa: una cota de programación,
  recomendada o de fabricante NUNCA se anuncia como normativa.
- **Control de validación dimensional por local (sección 19)**
  (`domain/hospital_specs.py`, nuevo; `ui/editor_espacios.py`):
  `validar_local()` mide el local contra su uso — superficie, ancho,
  altura del nivel, puertas y pasillos — y devuelve hallazgos
  V01-V05 con su severidad y el checklist completo con lo geométrico
  medido y lo de cálculo/fabricante pendiente; `validar_proyecto()`
  suma por severidad en todo el edificio. El asistente de local
  estrena el botón «Validar cotas» (el informe sale en el cuadro de
  diagnóstico, cp1252 a prueba de consola) y todo es de solo lectura:
  la validación no crea entidades ni toca el undo.
- **40 especialidades nuevas en el DNA**
  (`resources/knowledge/space_dna.json`, 77 tipos): sala de
  autopsias, preoperatorio, recuperación postanestésica, resonancia,
  ecografía, UCI pediátrica, UCI neonatal, aislamiento, biología
  molecular, banco de sangre, toma de muestras, sala de
  procedimientos, endoscopia, hemodiálisis, farmacia estéril,
  rehabilitación, hidroterapia, obstetricia/partos, neonatología,
  pediatría, odontología, oftalmología, dermatología, cardiología,
  hemodinamia, medicina nuclear, anatomía patológica forense,
  central de gases, cuarto eléctrico, grupo electrógeno, UPS, cuarto
  de bombas, lavandería, ropa limpia, ropa sucia, cuarto de
  limpieza, administración, archivo clínico, admisión y almacén
  estéril — cada una con área mínima y preferida del cuadro, puerta
  de camilla, pasillo que pide, metadata técnica (presión, blindaje,
  incubadoras, antecámara, tratamiento de agua...) y adjacencias
  clínicas. Sus lux (entrega 500, resonancia 150...), su mobiliario
  (cunas en neonatología, lavadoras en lavandería, archivadores en
  el archivo clínico) y sus equipos de referencia (resonancia,
  angiógrafo, gammacámara, incubadoras, máquinas de diálisis...)
  entran en las capas de siempre.
- **La ficha PDF del local crece con el documento**
  (`exporters/ficha_local.py`): secciones «Especificaciones técnicas
  del uso» (la ficha cualitativa completa con su prioridad
  funcional), «Cotas de referencia del uso» (mínima, recomendada,
  cota típica y superficie real), «Control de validación dimensional»
  (hallazgos medidos + checklist §19) y «Fuentes y advertencia».
  El recurso viaja en el bundle de PyInstaller y la verificación
  post-compilación lo exige (`compilar_bundle.py`); selftest llega a
  **64 checks** con el check 64 autocontenido.
- **BUG de persistencia corregido de paso**: `create_project` y
  `open_project` insertaban su evento de ciclo de vida DESPUÉS del
  commit y dejaban la transacción de escritura ABIERTA — un contexto
  descartado que el recolector de basura tardara en recoger retenía
  el lock de SQLite y la siguiente escritura del proceso moría con
  «database is locked» (visible en el presupuesto PRECONS tras abrir
  un proyecto dos veces). Ahora el evento se confirma en el propio
  ciclo de vida y la conexión queda ociosa; la conexión sin
  transacción abierta está cubierta por prueba.

---

## Novedades v3.21.0 — PASILLOS HOSPITALARIOS, EQUIPOS EN EL PRESUPUESTO VIVO Y FICHA DEL LOCAL

- **El pasillo obedece a los LOCALES, no solo al uso**
  (`resources/knowledge/space_dna.json`, `ui/building_wizard.py`):
  cada especialidad del DNA trae su «pasillo_m» como datos — 2,40 m
  donde pasa una camilla (hospitalización, UCI, quirófano,
  tomografía, fluoroscopia, urgencias, cuidados progresivos), 2,00 m
  donde ruedan carros y camillas de servicio (morgue, anatomía
  patológica, esterilización, almacén), 1,80 m para laboratorio y
  local de desechos y 1,50 m para el nodo informático. El asistente
  sube el ancho del pasillo al máximo que pida el LOCAL más exigente
  del programa (solo sube, nunca reduce), y el aviso normativo cita
  al culpable: «el programa pide 2,40 m (por «Tomografía (TAC)» pasa
  una camilla)». La vivienda y los usos sin locales de camilla se
  quedan exactamente como estaban.
- **El presupuesto vivo factura los APARATOS de las especialidades**
  (`ui/variant_budget.py`): nueva categoría «Equipos» — el catálogo
  oficial PRECONS III instrumenta la construcción pero no publica el
  precio de lista de los aparatos médicos, así que cada local de
  salud aporta sus equipos con un PRECIO DE REFERENCIA visible y
  determinista (misma honradez que el factor de calidad):
  tomógrafo helicoidal, consola de reconstrucción, arco C,
  radiología convencional, lámpara escialítica, equipo de anestesia,
  monitor y ventilador por UCI, carro de paro, microtomo,
  autoclave, cámara frigorífica, cabina de bioseguridad clase II,
  campana de laboratorio, SAI con rack, contenedor sanitario y
  transpaleta. Las filas viajan con su precio en la propia fila
  (fuente «referencia»), no se buscan en el ruleset y la calidad de
  acabados NO las toca — un tomógrafo no se «revestimenta».
- **La FICHA IMPRIMIBLE del local, en PDF**
  (`exporters/ficha_local.py`, `ui/editor_espacios.py`,
  `ui/app_window.py`): el asistente de local estrena el botón «Ficha
  PDF...» junto al diagnóstico: reúne identidad y medidas, DNA del
  uso con su ficha técnica (radiación, frigocámara, bioseguridad,
  SAI, extracción…), tabla de vanos, mobiliario, instalaciones,
  PLANTA DIBUJADA (muros del local recortados a sus aristas —
  gruesos los propios y finos los compartidos—, huecos de puertas
  con su arco de giro hacia dentro y ventanas con marco, todo a
  escala) y el diagnóstico completo. PDF 1.4 100 % stdlib, el mismo
  motor del presupuesto PRECONS III; `geometria_local()` y
  `_tramos_en_aristas()` dejan el recorte disponible para quien
  dibuje después.

## Novedades v3.20.0 — ASISTENTE DE LOCAL PARA MODIFICAR + ESPECIALIDADES DE SALUD

- **El «Asistente de local» ahora MODIFICA un local existente**
  (`ui/editor_espacios.py`, `ui/app_window.py`): el botón de la barra
  abre un asistente completo con 5 pestañas — Local, Geometría, Vanos,
  Instalaciones y Mobiliario — sobre el local que elijas, con el
  diagnóstico DNA siempre visible a la derecha. Identidad: nombre y
  uso con validez DNA (área mínima y puerta de camilla del uso se
  avisan; el tipo desconocido se rechaza amablemente) y reamueblado
  opcional al cambiar el uso. Geometría: redimensionar (muros
  exclusivos y vanos re-proyectados), MOVER el local completo
  (boundary, muros exclusivos y mobiliario; los muros compartidos se
  avisan), espesor de todos sus muros exclusivos y COTA DEL PISO.
  Vanos: crear acceso con el ancho del uso (o el que escribas),
  crear ventana con el hueco de ventilación, y retocar ancho, alto,
  antepecho y posición del vano que elijas de la lista o darlo de
  baja. Instalaciones: conectar a eléctrica y sanitaria, ILUMINAR
  este local con la lámpara del catálogo y los lux del uso (el resto
  del proyecto conserva sus luminarias) y PROTEGER con alarma. Todo
  por los caminos oficiales: comandos, auditoría, undo persistente,
  QTO y reanclado de instalaciones.
- **Las especialidades de salud pedidas entran al taller**
  (`resources/knowledge/space_dna.json`, `ui/building_wizard.py`):
  tomografía (TAC), fluoroscopio, anatomía patológica, morgue,
  cuidados progresivos, laboratorio de microbiología, nodo
  informático, local PGD (gestión de desechos) y almacén — 9 tipos
  nuevos del DNA con área mínima, altura, puerta de camilla/carga,
  blindaje plomado en imagenología, cámara de frío y extracción
  independiente donde toca. El Policlínico y el Hospital del
  asistente de edificación incorporan las nuevas salas (el hospital
  pasa de 21 a 30 locales), con pares de puertas críticas y hint
  actualizados. Rayos X y laboratorio clínico ya vivían aquí.
- **Lux y equipamiento por especialidad** (`domain/iluminacion.py`,
  `domain/mobiliario.py`): la iluminación artificial ya conoce los
  lux hospitalarios (quirófano 1000, laboratorios 500, exploración
  300, morgue 200, lechos 100) y el catálogo de mobiliario suma mesa
  de operaciones, mesa de autopsias y rack de servidores, con reglas
  para quirófano, imagenología, UCI y las 9 especialidades nuevas —
  incluido el anclaje «fila» documentado desde la v1 y funcional
  desde aquí (estanterías de almacén y racks del nodo se repiten a lo
  largo del muro).
- Regresión nueva (`tests/test_151_salud_especialidades.py`, 22
  pruebas; `tests/test_152_asistente_local.py`, 27 pruebas headless y
  de GUI con Xvfb) y selftest en **62 checks**.

---

## Novedades v3.19.1 — SELECCIONAR EN EL PLANO VUELVE A FUNCIONAR

- **La mira ya no se come el clic** (`ui/app_window.py`): desde que
  existe la cruz estilo AutoCAD (v3.16.0) el objeto «current» de Tk
  era SIEMPRE la propia mira —que pasa por debajo del puntero— y el
  clic no seleccionaba locales, muros, ventanas, puertas ni nada. El
  picking ahora recorre los objetos de ARRIBA hacia ABAJO con
  `find_overlapping`, SALTA los superpuestos de dibujo (mira
  `acad_mira` y capa de la orden CAD `cadoverlay`) y resuelve el
  primer tag con fila real del explorador. Lo usan el clic, el doble
  clic (propiedades) y el menú del clic derecho.
- **El mobiliario, las cubiertas, rampas, barandillas y escaleras SON
  objetos** (`ui/models.py`): el explorador de Arquitectura nunca
  listaba FURNITURE/ROOF/RAMP/HANDRAIL/STAIR, así que el clic sobre
  un mueble atravesaba hasta el local y no había forma de
  seleccionarlos. Ahora aparecen en el árbol, se pueden buscar y el
  clic los selecciona con su ficha de propiedades (medidas y
  tipología en el resumen).
- Regresión completa nueva (`tests/test_150_seleccion.py`, 9 pruebas)
  con clic REAL sobre el lienzo (Motion + Button-1 con la mira
  activa): muro, local, puerta, ventana, mueble y escalera se
  seleccionan; clic en vacío conserva la selección; doble clic abre
  propiedades; clic derecho selecciona y abre el menú; y con una
  orden CAD activa (MOVER) el clic sigue alimentando la orden.

---

## Novedades v3.19.0 — ESCALERAS POR TIPOLOGÍA, ABERTURAS, ILUMINACIÓN Y ALARMAS

- **Escaleras según Neufert** (`domain/escaleras.py` + pestaña 🪜):
  cuatro TIPOLOGÍAS clásicas — **recta** (con meseta intermedia si el
  tramo pasa de 16 contrahuellas), **en L** (dos tramos a 90° con
  meseta cuadrada), **en U / doble piso** (tramos paralelos con hueco
  de una huella) y **de caracol** (peldaños en abanico alrededor del
  tubo, huella medida en la línea de paso al 2/3 del radio). La
  fórmula de **Blondel (2h + p = 0.60–0.64 m)** reparte el desnivel en
  contrahuellas iguales y el catálogo Neufert aconseja medidas por uso
  (Vivienda 0.175/0.28, salud pública 0.16/0.30…). La GEOMETRÍA
  generada (contorno, líneas de huella y cajas 3D de cada peldaño con
  sus cotas y giro) viaja en la metadata de la entidad STAIR: el
  lienzo 2D dibuja la planta con sus huellas y la vista 3D extruye
  los peldaños; QTO cuenta peldaños, huella en planta, desarrollo y
  barandilla a dos lados.
- **Tipos de puertas y ventanas** (`domain/aberturas.py` + pestaña
  🚪): la puerta ya no es solo un hueco — **abatible** (una o **doble
  hoja**), **corredera**, **plegable** (acordeón), **vaivén** y
  **pivote** central; la ventana gana **practicable**,
  **oscilobatiente**, **abatible**, **proyectante**, **corredera**,
  **guillotina**, **fija** y **pivotante**, cada una con sus hojas,
  su porcentaje de apertura útil y su antepecho aconsejado. La
  tipología se aplica a TODAS las del nivel con un clic (auditoría,
  undo persistente e invalidación) y el plano dibuja el SÍMBOLO de
  arquitectura de cada una: arco de giro, doble hoja espejada,
  corredera con doble línea, zigzag plegable, hoja a 45° de vaivén,
  triángulo de proyectante…
- **Iluminación artificial por tipos de lámparas**
  (`domain/iluminacion.py` + pestaña 💡): catálogo de **12 lámparas**
  — **LED** bombilla A60, panel 60×60, downlight, lineal/regleta,
  tira (por metro), campana industrial y proyector exterior, más
  fluorescente T8 y compacta, halógena, incandescente y sodio de alta
  presión — con potencia, flujo, temperatura de color, vida útil y
  eficacia lm/W calculada. El **método de los lúmenes**
  (N = E·A / (F·CU·MF)) dimensiona con los lux del uso del local
  (cocina 300, dormitorio 100, oficina 500…) y COLOCA las luminarias
  en retícula dentro de cada local como nodos LUMINAIRE reales de la
  red de alumbrado (misma auditoría, undo y QTO que cualquier
  instalación), con la potencia y el flujo en atributos para el
  balance eléctrico. La **comparativa** dice cuántas lámparas y
  cuántos watios pediría cada tecnología para la misma luz: la LED
  sirve la misma iluminación con una fracción de la potencia.
- **Alarmas contra intrusos por locales** (`domain/alarmas.py` +
  pestaña 🔔): el usuario ELIGE qué locales proteger en la lista y el
  sistema arma la red INTRUSION real — **detectores PIR** de esquina
  (1 por sector de ~12 m²), **contactos magnéticos** en TODOS los
  vanos del perímetro de cada local (reconoce los compartidos),
  **panel, teclado y sirena** en el local que se pida (sirena
  exterior opcional junto a la fachada sur) — con la zona nombrada en
  los atributos y la COBERTURA validada por el motor de intrusión
  (zonas, batería en Ah, hallazgos por zona). Idempotente: los
  dispositivos generados se retiran antes; lo cableado a mano se
  conserva.
- **Ingeniería**: entidad STAIR con migración 011 y repositorio
  propio; fórmulas QTO STAIR_COUNT/RISERS/FOOTPRINT/RUN/HANDRAIL;
  colores fijos en 2D y 3D para el PNG determinista; 9 pestañas en el
  taller de diseño con tooltips nuevos; 76 pruebas nuevas
  (test_146–149) y selftest en **61 checks**.

---

## Novedades v3.18.0 — ASCENSORES SEGÚN NEUFERT Y FACHADA: PARASOLES Y PIELES EXTERIORES

- **Ascensores con las tablas de Neufert** (`domain/ascensores.py` +
  pestaña 🛗 Ascensores del taller de diseño): el catálogo del libro
  (5.ª ed. en español) lleva capacidad y dimensiones de referencia
  para PASAJEROS (450 kg/6 personas a 2000 kg/26, con cabina, hueco y
  puerta central), HOSPITAL con camillas (puerta 1.20 m),
  MONTACARGAS y PANORÁMICO. El botón «Levantar hueco» elige la
  capacidad por el número de personas (o por kg en montacargas),
  calcula el FOSO, el PASO LIBRE SUPERIOR y la VELOCIDAD de referencia
  según el recorrido, recomienda la CANTIDAD por ocupación y uso
  (1 por ~75 en vivienda, ~175 en oficina, doble desde 7 plantas) y
  coloca el hueco REAL: dentro de un NÚCLEO o ESCALERA que lo acoja
  (con la puerta hacia el vecino más cercano) o ADOSADO a la fachada
  que pidas, con aviso. Errores propios `ARQ-ELE-001/002`; la tabla
  completa del tipo sale en la salida.
- **Parasoles por orientación** (`domain/fachadas.py` + pestaña
  🌤 Fachada): «auto» aplica la regla solar clásica — LAMAS
  HORIZONTALES al SUR (el sol cae alto), ALETAS VERTICALES a ESTE y
  OESTE (lo barre bajo) y NORTE sin parasol con aviso (luz difusa) —
  y puedes fijar el tipo a mano: horizontal, vertical, MIXTO (celosía
  en cruz) o LAMAS ORIENTABLES (45°). Materiales de aluminio, madera,
  acero corten, GRC, cerámica o textil, con vuelo, separación y banda
  vertical propias; cada PARASOL mide la línea de fachada del recinto
  del nivel y sus lámas entran en QTO como desarrollo total y ÁREA DE
  SOMBRA proyectada.
- **Pieles exteriores modernas** (misma pestaña): OCHO pieles
  contemporáneas con su CÁMARA VENTILADA (0.30-2.00 m) y su
  porcentaje de perforación — doble piel de vidrio, celosía de
  madera, malla metálica tejida, baguettes de terracota, panel
  metálico perforado, jardín vertical, paneles de GRC y
  policarbonato — y el ESTILO arquitectónico del asistente la SUGIERE
  en «auto» (Racionalista/Minimalista -> doble piel de vidrio,
  Sostenible -> celosía de madera, High-tech -> malla, Brutalista ->
  GRC, Contemporáneo -> terracota...). La piel sube desde su nivel
  base hasta el top del edificio y entra en QTO por superficie
  vestida y longitud de fachada.
- **Entidades oficiales y 3D**: ELEVATOR, PARASOL y SKIN con
  migración 010, auditoría, undo persistente, códigos
  `ARQ-ELEVATOR/PARASOL/SKIN-nnn` y regeneración; el 3D dibuja el
  hueco con su cabina y puerta central a la altura servida, las
  láamas de cada material y el plano de piel con su retícula
  (montantes, listones o baguettes según el tipo), con interruptor
  «🌤 Parasoles y pieles» en el diálogo 3D y PNG determinista.
- **GUI**: el taller de diseño crece a CINCO pestañas (mobiliario,
  cubiertas, accesibilidad, ascensores y fachada) con iconos y
  tooltips nuevos; selftest en **60 checks**.

## Novedades v3.17.0 — COTA DE IMPLANTACIÓN DE LA CUBIERTA Y VISTA 3D EN PERSPECTIVA

- **La cubierta a la altura que tú decidas** (`domain/cubiertas.py` +
  pestaña ⌂ Cubiertas del taller de diseño): el campo nuevo «Cota de
  base m» fija la altura de implantación de la cubierta sobre el
  datum del proyecto — `0` (o vacío) la apoya sobre el TOP de los
  muros del nivel cubierto, y un valor explícito la deja a esa cota
  sea más arriba (ático retranqueado, planta nueva bajo el techo) o
  más abajo (mansarda enterrada), con AVISO amable cuando queda por
  debajo del top de los muros y error propio `ARQ-CUB-002` por
  encima de 500 m. La cota viaja en la metadata de la ROOF
  (persistida, undo persistente y QTO intactos), el resumen dice
  «base a X.XX m» y el 3D la respeta en todas las tipologías —
  plana, aguas, mansarda, mariposa y dientes de sierra — y la
  «explosión» la acompaña junto a su nivel.
- **Defecto heredado corregido**: desde v3.15.0 la cubierta se
  dibujaba naciendo en el PISO del nivel superior, por lo que quedaba
  DENTRO de la edificación (cumbrera a 1.38 m con muros de 3.00 m);
  ahora nace sobre el top de los muros sin que nadie cambie nada.
- **Vista 3D en perspectiva** (`ui/view3d.py`, misma cámara): la
  casilla «Perspectiva» del diálogo (o la tecla `P` con el lienzo
  enfocado, sincronizada en ambos sentidos) conmuta entre la
  axonométrica de siempre (ojo en el infinito) y la proyección CON
  PUNTO DE FUGA: el modelo se ve como en la realidad — los volúmenes
  cercanos crecen y los lejanos encogen — con el centro y la
  distancia de la cámara calculados solos a partir del FOV de
  fábrica (50°) y del tamaño de la escena, plano cercano de
  seguridad contra divisiones locas y el MISMO encuadre automático,
  orden del pintor, sombreado, sol/terreno y exportación PNG
  determinista de siempre. `Home` re-encuadra la distancia; girar,
  inclinar, zoom, explosión, aislado y capas funcionan igual en las
  dos proyecciones.

## Novedades v3.16.0 — TECLADO Y PUNTERO AUTOCAD, EDITOR DE LOCALES Y CUBIERTAS V2

- **Teclado de trabajo estilo AutoCAD** (`ui/keymap.py`, motor sin Tk
  con pruebas propias): `F3` referencias, `F7` rejilla, `F8` orto,
  `F9` imantación, `F10` polar; `ESC` cancela la orden; `ESPACIO` o
  `ENTER` repiten la ÚLTIMA orden; alias de comando letra a letra con
  la misma regla de la línea de comandos (`M`+ESPACIO mueve,
  `M`+`I` refleja, `CO` copia, `RO` gira, `TR` recorta, `EX` alarga,
  `CHA`/`F` chaflán, `DIV` divide, `S` estira, `O` paralela,
  `E`+ESPACIO borra, `U` deshace, `P` pan); y los combos de siempre
  (`Ctrl+Z/Y`, `Ctrl+C/X/V` sobre el plano, `Ctrl+S/O/N`, `Ctrl+0`).
  La lista completa vive en Ayuda -> Atajos de teclado.
- **Puntero como AutoCAD** (`ui/cursor_acad.py`): MIRA de punta a
  punta que sigue al ratón, configurable en tamaño (100 % = cruz de
  lado a lado), grosor, color y persistida en
  `~/.arqgen/prefs.json` (diálogo Herramientas -> Puntero y
  rejilla...); referencias (osnap) a EXTREMOS (marcador cuadrado) y
  PUNTOS MEDIOS (triángulo) de los muros; `F8` endereza el paso y
  `F9` lo imanta a la rejilla adaptativa que ya se dibuja; la
  referencia ganada gana, como en AutoCAD. Las flechas desplazan la
  vista y en la Vista 3D giran/inclinan (`+`/`-` zoom, `Home`
  resetea).
- **Editor profundo de locales** (`ui/editor_espacios.py` + diálogo
  Herramientas -> Editor de local... y menú contextual del lienzo):
  diagnóstico completo del local (dimensiones, muros
  exclusivos/compartidos, puertas, ventanas, hueco de ventilación y
  avisos amables), CREAR ACCESO con el ancho que pide el uso
  (Neufert abreviado), CREAR VENTANA con el hueco que pide la
  ventilación (habitables 1/6 del suelo, húmedos 1/25, CTE DB-HS1),
  REDIMENSIONAR moviendo SOLO los muros exclusivos (los compartidos
  se quedan y se avisa) con vanos re-proyectados, mobiliario
  re-colocado, instalaciones reancladas y QTO recalculado, y
  REAMUEBLAR un local concreto. Todo auditado y deshacible con
  `Ctrl+Z`.
- **Cubiertas v2** (`domain/cubiertas.py` + render 3D): tres
  tipologías nuevas con geometría verificada a mano — MANSARDA a la
  francesa (dos pendientes por faldón con el codo al 55 % del
  semivano y superficie ponderada), MARIPOSA (las aguas caen al
  centro: el eje es el valle) y DIENTES DE SIERRA (n dientes de ~3 m
  con vidrio vertical al fondo) —, el material FIBROCEMENTO, y la
  PENDIENTE MÍNIMA por material (teja 22 %, pizarra 20 %, chapa y
  fibrocemento 8 %): si pides menos, la cubierta sube a la mínima y
  te lo avisa.

## Novedades v3.15.0 — CONCEPCIÓN DE ESPACIOS: MOBILIARIO, CUBIERTAS Y ACCESIBILIDAD

- **Un taller nuevo en la barra** (botón 🛋 Diseño de espacios, menú
  Herramientas, menú contextual del lienzo y diálogo con geometría
  recordada): tres pestañas sobre los motores puros de ``domain/`` —
  mobiliario, cubiertas y accesibilidad — y tres interruptores nuevos
  en la vista 3D (🛋 Mobiliario, ⌂ Cubierta, ♿ Accesibilidad).
- **Todo se regenera con la edificación**: `apply_plan` amuebla, cubre
  y aplica accesibilidad tras cada trazado; `purge_generated` purga
  también lo de estos motores y lo editado a mano sobrevive igual que
  un muro dibujado a mano. Entidades reales con migración 009
  (furniture, roofs, ramps, handrails), auditoría, undo persistente,
  códigos ARQ-FURNITURE/ROOF/RAMP/HANDRAIL-nnn y roundtrip JSON/undo.

### Mobiliario según el tema y el uso (`domain/mobiliario.py`)
- **Catálogo de 32 piezas** con ámbito (doméstico/social/ambos) y
  dimensiones Neufert: camas, armarios, sofás, mesas, sanitarios,
  encimera, nevera, mostrador, camillas, pupitres de aula, pizarra...
- **Reglas por TIPO DE LOCAL** (dormitorio, baño, cocina, sala, aula,
  espera, consulta, comedor, almacén, biblioteca, hospitalización...):
  qué piezas y contra qué muro, con fracciones deterministas. El área
  manda (dormitorio pequeño cambia a cama individual) y la DENSIDAD
  (compacto/estándar/amplio) añade o quita piezas cómodas.
- **El tema decide**: Vivienda amuebla en doméstico y los usos
  institucionales en social (o lo que elijas en el combo).
- **Colocación a prueba de choques**: cada pieza entra en el recinto,
  se desliza si pisa y deja PASO mínimo (0.75 m doméstico, 0.90 social)
  con aviso de pasillo estrecho frente a frente; en el plano son
  rectángulos con etiqueta al acercar y en 3D cajas coloreadas por
  categoría. QTO: FURNITURE_COUNT y FURNITURE_AREA.

### Cubiertas según estilo y tipología (`domain/cubiertas.py`)
- **El estilo arquitectónico sugiere** (colonial → teja curva a dos
  aguas, racionalista → plana de hormigón, sostenible → vegetal
  transitable, modernista → chapa a un agua...); tipología, material,
  pendiente, alero y estructura pueden fijarse a mano y siempre se
  compasan (una plana no lleva teja, un agua no lleva losa).
- **Geometría real**: envolvente convexa de los locales del nivel
  superior, alero por offset convexo de las aristas, cumbrera por el
  eje largo con altura = semivano × pendiente (acortada en cuatro
  aguas), y superficie REAL = proyección × sqrt(1 + pendiente²) que
  entra en QTO (ROOF_AREA / ROOF_PROJECTED_AREA).
- **En planta** el alero sale a trazos con la cumbrera en firme y **en
  3D** los faldones se sombrean por material con frontones en dos aguas,
  hips en cuatro aguas y parapeto de 30 cm en las planas.
- **Estimador paramétrico**: teja → renglón 126211, chapa → 124151,
  plana → 110120/124712 (como antes), con la superficie inclinada.

### Accesibilidad: barreras fuera (`domain/accesibilidad.py`)
- **Analizar barreras** con códigos ARQ-ACC-10x: puertas < 0.80 m,
  pasillos < 1.00 m (1.20 social), escaleras fuera de Blondel
  (2CH+H 0.545-0.735, CH ≤ 0.175, H ≥ 0.28) y sin barandilla,
  desniveles de piso sin rampa y aseos sin el círculo de giro de 1.50 m.
- **Aplicar soluciones** genera elementos REALES: barandillas de
  escalera a 0.90 m a ambos lados, rampas de desnivel con la pendiente
  normativa (10 % hasta 0.50 m, 8 % hasta 1.00 m, 6 % hasta 2.00 m,
  más pide ascensor) partidas en tramos de 10 m con mesetas de 1.50 m,
  pasamanos DOBLE (0.95 + 0.65 m) a ambos lados de la rampa y barras
  de apoyo de 0.70 m a 0.75 m junto a cada inodoro.
- **QTO de accesibilidad**: HANDRAIL_LENGTH, RAMP_LENGTH y RAMP_AREA;
  el estimador añade la barandilla de escalera (renglón 094211).

### QTO, presupuesto y traza
- **QTO incremental** (``services/quantity_service.py``) mide ahora
  también FURNITURE/ROOF/RAMP/HANDRAIL; las superficies de cubierta se
  DERIVEN de la geometría guardada (spec 52, origen trazable).
- **Regeneración sin huérfanos**: `collect_generated`/`purge_generated`
  reconocen las cuatro familias nuevas; el asistente guarda las
  preferencias (tema/densidad, tipología/material/pendiente/alero y
  accesibilidad) en la metadata «edificacion» y el programa se
  reconstruye con ellas.

---

## Novedades v3.14.0 — HERRAMIENTAS DE EDICIÓN TIPO CAD + ASISTENTE DE MODIFICACIONES

- **Paleta de herramientas con iconos** (botón 🛠 en la barra, menú
  Herramientas y ventana flotante que recuerda su posición): mover,
  copiar, reflejar, girar, recortar, alargar, chaflán, dividir,
  estirar, paralela y borrar. Cada herramienta guía por la barra de
  estado, dibuja marcas/elástico/fantasma sobre el plano y se cancela
  con Esc; la distancia del chaflán se fija en la paleta.
- **El motor (`ui/cad_tools.py`, sin Tk)** opera sobre la edificación
  real con los servicios oficiales: auditoría UPDATE_ENTITY por
  entidad (Ctrl+Z paso a paso), eventos de geometría, invalidación y
  recálculo incremental de QTO tras cada operación. Mover un LOCAL
  lleva consigo sus muros EXCLUSIVOS (los compartidos con otros
  locales se quedan, como en AutoCAD), los vanos viajan rígidos con
  su muro y las terminales de instalaciones se REANCLAN (baja con
  cascada + reconexión del local).
- **Vanos inteligentes**: al recortar, dividir o estirar, el centro de
  cada vano se conserva en el mundo y se re-proyecta sobre el nuevo
  eje; los que ya no caben se dan de baja con aviso y las puertas
  cambian de mano al reflejar. El chaflán recorta ambos muros y crea
  el muro de unión heredando espesor/altura/material.
- **Lo editado a mano SOBREVIVE a la regeneración**: toda entidad
  generada por el asistente que toque una herramienta se re-marca
  (metadata «editada_a_mano» + origen «edición manual») y
  `collect_generated` la respeta igual que lo dibujado a mano.
- **Asistente de modificaciones** (menú Herramientas): edición guiada
  por pasos — elemento (lista de muros o locales), operación y
  parámetros numéricos (coma o punto decimal) con VISTA PREVIA
  antes/después en un canvas — para cuando el clic fino sobre el
  plano no es cómodo. Mismas operaciones, mismo motor, mismos avisos.

## Novedades v3.13.1 — CONSOLA A PRUEBA DE WINDOWS

- **El selftest del ejecutable ya no muere al imprimir el check 55**: el
  mensaje llevaba la flecha «→» (U+2192) en «exportar→importar» y la
  consola de Windows (cp1252) no sabe codificarla — el pipeline
  imprimía 54 líneas OK y reventaba con ``UnicodeEncodeError`` justo
  en la última. La flecha pasa a «->» y el texto de TODOS los checks
  es codificable en cp1252 (verificado con una prueba que simula la
  consola exacta).
- **Blindaje de doble capa** (``core/consola.py``): ``consola_segura()``
  reconfigura stdout/stderr con ``errors="replace"`` en la entrada de
  la CLI y en el bloque de consola del selftest — los acentos siguen
  intactos y cualquier carácter futuro que la página de códigos no
  entienda sale como «?» en lugar de tumbar el proceso.
- **Ocho ``print()`` de la CLI y el mensaje de conversión prohibida de
  unidades** también llevaban «→»: las rutas de redes, trazo,
  pluviales, estructura y precios ya no son una trampa latente en
  Windows; la ayuda de ``bim tree`` pasa a «->».

## Novedades v3.13.0 — SOMBRAS SOLARES, TERRENO 3D E IFC DE ENTRADA/SALIDA

### Sol, sombras y orientación (`ui/solar.py`)
- **Posición solar verificable a mano**: declinación de Cooper + ángulo horario
  (hora solar, no de leyenda) dan azimut (0°=N, 90°=E, 180°=S, 270°=O) y
  elevación sin ambigüedad de cuadrante. El mediodía del equinoccio en Madrid
  cae a 49° desde el SUR, en La Habana en junio el sol pasa por el CENIT por el
  lado norte y a los 80°N en diciembre hay noche polar — todo testeado.
- **Sombras de verdad, no manchas**: cada muro proyecta sus 8 esquinas por
  rayos paralelos, la envolvente convexa se recorta con Sutherland-Hodgman
  contra las 4 franjas FUERA de la huella (la parte que cae debajo la tapan los
  muros y provocaría parpadeos coplanares) y la sombra se ARRUGA siguiendo la
  malla del terreno cuando la hay. Su longitud es exactamente h/tan(elevación).
- **Brújula y trayectoria solar**: aguja NORTE roja al sur de la huella, un
  disco por cada hora soleada de 5 a 19 h y el disco naranja grande marca la
  hora elegida; de noche queda la brújula y cero sombras. La línea de estado y
  el pie del PNG dicen «sol az 180° el 43° (21 dic · 12 h)» y la ficha de
  orientación recomienda fachada principal según la latitud (SUR en el
  hemisferio norte, NORTE en el austral, sombra y ventilación en la tórrida).
- **En el diálogo 3D**: casilla ☀ Sombras solares + combos de Latitud (8
  ciudades de Madrid a Santiago), Fecha (equinoccios y solsticios) y Hora
  solar (06 a 18, mediodía por defecto). Todo recalcula al instante y sale en
  el PNG determinista.

### Terreno 3D (`ui/terreno3d.py`)
- **El solar donde se posa el edificio**: malla determinista (ruido de valores
  con semilla — el mismo terreno siempre, en cualquier máquina) con pendiente
  uniforme de 0 a 25 % en la dirección que se pida, ondulaciones de amplitud
  configurable y PLATAFORMA NIVELADA a −1 cm bajo la huella con transición
  suave de 2,5 m: el edificio nunca queda colgando ni la losa pelea con la
  malla (los quads íntegramente bajo la huella se omiten).
- **Rampa de color por altura** (verde de pradera → tierra → tierra clara) y
  matemática exacta: 10 % sobre 24 m son 2,40 m de desnivel, testeado a
  1e-9. En el diálogo 3D: casilla ⛰ Terreno + combos de Pendiente, rumbo
  hacia el que baja (N/E/S/O) y Relieve (Liso/Suave/Accidentado).
- **Los pisos a su cota**: los locales con «cota_piso_m» del asistente de
  terreno irregular (v2.3.0) ahora se dibujan levantados en la vista 3D.

### IFC de entrada (`importers/ifc_reader.py`) y salida corregida
- **El IFC ya entra**: parser SPF propio (Python puro, tolera cadenas con
  «;», comillas escapadas y refs envueltas en listas), unidades METRE/
  MILLIMETRE/CENTIMETRE/FOOT, colocaciones IfcLocalPlacement anidadas con
  guarda contra ciclos y extrusiones IfcExtrudedAreaSolid con perfil
  rectangular o poligonal. Reconstruye niveles (reutilizando los homónimos al
  reimportar), muros (también IfcWallStandardCase) desde los dos lados largos
  de su huella — espesor por distancia PERPENDICULAR entre rectas, no por
  puntos medios —, locales, y puertas/ventanas ancladas a su muro por la
  relación oficial (RelFills→RelVoids) o por cercanía perpendicular de
  respaldo, con ancho/offset/antepecho derivados del sólido.
- **Roundtrip demostrado**: exportar el demo → importar a proyecto nuevo
  reproduce muros a longitud/espesor/cota fieles, vanos con su ancho, offset y
  antepecho, y locales con su área. Lo que no es extrusión vertical se omite
  contado en avisos — nunca rompe.
- **Tres bugs de SALIDA corregidos (desde v1.x)**: los vanos se emitían en el
  origen del mundo y sin la cota del nivel (los visores externos no cortaban
  el hueco), IfcRelFillsElement llevaba los argumentos INVERTIDOS (apertura y
  relleno) y las representaciones iban como ref simple donde el esquema pide
  lista. Ahora los vanos salen en su sitio real sobre el anfitrión, a la cota
  de su piso y contenidos además en el IfcBuildingStorey como pide la práctica
  estándar.

---

## Novedades v3.12.0 — PRESUPUESTO VIVO SOBRE LAS VARIANTES

### Estimador paramétrico con precios oficiales (`ui/variant_budget.py`)
- **Del trazado al coste sin pasar por la base de datos**: cada `LevelLayout` rinde su
  takeoff — muros por tipología constructiva (bloque 0,10/0,15/0,20 m según el espesor,
  tabiques de madera, panel sándwich o muros de hormigón monolítico), **vanos descontados
  del muro**, losa según la tipología (vigueta y bovedilla, losa maciza o entablado de
  madera), malla electrosoldada, escaleras de hormigón, repello a dos caras, enlucido de
  techos, pisos, puertas y ventanas Miami por área, aparatos sanitarios según el tipo de
  local (baño → inodoro/lavamanos/ducha; cocina → fregadero) y puntos eléctricos por
  local. Preparación y cimentación solo en el nivel 0; cubierta y alero en el último.
- **Clasificación geométrica exterior/interior**: cada muro fusionado se muestrea a lo
  largo de su eje (paso 1 m, puntos medios, contención estricta) y un tramo es exterior
  cuando a un lado no hay local — el pasillo, el patio, la escalera y el núcleo cuentan
  como lado cubierto. Sin reglas por esquema: funciona igual en lineal, doble crujía,
  patio, L, T, U, H, cruz y articuladas, y no se deja engañar por las esquinas.
- **Precios SIEMPRE del catálogo**: los 30 renglones del estimador son renglones
  oficiales del PRECONS III (RoPres 3.30) con precio de lista CUP; el nombre, la unidad
  y el precio se resuelven del ruleset (fuente única de verdad). Un renglón ausente en
  otra versión del catálogo anota un aviso y la estimación sigue.
- **Nada se persiste**: la estimación es derivada y efímera — vive en
  `PlantVariant.cost` (`VariantCost` con filas, categorías, avisos, coste/m² y
  `to_dict()` determinista) y el presupuesto del proyecto no se toca.

### Calidad de acabados y GUI viva (`ui/app_window.py`)
- **Calidad de acabados Económica / Estándar / Premium**: factor documentado (0,85 /
  1,00 / 1,30) sobre las categorías de acabado (revestimientos, pisos, carpintería,
  sanitaria y eléctrica); la obra gruesa (preparación, cimentación, estructura, muros)
  queda intacta. Cambiar el combo RECALCULA al vivo sin regenerar el trazado.
- **Regeneración (♻)**: columna nueva «Coste (CUP)» junto a la puntuación, línea de
  métricas con «Estimación: X CUP (Y CUP/m²)» + desglose top-3 por capítulos, botón
  «⤓ PNG de costes» que exporta la comparativa de todas las variantes (la más económica
  se nombra en el pie) y el mensaje tras sustituir anuncia la estimación con la calidad
  elegida. Si el catálogo no pudiera cargarse, los costes quedan en «—» sin romper nada.
- **Asistente de edificación (paso 6)**: la misma columna de coste y el mismo combo de
  calidad, con la estimación y su desglose en la descripción de la variante recomendada.
- **NUEVO tests/test_131_presupuesto_vivo.py (31)**: clasificación geométrica
  (rectángulo exacto, forma en L, patio como interior), takeoff con valores verificados
  a mano, tipologías constructivas, pórtico, alero, precios resueltos del ruleset,
  renglones agregados sin duplicados, calidad monotona con obra gruesa intacta,
  determinismo estricto, avisos por renglón ausente, PNG determinista y GUI completa
  (regeneración + asistente con calidad en vivo y PNG de costes).
- selftest: NUEVO check 54 con prueba conductual real (programa chico → variantes →
  costes oficiales → calidad → PNG) — **54 checks**.

---

## Novedades v3.11.0 — VISTA 3D AXONOMÉTRICA: EL EDIFICIO SE GIRA

### Motor de proyección puro (`ui/view3d.py`)
- **Cámara axonométrica ortográfica** (`Camara3D`): azimut envolvente módulo 360,
  elevación sujeta entre 8° y 80° y zoom entre 0,2× y 8×. La proyección (rotación en
  planta + inclinación) es la isométrica de libro verificada a mano: z sube en pantalla,
  x baja a la derecha y y baja a la izquierda. **Cero dependencias nuevas**: solo `math`
  y el exportador PNG stdlib que ya usaba la app.
- **Extrusión con criterio**: cada muro se levanta como caja desde su nivel (con su
  `height_m` propio y su `base_offset_m` de desnivel), con **eliminación de caras
  traseras** (back-face culling según el vector de cámara) y **sombreado por orientación
  ante la luz** — que viene de donde mira la cámara; la tapa siempre sale más clara. Los
  arcos del diseño orgánico ya vienen teselados desde el trazado: se extruyen como
  fajas de caras sin tocar nada.
- **Todo el proyecto al 3D**: pisos de locales a su cota +2 cm pintados por tipo
  (pasillo/patio/cocina/baño con paleta fija compartida con el asistente), vanos con su
  `sill_height_m` y altura real sobre la cara VISIBLE del muro que los aloja (puerta
  cálida, ventana azul), plataforma-losa de apoyo por nivel (la que se ve de canto en la
  «explosión») y niveles apilados por `elevation_m`.
- **Orden del pintor + explosión + aislado**: caras ordenadas de lejos a cerca
  (desempate por orden de emisión, para que los vanos salgan sobre su muro); la
  «explosión» separa cada nivel verticalmente (índice × metros) y el combo «Nivel:»
  aísla uno solo.
- **PNG determinista 100% stdlib** (`export_vista3d_png`): misma lista de caras, mismo
  encuadre y mismos colores que el lienzo Tk; contenedor válido, reproducible byte a
  byte y con tira de título des-accentuada como el resto de los rasterizadores.
- **De regalo: el texto de los PNG ya no sale en espejo** — `Canvas.text` leía la matriz
  5x7 LSB-primero y CADA glifo quedaba reflejado (defecto preexistente desde v2.0.0 en
  los títulos de los gráficos de presupuesto, las vistas del asistente y los detalles);
  ahora se lee MSB-primero (la L con el palo a la izquierda, la P con la panza bien) y
  **tests/test_119** lo fija a nivel de píxel.

### Diálogo «Vista 3D» en la GUI (`ui/app_window.py`)
- **Tres puertas de entrada**: menú Ver → «Vista 3D del edificio…», botón «Vista 3D»
  en la barra de herramientas (con tooltip nuevo obligatorio `vista3d`) y menú
  contextual del lienzo (🧊), junto a los asistentes y la regeneración.
- **Diálogo redimensionable** con geometría recordada (prefs «vista_3d»): lienzo sobre
  el fondo del tema con línea de estado (azimut, elevación, niveles, caras), botones de
  girar/elevación/zoom/encuadrar, combos «Nivel:» (aislar), «Colores:» (por tipo o
  monocromo) y «Explosión:» (0–3 m), «↻ Recargar» re-lee el proyecto y «💾 PNG…»
  exporta con la MISMA cámara que se está viendo.
- **Gestos**: arrastrar con el botón izquierdo gira (horizontal = azimut, vertical =
  elevación) y la rueda acerca/aleja (MouseWheel de Windows y Button-4/5 de Linux).
  Sin geometría → mensaje amable señalando el asistente (🏠) o la regeneración (♻).
- **NUEVO tests/test_130_vista3d.py (18)**: proyección isométrica verificada a mano,
  sujeción y envoltura de la cámara, modelo desde proyecto vacío/completo/apilado,
  culling con conteo exacto de caras, vanos a su cota con colores, explosión, aislado,
  orden del pintor, modos de color, PNG determinista/acotado/vacío/acentos y diálogo
  GUI completo hasta el PNG exportado.
- selftest: NUEVO check 53 con prueba conductual real (modelo del proyecto vivo →
  caras → PNG válido) — **53 checks**.

---

## Novedades v3.10.0 — EDIFICACIÓN REGENERATIVA: NADA DE CAMBIOS HUÉRFANOS

### El programa de locales vuelve a ser la fuente de verdad (`ui/building_wizard.py`)
- **Lo pedido**: «si hay algún local que quisiera mover hacia otro lugar… que recalcule y
  redistribuya los otros locales así como las instalaciones y módulos… generar otras
  variantes pero permitirme elegir cuál es la elegida para sustituir la anteriormente
  generada… agregar un local nuevo, o cambiarle las dimensiones, o eliminarlo, o agregar
  un nuevo local en un segundo nivel».
- **Motor nuevo (headless, testeado)**: `program_from_project()` RECONSTRUYE el programa
  editable desde el proyecto abierto (parámetros del metadata «edificacion» del edificio,
  locales desde los espacios generados — sin pasillos/patios/escaleras/núcleo, que el
  trazado recrea —, dimensiones desde los boundaries y relaciones entre locales);
  `move_room` (reordena dentro del nivel: la posición decide dónde lo coloca el trazado),
  `move_room_to_level` (crea el nivel si falta), `resize_room`, `remove_room` (limpia sus
  relaciones) y `add_room` (rechaza homónimos). Los metadata nuevos guardan vanos, región
  Neufert, distribución, semilla y curvatura para reconstruir el programa con fidelidad.
- **Sustitución sin huérfanos**: `collect_generated()` identifica TODO lo generado por el
  asistente (marca de origen en metadata; los especiales de edificios anteriores también),
  `purge_generated()` lo elimina en orden seguro (terminales de instalaciones → relaciones
  → vanos → muros → locales, cada baja por el CommandBus con auditoría, QTO y grafo) y
  `replace_plan()` re-traza el edificio COMPLETO con la variante elegida, reutiliza
  niveles/edificio y recalcula las instalaciones sobre la geometría nueva. Lo dibujado a
  mano NO se toca. La marca de origen llega ahora también a escaleras y núcleos.

### Editor regenerativo en la GUI (`ui/app_window.py`)
- **Menú Herramientas → «Regenerar edificación»** y opción en el menú contextual del
  lienzo (♻). Diálogo redimensionable con geometría recordada (prefs «regen»):
  - **Programa de locales** en árbol (nivel, local, tipo, ancho, fondo) con botones
    ↑ Subir / ↓ Bajar / A otro nivel… / Redimensionar… / Eliminar / ＋ Añadir local….
  - **Variantes de planta regeneradas**: el motor genera las 28 variantes puntuadas
    (6 métricas explicadas, penalización si no caben en el lote), tabla con #/esquema/
    título/puntos/cabe, PREVIEW dibujado del nivel 1 (muros y locales con colores por
    tipo) y línea de métricas de la variante elegida.
  - **«♻ Sustituir la edificación generada»** con confirmación clara: purga + trazado
    nuevo + `refresh_all(fit=True)`; si algo falla, rollback y el proyecto queda como
    estaba. Undo persistente funciona mutación a mutación sobre la auditoría.
- **NUEVO tests/test_129_regeneracion_edificio.py (16)**: programa editable puro,
  reconstrucción desde proyecto, sustitución sin huérfanos (nodos y relaciones colgantes
  = CERO), conservación de lo dibujado a mano, determinismo de variantes del programa
  editado, undo persistente, local nuevo en segundo nivel y diálogo GUI completo hasta
  sustituir.
- selftest: NUEVO check 52 con prueba conductual real (generar → reconstruir → editar →
  sustituir) — **52 checks**.

---

## Novedades v3.9.1 — EL PANEL DE AVISOS YA NO SE COME LA VENTANA

### Diagnóstico del espacio sobredimensionado (`ui/app_window.py`, `ui/prefs.py`)
- **El síntoma exacto**: «el espacio donde salen los recordatorios de los gestos del
  lienzo casi ocupa la mitad de la ventana y se la resta al modelador» — ese espacio es
  el panel inferior (Avisos / Registro / Estado de cálculos), donde aparecen consejos
  como «Arrastra los separadores a tu gusto».
- **Causa raíz**: las preferencias heredadas de la v3.8.0 guardaban el separador inferior
  con una colocación FIJA a 400 px desde arriba, pensada para ventanas altas; restaurada
  tal cual en una ventana de 700-800 px de alto, el panel se quedaba con el 40-50% de la
  ventana. La v3.9.0 lo respetaba por ser «lo guardado» — correcto en general, cruel aquí.
- **Arreglo — migración one-shot**: al arrancar, la primera sesión que aplica separadores
  descarta la posición inferior heredada, impone el default compacto y marca
  `bottom_compact` en las preferencias (formato v2). Desde ese momento manda lo que el
  usuario coloque con el separador. El guardado heredado se BORRA para que los
  re-apliques del arranque ni «Restaurar disposición» lo revivan. Un archivo v1 no puede
  colar la marca: solo las preferencias escritas por v3.9.1+ la conservan.

### El panel de avisos pide todavía menos (`ui/app_window.py`)
- Separador inferior de fábrica `SASH_DEFAULT_BOTTOM_MARGIN` 160 → **120 px**; el
  Notebook pide **100 px** (antes 150), los textos de Avisos y Registro 3 líneas y el
  Treeview de «Estado de cálculos» 4 filas.
- La línea de gestos del lienzo se acorta («Clic derecho: menú o mover») para pedir menos
  ancho y dejar respirar a los paneles laterales.
- **NUEVO tests/test_128_migracion_panel_inferior.py (9)**: prefs v2 conservan la marca,
  un archivo v1 no la cuela, la sesión heredada migra al compacto (120 px sobre el
  mínimo), la segunda sesión respeta EXACTO lo que el usuario dejó, de fábrica nace
  compacto, y «Restaurar disposición» guarda la posición viva compacta.
- selftest: check 51 ampliado con las constantes 240/300/120, el formato v2 de
  preferencias y la migración (51 checks).

---

## Novedades v3.9.0 — INTERFAZ COMPACTA, PLANO PRIMERO

### El logo ya no devora la ventana (`ui/icons.py`, `ui/app_window.py`)
- **Causa del desperdicio**: la barra de herramientas reutilizaba el PNG de branding
  (`logo.png`, 256×256 px — el mismo del icono del EXE) como imagen de la marca: la barra
  medía ~260 px de ALTO, más espacio que el panel de avisos entero.
- **Arreglo**: nuevo ayudante `icons.toolbar_logo()` que genera el logotipo EN MEMORIA a
  22 px con supermuestreo anti-aliasing (determinista, sin dependencias). El PNG grande
  queda SOLO para la barra de título del sistema y el icono del ejecutable. El texto
  «ARQ GEN» sale de la barra (ya vive en el título y en la barra de tareas).
- **De regalo, un bug latente resuelto**: `window_icon()` y `toolbar_logo()` registran ahora
  el PhotoImage en el intérprete de SU ventana (`master` explícito) — antes, una segunda
  ventana Tk del mismo proceso perdía la marca en silencio («image does not exist»).

### Barra de herramientas en DOS filas: el filtro de nivel SIEMPRE visible (`ui/app_window.py`)
- **Causa de los botones invisibles**: toda la barra (asistentes + zooms + buscador +
  filtro «Nivel:») cabía —mal— en una sola fila de ~1500 px: con la escala de Windows el
  extremo derecho se cortaba y el selector de niveles quedaba fuera de la ventana.
- **Arreglo**: la fila A concentra las ACCIONES (asistentes, objeto, editar, guardar y el
  conmutador de tema a la derecha); la fila B, la NAVEGACIÓN y FILTROS del lienzo
  (Encuadrar, Zoom ±, buscador compacto y el filtro «Nivel:» a 12 caracteres). En dos filas
  compactas nada se corta aunque la ventana sea estrecha o la escala alta.

### Menos espacio regalado, más plano (`ui/theme.py`, `ui/app_window.py`)
- **Separadores de fábrica al servicio del plano** (`SASH_DEFAULT_EXPLORER/PROPS_MARGIN/
  BOTTOM_MARGIN` = 240/300/160, importables y verificados): el lienzo central gana ~70 px
  de ancho; el panel de propiedades afina sus columnas para caber sin recortes.
- **Panel de avisos más bajo**: el Notebook pide 150 px (antes 170) y sus textos 5 líneas;
  el separador grueso de 10 px (v3.7.0) sigue permitiendo ampliarlo o colapsarlo con doble
  clic.
- **Tema compacto en ambos modos**: botones (8,4), acento (10,4), pestañas y filas de árbol
  más bajas — sin tocar el sash grueso de 10 px.
- **NUEVO tests/test_127_ui_compacta.py (12)**: logo pequeño real en la barra y grande solo
  en el título, dos filas verificadas por jerarquía de widgets, el filtro «Nivel:» DENTRO de
  los límites de una ventana de 1024×720 (peor caso de portátil), defaults 240/300/160
  aplicados y persistentes tras «Restaurar disposición», panel de avisos a 150 px y estilos
  compactos en oscuro y claro.

---

## Novedades v3.8.1 — SELFTEST PORTABLE AL EJECUTABLE

### La etapa 3 del post-build ya no se cae (`app/selftest.py`)
- **Síntoma**: `03_COMPILAR.bat` compilaba el ejecutable y el selftest del bundle
  moría con `FileNotFoundError: …dist\ARQ_GEN\_internal\ui\app_window.py`.
- **Causa**: los checks 49 (v3.7.0) y 50 (v3.8.0) verificaban TEXTO del fuente
  abriendo `ui/app_window.py` — pero PyInstaller embarca los módulos como
  bytecode y el `.py` no viaja junto al binario.
- **Arreglo**: esa verificación de texto se ejecuta SOLO en desarrollo
  (`sys.frozen` falso); al vuelo congelado se omite con el mismo criterio
  honesto de los scripts .bat (check 27) y la línea OK lo declara:
  «verificación de fuente omitida: ejecutable». Todas las demás aserciones de
  ambos checks (constantes de tema, prefs, validador de geometrías, tabla de
  ventanas, ediciones regionales, PDF de documentos…) SÍ corren en el exe.
- **NUEVO tests/test_126_selftest_congelado.py (5)**: simula el bundle
  (`sys.frozen` + `sys._MEIPASS` hacia la raíz) y exige el selftest COMPLETO
  en CORRECTO sin ningún FALLO, las dos líneas declarando la omisión, el mismo
  número de checks que en desarrollo, y — desde fuente — que los marcadores
  verificados siguen existiendo en `ui/app_window.py`.

---

## Novedades v3.8.0 — LAYOUT RESTAURABLE + 3 EDICIONES REGIONALES + PDF DE DOCUMENTOS

### La disposición se devuelve a fábrica con un clic (`ui/app_window.py`)
- **«Ver ▸ Restaurar disposición por defecto» (Ctrl+0)**: muestra otra vez los tres paneles
  (explorador, propiedades, avisos), borra las posiciones guardadas de los separadores y aplica
  las de defecto amables (280 px / borde derecho / avisos abajo). Las preferencias quedan
  coherentes: lo que ves tras el reset es lo que habrá en la próxima sesión.
- **Doble clic sobre un separador colapsa su panel**: el gesto estándar para darle TODO el
  espacio al plano. El sash no es un widget, así que se escucha el doble clic del `PanedWindow`
  y `identify(x,y)` decide si cayó sobre un separador — compatible con **Tk 9** (devuelve el
  índice directamente) y **Tk 8.6** (tupla `("sash", índice)`); el mapa sash→panel se deduce de
  los paneles visibles, así sigue siendo correcto aunque ya haya un panel oculto. El menú Ver
  (o Ctrl+1/2/3) devuelve cada panel.
- La guía rápida (paso 1) enseña los dos gestos nuevos: «Un doble clic sobre un separador
  colapsa su panel, y «Ver ▸ Restaurar disposición por defecto» (Ctrl+0) lo devuelve todo al
  estado de fábrica».

### Tres ediciones regionales nuevas (`resources/knowledge/detalles/`)
- **España (CTE)** — 6 detalles: fábrica de ladrillo doble hoja con cámara aislada (260 mm,
  reemplaza a la base), forjado unidireccional de bovedilla (315 mm), cubierta plana transitable
  INVERTIDA con XPS sobre la lámina (439 mm), teja curva ventilada con lámina bajo teja,
  ventana de PVC con rotura de puente térmico 4/16/4 low-e y **SATE** con EPS grafitado;
  normas DB-SE-A, DB-HS 1 y DB-HE en cada ficha.
- **Perú (RNE)** — 5 detalles: albañilería confinada E.070 con ladrillo KK (reemplaza al muro
  de bloque), losa aligerada de 20 cm con tejar (E.060), azotea tarrajeada con brea en dos manos
  (la clásica de la costa), viga de cimentación + sobrecimiento impermeabilizado y teja andina
  sobre correas de eucalipto para la sierra.
- **Chile (DS 61 / NCh)** — 5 detalles: **muro de corte de hormigón armado** (NCh433/DS 61,
  el sistema de los sismos de magnitud 8), albañilería confinada NCh21247, entrepiso de madera
  con vigas de pino radiata NCh1198, cubierta de chapa de zinc sobre volcometas y cadena de
  desplante de hormigón simple con revoque hidrófugo.
- La biblioteca llega a **7 ediciones regionales** (más México, Colombia, Argentina y Cuba);
  reemplazos y añadidos 1:1 sobre la base de 20 detalles, que **nunca se corrompe** (vigilado
  por pruebas: el retrato de espesores de la base es idéntico antes y después de recorrer las
  regiones).

### Los documentos llevan los detalles recomendados — y salen en PDF
- **Memoria y pliego con detalles**: `generate_memoria()` y `generate_especificaciones()`
  añaden la sección **«Detalles constructivos recomendados»** cuando el proyecto tiene la
  tipología constructiva del asistente (metadata `edificacion.tipologia_constructiva` del
  BUILDING): tabla determinista de los 9 recomendados (id, nombre, categoría y espesor total),
  texto con la edición regional activa y el aviso normativo de la biblioteca. Sin edificio (o
  sin tipología) la sección no aparece y los documentos quedan byte a byte como antes.
- **PDF de documentos (`exporters/markdown_pdf.py`)**: cualquier documento del motor de
  documentación sale en **PDF A4 vectorial determinista** — encabezados, listas, tablas con
  anchos proporcionales y recorte de celdas, negritas y acentos graves limpiados, transliteración
  honesta de símbolos (→, ≥, ×) — reutilizando `PdfReport` (cabecera con título y fecha, saltos
  automáticos y cabeceras de tabla repetidas). `DocumentationService.export_document(..., "pdf")`
  acepta el formato y el error de formato desconocido se mantiene.
- **Tres canales**: CLI `docs memoria <proyecto> --out memoria.pdf` (también specs/informe/…,
  la extensión manda), servicio (`export_document`) y GUI **«Herramientas ▸ Informe
  descriptivo (PDF)…»**.

### Calidad
- **NUEVO tests/test_125_layout_regiones_docs_pdf.py (30)**: acelerador Ctrl+0 y mapa
  sash→panel real (con panel oculto), doble clic que oculta los TRES paneles sobre la ventana
  viva y reset a fábrica con prefs coherentes (sin tocar dialogs ni tema); las tres ediciones
  nuevas (añadidos, reemplazos, espesores, base intacta, búsqueda por norma SATE/E.070/NCh433,
  recomendados adaptados 1:1) y CLI `detalles regiones|list|ver` punta a punta; memoria/pliego
  con sección adaptada a la edición activa, determinismo, PDF válido y descomprimido para
  verificar el contenido, vacío → ARQ-EXP-072, tablas anchas sin romper y exportación del
  informe PDF desde la GUI.
- selftest **50 checks** · suite completa **1127 pruebas** en verde (1 skip de GUI sin display).

---

## Novedades v3.7.0 — VENTANAS Y PANELES AJUSTABLES

### La planta manda: separadores arrastrables y recordados (ventana principal)
- **Sash grueso y visible**: los `ttk.PanedWindow` usan ahora un separador de **10 px** del color
  del borde (`theme.SASH_THICKNESS`) — antes el sash nativo de clam (3 px) era casi imposible de
  agarrar. Arrastrando los bordes del explorador, del panel de propiedades y del panel inferior
  (o el que separa el plano del panel de avisos) el plano gana exactamente el espacio que quieras.
- **Posiciones por defecto amables**: explorador 280 px, propiedades 330 px y panel inferior
  220 px — el centro (la planta) queda con la mayor parte desde el primer arranque.
- **La app recuerda cómo los dejas**: las posiciones de ambos separadores se guardan en
  `prefs["sashes"]` al cerrar y se restauran al arrancar (con difierimiento hasta que la ventana
  esté mapeada + doble aplicación 80/260 ms para que ningún `Configure` tardío las pise).
- **Tolerante por diseño**: si un panel está oculto (Ctrl+1/2/3) cambian las cuentas y la
  restauración de ese `PanedWindow` se descarta sin romper nada; la ventana principal tiene
  `minsize 960×600` para que el plano nunca colapse.
- **`launch()` respeta la geometría guardada**: el tamaño por CLI solo se usa la primera vez;
  antes el `window.geometry(...)` final pisaba siempre la geometría de preferencias.

### Todas las ventanas con borde ajustable (`_prepare_dialog`)
- Un preparador común aplica a cada ventana secundaria: **geometría recordada**
  (`prefs["dialogs"][clave]`, validada con `geometry_size()`), **tamaño mínimo** y
  **redimensionable True/True**; la geometría elegida se guarda al cerrar la ventana (también al
  salir de la app) y se re-aplica al reabrirla.
- **Con memoria de geometría**: catálogo PRECONS (1000×660), detalles constructivos (1020×680),
  presupuesto PRECONS (1060×640), importar catálogo §94 (760×540), importar DXF/DWG (760×560),
  asistente de edificación (1120×760), asistente de local (640×640) y guía rápida (640×620).
- **Formularios redimensionables sin memoria**: estado de la entidad, editar propiedad, nuevo
  objeto y tipo de objeto ganan minsize + borde arrastrable sin ensuciar preferencias.
- La guía rápida (paso 1) explica la función: «Arrastra los separadores entre paneles (y los
  bordes de cualquier ventana) para darle el espacio que quieras: la app recuerda cómo los dejas».

### Corrección estructural de preferencias (`ui/prefs.py`)
- **REGRESIÓN eliminada**: `load_prefs` devolvía `dict(DEFAULTS)` — copia superficial que
  COMPARTÍA los diccionarios anidados (`panels`, y ahora `sashes`/`dialogs`) entre todas las
  ventanas del proceso; una ventana mutaba los defaults de las demás. Ahora `copy.deepcopy`.
- Nuevos diccionarios validados en `_merge_defaults` (claves de texto, basura descartada) y
  selftest **49 checks** con batería completa en `tests/test_124_ventanas_ajustables.py` (26
  pruebas: defaults tolerantes, validador de geometrías, sashes por defecto, arrastre →
  persistencia → restauración en una ventana nueva, convivencia con toggle_panel, y las 12
  ventanas reales verificando minsize/resizable/geometría recordada).

---

## Novedades v3.6.0 — DETALLE EN PDF/PNG + VÍNCULO CON LA TIPOLOGÍA CONSTRUCTIVA

### Exportación del detalle en los tres canales (`exporters/detalle_export.py`)
- **PDF vectorial A4 vertical** (`export_detalle_pdf`): mismo contenido que el SVG — bandas de
  capas apiladas por espesor, **números de capa en círculos Bézier** (primitiva `circle` nueva en
  `PdfDoc`), líneas de referencia, **cota rotada** del espesor total (texto con matriz de giro en
  `PdfDoc.text`), leyenda tabulada de materiales, notas de obra y cajetín con la edición regional.
  Los cuatro caracteres que Helvetica-WinAnsi no tiene (λ ≈ ≤ ≥) se transliteran al vuelo.
- **PNG raster 2x** (`export_detalle_png`): composición idéntica sobre `Canvas` con la fuente
  bitmap 5x7 del sistema; listo para informes y mensajería.
- **Despachador `export_detalle`** por extensión (.pdf/.png/.svg, mayúsculas incluidas; extensión
  desconocida → SVG). 100% stdlib y **determinista byte a byte** en los tres canales.

### La biblioteca cubre ahora TODAS las tipologías (base v1.1, 20 detalles)
- **NUEVO `muros/muro_piedra_mamposteria`** (430 mm): mampostería de piedra careada con
  «llorones», enlucido de cal — para la tipología **Muros de piedra**.
- **NUEVO `muros/muro_adobe_tapial`** (470 mm): adobe o tapial estabilizado con enlucido de
  barro, zócalo y aleros obligatorios — para la tipología **Tierra (adobe o tapial)**.

### El vínculo detalle ↔ tipología (`domain/detalles.py`)
- **`TIPOLOGIA_DETALLES`**: las 10 tipologías constructivas del asistente
  (`ui.building_wizard.CONSTRUCTION_TYPES`) mapean a sus detalles recomendados en orden
  narrativo (cimentación → muro → entrepiso → cubierta → …). La **paridad con el asistente
  queda vigilada** por pruebas y selftest (como el spec contra el .bat).
- **`detalles_para_tipologia()`** devuelve los recomendados **adaptados a la edición activa**:
  México entrega la azotea con prefabricado, Cuba retira el hormigón celular de la
  recomendación; lo no disponible desaparece sin romper nada.
- **`buscar_tipologia()`** resuelve el texto del usuario sin acentos (exacta → única
  substring; «losa» es ambigua y lo dice con candidatos).

### En la GUI y la CLI
- **Navegador de detalles**: combo **Tipología** nuevo (tooltips `det_tipo`/`det_png`/`det_pdf`)
  que acota la lista a los recomendados y combina con edición, categoría y búsqueda; los tres
  botones **⤓ SVG / ⤓ PNG / ⤓ PDF** exportan el detalle elegido.
- **Asistente de edificación**: botón **«Detalles constructivos…»** junto a las vistas (tooltip
  `bld_detalles`, gancho `_bld_open_detalles`) que abre la biblioteca **pre-filtrada a la
  tipología elegida en el paso 1** — el corte de tu muro, tu losa y tu cubierta a un clic.
- **CLI sin proyecto**: `detalles pdf <id> archivo.pdf` · `detalles png <id> archivo.png`
  (con `--region`) y `detalles tipologia "mampostería de bloque" [--region --categoria]`,
  que lista los recomendados y avisa los retirados por la edición.

### Calidad
- **NUEVO tests/test_123_detalle_pdf_png_tipologia.py (39)**: base ampliada (piedra/tierra),
  paridad del mapa con CONSTRUCTION_TYPES, recomendaciones en orden narrativo y filtradas por
  categoría, adaptación por edición (reemplazo y retiro), buscador tolerante, PDF/PNG
  deterministas con estructura verificada (círculos Bézier, cota rotada, chunks PNG),
  transliteración WinAnsi, despachador por extensión, CLI punta a punta y flujos GUI reales
  (filtro en vivo, pre-selección desde el asistente, exportación PNG/PDF).
- selftest **48 checks** · suite completa **1071 pruebas** en verde (1 skip de GUI sin display).

## Novedades v3.5.0 — BIBLIOTECA DE DETALLES CONSTRUCTIVOS POR EDICIONES REGIONALES

### La biblioteca (`domain/detalles.py` + `resources/knowledge/detalles/`)
- **Base universal de 18 detalles en 8 categorías** — cimentaciones, muros, entrepisos,
  cubiertas, escaleras, humedades, carpintería y acabados: zapata corrida de HA, muro de
  bloque enlucido, losa maciza y de vigueta-bovedilla, cubierta de teja/chapa/plana
  transitable, escalera de HA con Blondel, drenaje perimetral, corte capilar, vanos con
  alféizar y premarco, solados cerámico y flotante. Cada ficha lleva el **corte por capas**
  (nombre, espesor en mm y material), espesor total, usos, norma de referencia y avisos de obra.
- **Cuatro ediciones regionales**, igual que Neufert pero para el cómo se construye:
  - **México (RCDF/NTC)**: añade el muro de block de 14 cm **confinado** con castillos y dalas,
    el nodo castillo–dala, la losa reticular de vigueta, el tabique de ladrillo recocido y la
    cadena de desplante; **reemplaza** la azotea plana por la versión con prefabricado de 4 mm
    y acabado reflejo.
  - **Colombia (NSR-10)**: mampostería confinada del Título D, **bahareque cementado** con
    guadua, losa f'c 21 MPa, viga de fundación y cubierta de teja de barro anclada al viento.
  - **Argentina (IRAM/CIRSOC 103)**: **doble muro cerámico con cámara**, techo de chapa canal
    con manta aislante, vigas de encadenado perimetrales, ventana con **DVH** y rotura de puente
    térmico, membrana asfáltica en terrazas.
  - **Cuba (NC, clima tropical)**: bloque nacional con repello hidrófugo, **teja criolla**
    amarreada contra ciclón, cadena de cimentación, losa nervada de viguetas, ventana de
    celosía y piso de mosaico granito; **retira** el hormigón celular autoclavado (no corriente
    en el mercado nacional).
- La edición **nunca corrompe la base**: añade/reemplaza por id y retira lo que no aplica
  (deepcopy, idempotente, una región inválida deja la base intacta — como la norma: aconseja,
  nunca bloquea).

### Navegador en la GUI y CLI
- **Herramientas ▸ «Detalles constructivos (biblioteca regional)…»**: combo de edición
  regional, filtro por categoría, búsqueda sin acentos (material, norma o solución), ficha
  completa en el panel inferior y botón **⤓ SVG** para exportar el esquema acotado. Tooltips
  `det_*` y sugerencias en la barra de estado.
- **CLI sin proyecto**: `detalles regiones` (ediciones instaladas), `detalles list --region
  mexico --categoria muros --buscar sismo`, `detalles ver <id> --region colombia` (ficha
  completa) y `detalles svg <id> archivo.svg --region cuba`.

### Esquema SVG acotado del detalle (`exporters/detalle_svg.py`)
- Bandas de capas apiladas proporcionalmente con numeración, líneas de referencia, cota del
  **espesor total**, leyenda tabulada de materiales, notas de obra y cajetín con la edición
  regional y el id del detalle. 100% stdlib y **determinista byte a byte**.

### Calidad
- **NUEVO tests/test_122_detalles.py (27)**: carga de la base, fichas tipadas y espesores,
  búsqueda sin acentos, las 4 ediciones (añadir/reemplazar/retirar sin corromper la base,
  idempotencia, región inválida), exportador SVG determinista y tolerante, CLI de punta a
  punta y flujo GUI real (cambio de edición, ficha, exportación SVG, búsqueda).
- selftest 47 checks · suite completa 1032 pruebas en verde.

## Novedades v3.4.0 — DWG DE ENTRADA + BUNDLE PYINSTALLER VERIFICADO

### Importar planos DWG (pasarela a conversores locales)
- DWG es un formato binario propietario: ARQ GEN lo afronta con la vía honesta y 100% offline —
  **pasarela de conversión local a DXF** (`importers/dwg_reader.py`) y de ahí el motor §94 ya
  certificado (muros, locales, nombres desde TEXT, todo transaccional y auditado).
- **Conversores detectados automáticamente**: LibreDWG `dwg2dxf`, ODA File Converter (PATH y
  rutas de instalación típicas) o el suyo propio declarado en el asistente o en la variable
  `ARQGEN_DWG2DXF` (se invoca `<exe> <entrada> <salida>`).
- **En la GUI**: el asistente «Importar plano DXF/DWG (§94)» acepta .dwg, muestra la versión
  detectada (de R11/R12 a AutoCAD 2018), el conversor usado y el DXF temporal, y después el
  mismo PREVIEW → APLICAR de siempre. **En la CLI**: `importar dwg plano.dwg --file proyecto
  --convertidor ... [--aplicar]`.
- El informe de conversión NUNCA lanza: si no hay conversor explica las tres opciones
  gratuitas; si el conversor falla muestra su stderr; timeouts configurables.

### Bundle PyInstaller verificado (spec + verificador multiplataforma)
- **`ARQ_GEN.spec`**: espejo exacto de los flags de `03_COMPILAR.bat` (onedir, recursos,
  `collect-submodules ui`/`plugins.builtin`, exclusión de los seis bindings Qt). La paridad
  spec/bat queda vigilada por pruebas — imposible que se desincronicen.
- **`compilar_bundle.py`**: camino multiplataforma (Linux/macOS/CI). Compila con el spec y
  verifica el resultado: ejecutable presente, los 8 recursos clave dentro del bundle (incluido
  el catálogo PRECONS de 8,6 MB), `selftest` DEL EJECUTABLE y `precons certificar` del
  ejecutable. `--verify-only dist` para re-verificar; `--full` para todo.
- **Corrección real descubierta al compilar**: en intérpretes gestionados (uv/conda) de Linux,
  PyInstaller no recolecta `libtcl9tk9.0.so`/`libtk9.0.so` y el bundle no podía abrir la GUI;
  el spec ahora los recolecta del propio intérprete (no-op en Windows/macOS).
- **Verificación ejecutada**: bundle de 12,9 MB con selftest interno de 46 checks CORRECTO
  (incluida la GUI Tkinter real desde el ejecutable), proyecto demo generado por el exe y
  catálogo PRECONS III certificado desde el bundle.

### Calidad
- **NUEVO tests/test_121_dwg_bundle.py (34)**: versiones DWG tabuladas, descubrimiento de
  conversores, gateway con conversor falso (éxito, fallo con stderr, timeout), pipeline §94
  completo a través del gateway, CLI punta a punta, paridad spec/bat, verificador con runner
  inyectable y flujo GUI con .dwg.
- selftest 46 checks · suite completa 1005 pruebas en verde.

## Novedades v3.3.0 — IMPORTADOR §94 EN GUI (DXF) + VISTAS EN PDF/SVG/PNG

> Las dos brechas que quedaban del plan maestro quedan cerradas: el plano DXF entra por la GUI y
> cada vista del asistente sale en los tres formatos — vectorial SVG, imagen PNG y PDF imprimible
> con cajetín. Todo 100% stdlib, offline y determinista.

### Importar plano DXF desde la GUI (brecha #2)
- **Herramientas ▸ «Importar plano DXF (§94)…»**: asistente con PREVIEW → APLICAR sobre el motor
  DxfImporter (LINE de capas de muros + LWPOLYLINE cerradas de capas de locales, nombres desde TEXT).
- Capas explícitas opcionales (vacío = detección por nombre muro/wall y local/space/hab/ambiente),
  espesor de muro configurable (0,05–2,0 m) y nivel destino (se crea si no existe).
- El análisis muestra conteos, hasta 10 locales con área, avisos y errores ANTES de importar;
  la importación es transaccional, auditada (IMPORT_DXF) y refresca explorador y lienzo.
- El importador de catálogos ahora también acepta .txt delimitado en su selector de archivos.

### Vistas del asistente en PNG y PDF (brecha #4)
- **«⤓ SVG / ⤓ PNG / ⤓ PDF»** en la fila de vistas: los tres formatos dibujan EXACTAMENTE lo mismo
  que el lienzo (comparten el Drawing de core.geometry.representation).
- **PNG raster** (nuevo `export_view_png`): Canvas ampliada con línea Bresenham con grosor,
  polilínea, arco paramétrico y relleno poligonal por scanline; tramas de material rasterizadas,
  guiones aproximados y franja de título. Resolución configurable (px/m) con tope de tamaño.
- **PDF vectorial A4 apaisado** (nuevo `export_view_pdf`): PdfDoc ampliada con color RGB y guiones
  (retrocompatible con la API en grises), tramas vectoriales recortadas con Liang-Barsky, arcos
  poligonales y cajetín con vista y escala aproximada («ESC 1:X aprox»).
- Nuevo dispatcher `export_view(...)` por extensión (.svg/.png/.pdf) y determinismo byte a byte:
  mismas entradas → mismo archivo.

### Calidad
- **NUEVO tests/test_119_vistas_png_pdf.py (10)**: estructura de chunks PNG y objetos PDF,
  determinismo, 4 vistas × formatos, arcos orgánicos, datos vacíos y retrocompatibilidad de PdfDoc.
- **NUEVO tests/test_120_dxf_gui.py (12)**: primitivas nuevas de Canvas, diálogo y ganchos _dxf_*,
  flujo GUI analizar→importar real (muros/espacios/level/nombres desde TEXT), avisos y hooks de
  exportación SVG/PNG/PDF del asistente.
- **selftest check 45**: vistas en PDF/PNG/SVG con cabeceras válidas + preview §94 de un DXF
  generado al vuelo → **45 checks**.

---

## Novedades v3.2.0 — DISEÑO ORGÁNICO (distribución articulada, muros curvos y diagonales)

> La edificación deja de ser una caja rígida: los locales se **articulan**, la envolvente gana **muros curvos** y **diagonales**, y el pasillo **respira** — sin perder un solo metro cuadrado ni romper un vano.

- **Nuevo parámetro «Distribución interior»** en el paso 1 del asistente, con tres caracteres: **Ortogonal** (el trazado clásico de siempre), **Articulada** (fondos escalonados por local, chaflanes a 45° en las esquinas de la envolvente y pasillo con curva suave) y **Orgánica** (todo lo anterior, con esquinas **redondeadas en radón**, **fachada en arco** y **pasillo serpenteante**).
- **Fondos escalonados**: cada local juega en profundidad (la fachada trasera «respira» en esquema lineal); las áreas **solo crecen** — nunca se reduce un local por debajo de lo pedido.
- **Muros curvos de verdad**: la fachada más larga sin vanos se abulta en arco (flecha ajustable), las esquinas de la envolvente se redondean con radón tangencial o se cortan a 45°, y el muro libre del pasillo ondula en S. Todo se materializa en muros rectos cortos: vanos, QTO, representación, exportadores DXF/SVG y presupuesto funcionan sin cambios.
- **Seguridad arquitectónica verificada**: NUNCA se toca una pared compartida entre dos locales (detección geométrica por lados, no por conteo), los recortes de esquina son **conscientes de los vanos** (el chaflán se ajusta para no alcanzar ninguna puerta/ventana y corre los offsets) y la S del pasillo respeta el galibo (nunca invade más de la mitad del ancho libre sobre 1,20 m).
- **Curvatura y semilla reproducibles**: la **curvatura** (0,3–4,0 m) dosifica el gesto y la **semilla** reproduce exactamente la misma planta (prueba varias y quédate con tu favorita); validación amable en el paso 1.
- **Ayuda viva**: tres tooltips nuevos (distribución, curvatura, semilla), el resumen del paso 6 cita la distribución con su descripción y los avisos explican cada gesto aplicado («Distribución orgánica: 2 esquinas redondeadas, fachada en arco.»).
- Selftest con check 44 (44 checks) y **21 pruebas nuevas** en `test_118_organico.py` (geometría de arcos/chaflanes/radones, fondos que solo crecen, determinismo por semilla, paredes compartidas intactas, vanos que caben en su muro tras el gesto, galibo del pasillo, idempotencia y `apply_plan` creando el proyecto completo).
- **Suite en verde: 949 pruebas** (928 + 21).

---

## Novedades v3.1.0 — CERTIFICACIÓN DEL CATÁLOGO PRECONS III (integridad verificable del libro oficial)

> El catálogo oficial PRECONS III (RoPres 3.30) embebido en la aplicación quedó **certificado 1:1** contra el XLSX del repositorio de origen y ahora la app puede **recertificarse sola**, sin proyecto ni conexión.

- **Certificación 1:1 contra la fuente**: el ruleset `precons_iii_rospres_330` (v3.30) coincide dict a dict con `Catalogo_PRECONS_III_Completo.xlsx` del repositorio oficial — **15981 renglones** (código, descripción, unidad, capítulo/subcapítulo y los 4 precios CUP de cada uno) y **4383 recursos** (3569 materiales, 671 equipos, 143 mano de obra) con su precio de lista, además de **38 secciones**, 8 parámetros y 4 límites; 0 renglones omitidos y 0 errores en la reimportación del libro.
- **Nuevo comando `precons certificar`** (no requiere proyecto): comprueba recuentos oficiales contra la línea base, unicidad de códigos de renglón y recurso, consistencia del desglose de precios (**materiales + mano de obra + equipos = total** en los 15981 renglones, tolerancia 1 centavo) y **SHA256 del fichero empaquetado** (8.603.883 bytes). Sale con código 0 si el catálogo está íntegro y 1 con el detalle de fallos si está alterado.
- **Detección de manipulación**: alterar un precio, quitar renglones o recursos, o corromper el JSON se detecta y reporta — la línea base (15981/4383/3569/671/143/38/8/4) queda fijada en `services/precons_service.py` (`CATALOG_BASELINE`) y cualquier desviación exige una decisión consciente de versión.
- **Check de selftest 43** (43 checks en total) y **10 pruebas nuevas** en `test_117_precons_certificacion.py` (recuentos, SHA256 estable, precios oficiales de referencia, detección de manipulación y salida del CLI).
- **Suite en verde: 928 pruebas** (918 + 10).

---

## Novedades v3.0.0 — INTERFAZ MODERNA Y DINÁMICA (temas claro/oscuro, ayuda viva, clic derecho, autoguardado)

> La interfaz da el salto: más moderna, dinámica e intuitiva **sin abrumar**, con la información justo cuando se necesita.

- **Modo claro y modo oscuro con cambio EN VIVO** (`Ctrl+T` o botón 🌓 de la barra): los dos temas comparten el mismo lenguaje visual (fondo por capas, un acento amable, jerarquía sin ruido) y el cambio es instantáneo — estilos ttk, menús, lienzo, tramas, colores de entidades y globos de ayuda se adaptan al momento. La elección **se recuerda** para la próxima vez (preferencias por usuario en `~/.arqgen/prefs.json`).
- **Autoguardado ante cada cambio**: cualquier acción del proyecto marca pendiente y, tras 1,2 s de calma, se vuelca a SQLite con el mismo mecanismo de `Ctrl+S` (nunca a mitad de una ráfaga de comandos; commit sin eventos → sin bucles). La barra de estado muestra siempre `💾 Guardando… / Autoguardado HH:MM:SS`; se pausa desde el menú Ver y la hora del último guardado queda a la vista.
- **Clic derecho con menús contextuales**: sobre el lienzo (editar «objeto», estado de la entidad, eliminar — o zoom/encuadrar/nuevo objeto si el clic es en vacío), sobre el explorador (nuevo objeto en esa disciplina, editar, eliminar) y sobre el panel de propiedades. Y el clic derecho sigue moviendo el plano si **arrastras**: menú si es clic, pan si es gesto.
- **Rueda del ratón completa**: rueda = zoom anclado al cursor, **Mayús+rueda = desplazamiento horizontal** del plano; en el resto de paneles, scroll natural.
- **Ayuda viva en cada control**: los globos de ayuda ahora se colorean según el tema activo, la barra de estado sigue explicando cada botón al pasar el cursor y llega el modo **«¿Qué es esto?»** (Mayús+F1 o menú Ayuda): pulsas cualquier control y una tarjeta no modal con autocierre te explica para qué sirve (sin bloquear el trabajo).
- **Íconos según funcionalidad**: registro central de glifos (`ui/icons`) aplicado a la barra de herramientas (asistentes, encuadre, zoom, objeto, editar, guardar, buscar) con etiquetas de texto — reconocibles de un vistazo sin perder claridad.
- **Logo de la aplicación**: logotipo programático determinista (chevron de cubierta sobre líneas de forjado, placa redondeada con degradado) generado sin dependencias en `resources/branding/`: **ícono del EXE** vía PyInstaller `--icon logo.ico` (multi-tamaño 16→256 px, `03_COMPILAR.bat`) e **ícono y logo en la ventana principal** (`iconphoto` + tarjeta de marca en la barra).
- **Aprovechamiento del espacio**: panel inferior integrado en el layout redimensionable (arrastras el separador y el plano gana), y **paneles colapsables** — explorador (`Ctrl+1`), propiedades (`Ctrl+2`) y avisos/registro (`Ctrl+3`) — desde el menú Ver; la visibilidad se recuerda.
- **Menú Archivo con «Guardar»** a la vista, **atajos nuevos documentados** (Ctrl+T tema, Ctrl+1/2/3 paneles, Mayús+F1 ayuda) y preferencias de usuario tolerantes (archivo ausente o corrupto → valores por defecto sin romper el arranque).
- Selftest con comprobación de interfaz (42 checks: tokens gemelos, mutación en el sitio, glifos, logo PNG/ICO determinista, preferencias y autoguardado por calma) y **918 pruebas** (41 nuevas en `test_116_ui_v3.py`).

> Desde v3.1.0: **928 pruebas** y 43 checks de selftest (certificación del catálogo PRECONS III). Desde v3.2.0: **949 pruebas** y 44 checks (diseño orgánico). Desde v3.3.0: **971 pruebas** y 45 checks (vistas PDF/SVG/PNG e importador DXF en GUI). Desde v3.5.0: **1032 pruebas** y 47 checks (biblioteca de detalles constructivos por ediciones regionales). Desde v3.6.0: **1071 pruebas** y 48 checks (detalle en PDF/PNG y vínculo con la tipología constructiva). Desde v3.7.0: **1097 pruebas** y 49 checks (ventanas y paneles ajustables). Desde v3.8.0: **1127 pruebas** y 50 checks (layout restaurable, ediciones España/Perú/Chile y PDF de documentos). Desde v3.8.1: **1132 pruebas** y 50 checks (selftest portable al ejecutable). Desde v3.9.0: **1143 pruebas** y 51 checks (interfaz compacta, plano primero). Desde v3.9.1: **1152 pruebas** y 51 checks (migración del panel inferior compacto). Desde v3.10.0: **1168 pruebas** y 52 checks (edificación regenerativa, nada de cambios huérfanos). Desde v3.11.0: **1188 pruebas** y 53 checks (vista 3D axonométrica). Desde v3.12.0: **1219 pruebas** y 54 checks (presupuesto vivo sobre las variantes). Desde v3.13.0: **1267 pruebas** y 55 checks (sombras solares, terreno 3D e IFC de entrada/salida). Desde v3.13.1: **1268 pruebas** y 55 checks (consola a prueba de Windows). Desde v3.14.0: **1295 pruebas** y 56 checks (herramientas de edición tipo CAD y asistente de modificaciones). Desde v3.15.0: **1381 pruebas** y 57 checks (concepción de espacios: mobiliario, cubiertas y accesibilidad). Desde v3.16.0: **1455 pruebas** y 58 checks (teclado y puntero AutoCAD, editor de locales y cubiertas v2). Desde v3.17.0: **1487 pruebas** y 59 checks (cota de implantación de la cubierta y vista 3D en perspectiva). Desde v3.18.0: **1548 pruebas** y 60 checks (ascensores según Neufert y fachada: parasoles y pieles exteriores). Desde v3.19.0: **1624 pruebas** y 61 checks (escaleras por tipología, aberturas, iluminación y alarmas por locales). Desde v3.19.1: **1632 pruebas** y 61 checks (selección en el plano corregida). Desde v3.20.0: **1682 pruebas** y 62 checks (asistente de local para modificar y especialidades de salud). Desde v3.21.0: **1698 pruebas** y 63 checks (pasillos hospitalarios por DNA, equipos médicos en el presupuesto vivo y ficha imprimible del local). Desde v3.22.0: **1730 pruebas** y 64 checks (especificaciones técnicas hospitalarias y validación dimensional por local). Desde v3.23.0: **1758 pruebas** y 65 checks (catálogo maestro de viviendas: compatibilidad estilo-sistema, programa paramétrico del §7, validación VIV001-030 y calidades 1-5). Desde v3.24.0: **1783 pruebas** y 66 checks (estudios de vivienda: alternativas comparables §62-63, modulación §56 y energía solar §38). Desde v3.25.0: **1802 pruebas** y 67 checks (documento comercial CC/OF: 20 tipologías, 59 cuadros MIN/REC, programa §89-90, relaciones §78, validación honesta y equipos sin calidad). Desde v3.26.0: **1832 pruebas** y 68 checks (documento educacional: 4 tipologías, 82 cuadros MIN/REC, programa paramétrico §106-109, relaciones §98-101 con flujos §102, validación honesta, seguridad infantil §89 y equipos sin calidad). Desde v3.27.0: **1844 pruebas** y 69 checks (informe de validación en HTML autocontenido con «Guardar HTML...» en los tres cuadros). Desde v3.28.0: **1862 pruebas** y 70 checks (presets de configuración del asistente en JSON local). Desde v3.29.0: **1879 pruebas** y 71 checks (comparador de variantes de planta: matriz, texto cp1252 y CSV). Desde v3.30.0: **1903 pruebas** y 72 checks (servicios de vivienda: piscina §45 con valores calculados a mano, acústica §46 con muros medidos y domótica §39 con conteos del modelo). Desde v3.31.0: **1918 pruebas** y 73 checks (DXF R12 ASCII con AC1009 sin LWPOLYLINE y coste ligado al check con el renglón oficial 011111 x 500). Desde v3.32.0: **1940 pruebas** y 74 checks (multiplicadores de niveles / planta tipo repetida: expansión sana, nombres únicos, cotas y plan multiplicados, identidad con x1). Desde v3.33.0: **2001 pruebas** y 75 checks (herramientas de dibujo a dos clics con reglas del DNA y asistente de servicios por temática: 6 servicios, 46 locales, programa dimensionado y aplicación con zona, pasillo y relaciones). Desde v3.34.0: **2041 pruebas** y 76 checks (desde dibujo, generación inversa: contorno por espacio, rectángulo o DXF, inferencia de forma y medidas, programa por servicio o usos del DNA, ajuste honesto con crecimiento en altura y escalera según Blondel, y generación real por los caminos oficiales). Desde v3.35.0: **2090 pruebas** y 77 checks (servicios médicos: catálogo v2.0 con morgue, tomografía, UCI, cuidados intermedios y urgencias, anatomía patológica enriquecida a 16 locales, grupos con subtotales, criticidad por niveles, puertas y circulación del catálogo, validación con prohibidas y separación limpio/sucio, y los documentos del servicio: ficha de local §30, matriz de instalaciones §22, relaciones §17, flujos §18 y 20 reglas de generación §24). Desde v3.36.0: **2131 pruebas** y 78 checks (catálogo universal v3.0: 34 servicios en 8 sectores con filtro por sector en el asistente y en «Desde dibujo», 23 servicios nuevos —12 de salud y 11 de otros usos—, explorador del catálogo en el flujo desde dibujo y recintos-nave para locales de superficie grande). Desde v3.37.0: **2172 pruebas** y 79 checks (DXF real: unidades $INSUNITS escaladas a metros, cierre geométrico de polilíneas, contornos de planta descompuestos en segmentos de muro, textos vacíos avisados, cierre automático de contornos casi cerrados y el flujo desde dibujo → servicio probado con el plano real «AP Y MORGUE»). Desde v3.38.0: **2235 pruebas** y 80 checks (dibujo y navegación estilo CAD clásico: gramática de coordenadas 10,5 / @10,5 / @10<45 / 25 y =expresiones seguras, línea de comandos con historial y F2, zoom ventana/anterior con pila de 32, selección ventana/cruce azul/verde, referencias extremo/intersección/medio/centro con precedencia, rejilla anidada adaptativa, DYN y aliases MU/ES/ZO/PU/VE y Z/ZE/ZP/QC). Desde v3.39.0: **2300 pruebas** y 81 checks (desde dibujo reforzado: validación previa del contorno, checklist, contratos PlanRequest/PlanResult, alternativas con puntuación explicada, decisiones sin IA, reemplazo del edificio previo, configuraciones y estado en el proyecto, quick-spec en una línea y patio experto). Desde v3.39.1: **2307 pruebas** y 82 checks (hilo seguro SQLite: check_same_thread=False + candado reentrante, regresión completa del «ERROR AL IMPORTAR» con hilos reales). Desde v3.40.0: **2337 pruebas** y 83 checks (encaje estricto al polígono: tesela la parcela en contenedores reales, nada se sale, la forma se aprovecha y el aprovechamiento se declara). Desde v3.41.0: **2372 pruebas** y 84 checks (programa adaptable: selección de locales por temática documentada y ajuste dimensional mínimo/medio/estricto con la rebaja de norma declarada local a local). Desde v3.42.0: **2399 pruebas** y 85 checks (pasillos y filtros: el pasillo se reserva primero y los locales lo sirven adaptando fondo por ancho, teselado completo hasta los bordes, orden por flujo con el filtro sanitario como barrera y compactación que baja de niveles hasta teselar el caso real AP + morgue en 1 planta al 95 %+). Desde v3.43.0: **2436 pruebas** y 86 checks (vivienda social: DNA con Sala de 9 m2 y lavadero doméstico, «1 nivel» tope duro que compacta antes de crecer con ARQ-DDI-011 que nombra lo excluido, sala distribuidora sin pasillo en casas de <= 60 m2, chaflanes a 45 grados y mobiliario automático)

---

## Novedades v2.8.0 — EDICIONES REGIONALES DE NEUFERT (el libro adaptado por región)

> El libro se publica adaptado por regiones: clima, materiales y códigos locales cambian valores concretos. ARQ_GEN ahora lleva la base del libro **y las ediciones regionales** con fusión profunda.

- **Ediciones regionales instaladas** en `resources/knowledge/neufert_regions/`: **Cuba** (adaptación caribeña), **México** (edición mexicana, RCDF), **Argentina** (adaptación IRAM-CIRSOC 251) y **Colombia** (adaptación NSR-10 / NTC 4147). Cada fichero declara código, edición, referencias y aviso de «verificar la norma local vigente».
- **Cuba tropical**: techos de 3,0–3,5 m (el aire por persona), luz de ventanas **1/5–1/4 del suelo** (ventilación cruzada), alero de 1,20 m y **portal de 2,40 m**, plaza de auto compacta (2,30×4,60 m con pasillo de 5,50 m), puerta principal doble de 1,20 m.
- **México**: techos contenidos 2,40–2,70 m, mampostería **confinada de block 0,14 m**, rampas hasta 10 % en tramos cortos, azotea plana de losa. **Argentina**: techo 2,60 m, ladrillo común **0,18 m**, rampa al 8 % (IRAM-CIRSOC 251). **Colombia**: techo 2,50 m, confinada **0,15 m** (NSR-10), accesibilidad NTC 4147.
- **Lo universal no se toca**: la fórmula de Blondel, los pasillos de camillas (2,40 m), las puertas de 1,20 m en salud y los recuentos de aseos son idénticos en todas las ediciones. La fusión es **profunda**: cada región solo reemplaza lo suyo.
- **Base blindada con deepcopy**: rondar todas las regiones y volver a la base devuelve exactamente los valores del libro (detectado y corregido un bug de corrupción por copia superficial).
- **Combo «Edición regional Neufert» en el paso 1** del asistente: cambiar la edición re-aplica los valores del libro (solo sube), sincroniza pasillo/puerta/muro del paso 4 y avisa con el nombre de la edición. Los avisos normativos citan la edición activa («Neufert (edición Cuba): el acristalado suma al menos 1/5 del suelo…») y el resumen añade «· Edición: Cuba».
- **Nuevas reglas del libro en la base** (catálogo v2.1, 21→26 secciones): **evacuación** (hoja 0,90 m hasta 50 personas, 1,20 m hasta 100; distancias de 30/45 m), **ergonomía** (trabajo de pie 0,85–1,10 m, sentado 0,73 m), **oficinas** (puesto 4–6 m², cubículo 1,50 m, juntas 2 m²/persona), **comercio** (pasillos de venta 1,50–3,00 m, depósito 15–25 %) y **alojamiento** (celda 6/9 m², +3 m² por persona extra). El bloque `normativa` del metadata ahora incluye **edicion_regional**, **evacuación** y la **sección propia del uso** (salud, oficinas, comercio, alojamiento, educación, comedor).
- Ayuda dinámica (`bld_region`), selftest con comprobación regional (41 checks) y **877 pruebas** (32 nuevas en `test_115_neufert_regional.py`).

---

## Novedades v2.7.0 — NORMATIVA NEUFERT (reglas y especificaciones del libro)

> Todas las reglas dimensionales del asistente se apoyan ahora en *«El arte de proyectar en arquitectura»* de **Ernst Neufert**, el libro que mide la arquitectura con el cuerpo humano.

- **Catálogo normativo nuevo** `resources/knowledge/neufert_standards.json` (20 secciones): antropometría (paso 0,60 m, círculo de giro 1,50 m), puertas, pasillos por uso, escaleras (fórmula de **Blondel** 2h+p = 0,60–0,64 m), rampas (máx. 8 %), ventanas (el acristalado suma **1/8 a 1/6 del suelo**), alturas libres por uso, mobiliario de referencia, separaciones entre muebles, aseos y su **recuento por ocupación**, estacionamiento (2,50×5,00 m, accesible 3,50×5,00 m), espesores de muro por tipología, pendientes de cubierta, cocina (triángulo de trabajo 4–7 m), salud (camillas), educación y comedor colectivo.
- **Módulo `domain/neufert.py`**: registro tipado con consultas (pasillo/puerta/escalera/altura/muro/aseos/estacionamiento por uso) y carga resiliente (la norma aconseja, nunca bloquea).
- **Space DNA v2.0**: 28 tipos de local (6 nuevos: **Aseo, UCI, Comedor colectivo, Cocina institucional, Biblioteca y Estacionamiento**), todos con su bloque `neufert` (puerta sugerida, referencia dimensional y criterio del libro) que viaja a los **requerimientos de cada local** generado.
- **Escalera por uso social**: vivienda 17,5×28 cm (Blondel 0,63); salud y escuelas 16×30 cm (Blondel 0,62) con **caja de 1,80 m para camillas**; la caja clásica de 1,40 m nunca se encoge. El requerimiento del local escalera guarda contrahuella, huella, Blondel y la norma.
- **Sugerencias normativas al cargar el programa del uso** (`apply_neufert_defaults`): pasillo a 2,40 m y puerta de 1,20 m en salud, espesor de muro por tipología (0,20 m mampostería, 0,40 m piedra, 0,45 m tierra…). **Solo sube**: nunca reduce lo que el usuario pidió, y la GUI lo explica y sincroniza los campos del paso 4.
- **Avisos normativos no bloqueantes** (`neufert_advisories`) en resumen y generación: pasillo corto para el uso, puerta sin ancho de camilla, luz de ventana por debajo de 1/8 del suelo, altura libre menor que la recomendada, rampa del desnivel al 8 % y estacionamiento en usos públicos.
- **Metadata del edificio** con el bloque **`normativa`** completo (fuente, pasillo, puerta, escalera Blondel, rampa, alturas, accesibilidad, muros por tipología, estacionamiento) y línea «Normativa Neufert…» en el resumen del paso 7.
- **Presets afinados con el libro**: aulas de 6,00×6,00 m (36 m² = 2 m²/alumno), biblioteca en la escuela y **UCI de 2 camas (18 m²/cama)** en la planta de quirófanos del hospital. Ventana por defecto de 1,40×1,20 m para cumplir el ratio de luz.
- Ayuda dinámica ampliada (`bld_neufert`), selftest con comprobación Neufert y **845 pruebas en verde** (43 nuevas en `test_114_neufert.py`).

---

## 1. Qué incluye esta fase

| Componente | Estado | Detalle |
|---|---|---|
| Núcleo (CORE) | ✔ completo | Entidades con UUID persistentes, códigos humanos (`ARQ-WALL-001`), unidades con control de dimensiones, eventos, Command Bus con undo/redo transaccional, motor de reglas con lenguaje de fórmulas seguro (sin `eval`), validación, grafo de dependencias, auditoría, versionado, backups, permisos, sistema de plugins |
| Motor geométrico 2D | ✔ completo | Point/Line/Polyline/Arc/Circle/Ellipse/Polygon + `distance, angle, area, perimeter, centroid, intersection, contains, overlaps, offset, trim, extend, split, join, fillet, chamfer, mirror, rotate, translate, scale, project, nearest_point, bounding_box` + reparación geométrica con el patrón DETECTAR→EXPLICAR→PROPONER→APROBAR→APLICAR→REVALIDAR |
| Modelo semántico | ✔ completo | Project→Site→Building→Level→Zone→Space→Wall→Door/Window/Opening + relaciones entre locales como entidades + Space DNA (conocimiento técnico en JSON) |
| Persistencia | ✔ completo | SQLite con migraciones versionadas y reversibles, repositorios indexados, backup con verificación de integridad |
| Módulo Arquitectura | ✔ completo | Niveles, zonas, locales, muros, puertas, ventanas; relaciones espaciales por geometría; adyacencias con explicación |
| QTO (cómputo) | ✔ completo | Fórmulas paramétricas en datos (JSON), cantidades con origen trazable, desperdicio, recálculo **incremental** por hash de entrada |
| Precios y presupuesto | ✔ completo | Listas de precios con histórico (nunca se sobrescribe un precio), recursos, capítulos/partidas/recursos, directos + indirectos + otros = total |
| Interoperabilidad | ✔ completo | Exportación **DXF** (ezdxf, capas ARQ-*, un layout por nivel), **XLSX** (openpyxl), **CSV**, **JSON** (ida y vuelta completa) |
| Instalaciones (FASES 10–13) | ✔ completo | **Módulo INSTALLATIONS CORE**: redes Nodo→Tramo con trazado, caminos de coste mínimo, validación topológica (árbol radial/sumaidero) y detección de finales muertos; **motor de rutas** ortogonal determinista con obstáculos (muros), cruces, holguras y corredores preferentes; **motor eléctrico** (corrientes 1φ/3φ, factores de demanda, caída de tensión IEC, protecciones normalizadas, secciones con coordinación In≤Iz, canalización al 40%, balanceo de fases); **motor sanitario** (caudales con simultaneidad, Hazen-Williams, Manning en gravedad, diámetros y pendientes por tabla, bombeo TDH/potencias, tanques); **motor HVAC** (carga térmica por componentes, caudal de aire, ductos circulares/rectangulares, selección de equipos del catálogo). Todo integrado con QTO (13 fórmulas nuevas), presupuesto (capítulos 03–05), eventos, auditoría, undo/redo y validación |
| Pluviales, gas y telecom (FASES 14–16) | ✔ completo | **Pluviales**: método racional de captación, canalón tipo canal rectangular (Manning), bajantes por tabla, colectores Manning al 50%, tanque de detención V=Q·t y evacuación con margen 10%. **Gas**: caudal por PCI y unidades de consumo, Darcy-Weisbach con catálogo de DN, velocidad máxima, validaciones de válvulas por aparato, ventilación 1/50 del suelo, separación gas-eléctrico y recorridos. **Telecom**: llenado de canalización ≤40%, enlace horizontal TIA-568 de 90 m, rack U, puertos patch/switch, presupuesto óptico de fibra. QTO con 10 fórmulas nuevas y comandos `plu/gas/tel` |
| Estructura (FASES 17) | ✔ completo | Materiales (hormigón/acero/mampostería/madera), secciones rectangulares/circulares/perfil I con propiedades, acciones y combinaciones ULS/SLS (1,35G+1,5Q, viento, sismo), vigas isostáticas y empotradas (reacciones, cortante, momento, flecha elástica), pilares (esbeltez, pandeo de Euler, utilización), torsión circular, **cerchas por método de los nudos** con solver gaussiano determinista, uniones (pernos y soldadura), cantidades de acero, QTO (CONCRETE_VOLUME/STEEL_WEIGHT/FORMWORK_AREA) y comandos `struct` |
| Seguridad (FASES 18–23) | ✔ completo | **FOV**: cono de cobertura por ray casting contra muros, puntos ciegos por retícula, solapamientos, detección de objetivos y candidatos de optimización. **CCTV**: cableado (ruta + rulo + desnivel + reserva), ancho de banda, PoE, almacenamiento y retención, capacidad switch/NVR. **Fuego**: cobertura de detectores por local, carga de lazo, batería 24 h + alarma, matriz **causa/efecto** parametrizada por ruleset. **Intrusión**: zonas, PIR por área, contactos, panel, batería y sirenas. **Acceso**: controladores, alimentación, batería y liberación de evacuación fail-safe. **Perímetro**: sensores de valla, cámaras y accesos. BOM de seguridad, QTO (14 fórmulas) y comandos `sec` |
| Coordinación y clash (FASES 24–25) | ✔ completo | Motor de interferencias determinista: HARD (dentro de muro), SOFT (proximidad), CLEARANCE (holgura), ACCESS (frente de maniobra), MAINTENANCE (zona de retiro) y ROUTE (cruce de rutas); entidad Clash con ciclo de vida OPEN→REVIEWED→ACCEPTED/RESOLVED/IGNORED, deduplicación por par de objetos, eventos CLASH_CREATED/CLASH_RESOLVED y comandos `clash` |
| PRECONS / SIECONS-like (FASES 30–31) | ✔ completo | Ruleset **versionado** de partidas/indicadores/recursos/rendimientos/precios (datos JSON, no tablas rígidas), análisis de precio unitario con coeficientes de transporte, indirectos y beneficio, takeoff por partida, análisis del proyecto alimentado por QTO, variantes (BASE/ECONOMIC/PREMIUM) con comparación, actualización de precios e **importador/mapeador** de bases externas por mapa de columnas; comandos `precons` |
| Importación externa (spec 94, v1.7.0) | ✔ nuevo | **Pipeline completo de 9 etapas** (DETECTAR→PARSE→VALIDAR→MAPEAR→CONVERTIR→PREVIEW→APROBAR→IMPORTAR→AUDITAR) sobre archivos externos: **catálogos PRECONS** (.xlsx/.csv/.json → ruleset con autodetección de hojas/columnas por sinónimos, mapa explícito opcional, importación plana por partida+insumo o multi-hoja con recursos/rendimientos/precios) y **planos DXF** (LINE→muros, LWPOLYLINE cerrada→locales con nombre desde TEXT/MTEXT, capas por pista muro/wall y local/space o capas explícitas) y **planos DWG** (v3.4.0: pasarela a conversores locales — ODA File Converter, LibreDWG o `ARQGEN_DWG2DXF` — con informe de versión y conversor; nunca lanza). Siempre PREVIEW antes de APLICAR; la aplicación es transaccional (CommandBus), audita `IMPORT_DXF`/import y emite eventos. Comando `importar catalogo|dxf|dwg`; `precons import` acepta ahora .xlsx/.csv |
| BIM e IFC (FASES 32–33) | ✔ completo | Modelo BIM interno ligero: cada objeto proyecta categoría, geometría, nivel, material, propiedades, clasificación, sistemas y relaciones (spec 63); árbol espacial Project→Site→Building→Storeys; **exportador IFC4 SPF** (ISO 10303-21) con IfcProject/IfcSite/IfcBuilding/IfcBuildingStorey/IfcSpace/IfcWall/IfcDoor/IfcWindow/IfcOpeningElement/IfcBeam/IfcColumn/IfcMember/IfcDistributionElement, IfcRelAggregates/ContainedInSpatialStructure/VoidsElement/FillsElement y GlobalIds deterministas; comandos `bim` y `export --format ifc` |
| Documentación (FASES 34) | ✔ completo | **Motor de planos** (spec 69): entidad Drawing con hoja, formato A0–A4, escala normalizada, orientación, vista, capas, anotaciones (Dimension/Text/Leader/Symbol/Hatch/Block/Viewport) y cajetín automático; **documentos paramétricos** (spec 70): plantillas con variables `{{PROJECT.NAME}}`, `{{CLIENT.NAME}}`, `{{BUDGET.TOTAL}}`, `{{QTO.TOTAL_WALL_AREA}}`… con validación estricta de variables sin resolver; **generación de documentos** (spec 68): memoria descriptiva, memoria técnica, especificaciones, cuadros de superficies/vanos, listados e informe de interferencias, en Markdown/HTML deterministas; **documentación automática por módulo** (spec 106): README/API/DATA MODEL/RULES/FORMULAS/TESTS/CHANGELOG; comandos `docs` |
| Optimización multiobjetivo (FASES 35) | ✔ completo | Motor del spec 19: los **12 objetivos** (AREA, COST, DISTANCE, CIRCULATION, LIGHTING, VENTILATION, PRIVACY, ACCESSIBILITY, SECURITY, MAINTENANCE, MATERIAL, COMPLEXITY) evaluados sobre el modelo con su dirección (minimizar/maximizar), **sin score mágico**; dominancia de Pareto, frente no dominado, comparación objetivo a objetivo con deltas y rangos; variantes cargables desde JSON; comandos `optimize` |
| Auditoría, versiones y backup (FASES 36–38) | ✔ completo | Auditoría filtrable (usuario, comando, tipo, objeto, rango de fechas) con estadísticas y exportación CSV/JSON (spec 71); versionado completo save/list/restore/**compare/export/branch** (spec 80) con backup automático previo a restaurar; backup **autosave rodante**, **incremental por hash SHA-256 con manifiesto**, estado y checkpoint del journal WAL, verificación de todas las copias y **recuperación automática** de proyectos corruptos conservando copia forense (spec 81); comandos `audit show|stats|export`, `version …`, `backup …` |
| Plugins y rendimiento (FASES 39–40) | ✔ completo | Contrato de plugins (spec 88-89) con **validación estática sin ejecutar**, información detallada de declaraciones y **andamiaje generador** de plugins externos; rendimiento (spec 86-87): suite de **benchmark determinista** de 8 operaciones (geometría, adyacencias, QTO, presupuesto, optimización, documentación, clash, exportación) con ops/s y **inventario de las 6 cachés** (geometry/rules/catalog/calculation/routing/coverage) con sus claves de invalidación; comandos `plugins validate|info|new` y `benchmark run|caches` |
| QA final (FASES 41–43) | ✔ completo | Suite de **305 pruebas** con valores dorados (presupuesto, IFC, QTO, PRECONS, demanda eléctrica, acero), TEST-021 Documentación y TEST-024 Recuperación cubiertos; selftest de **23 comprobaciones**; empaquetado PyInstaller onedir verificado |
| Interfaz | ✔ completa (CLI) | Consola profesional con más de 100 comandos; mensajes en español; códigos de salida para scripts |

**Fuera del alcance** hasta el cierre del plan maestro: solo la interfaz gráfica de ventanas (§90), preparada para engancharse a las fachadas de servicios existentes (spec 90-93). Todas las fases de dominio del plan maestro (1-43) están entregadas y funcionales.

---

## 2. Requisitos

- Windows 10/11 (los .bat también funcionan en Windows 8.1 con PowerShell disponible)
- **Python 3.13** instalado desde https://www.python.org/downloads/ (marcar *Add python.exe to PATH*)
- Solo para `01_INSTALAR_DEPENDENCIAS.bat`: internet una vez. Después, todo offline.

---

## 3. Instalación y uso (en orden)

| Paso | Archivo | Qué hace |
|---|---|---|
| 1 | `00_VERIFICAR_ENTORNO.bat` | Detecta Python 3.13 (`py -3.13` → `python3.13` → `py` → `python`), verifica versión y biblioteca estándar, guarda la elección en `config\python_home.txt`. **Registra todo en `logs\setup\`** |
| 2 | `01_INSTALAR_DEPENDENCIAS.bat` | Crea el entorno virtual `.venv`, instala `ezdxf`, `openpyxl` y `pyinstaller` con pip. Congela versiones instaladas en `logs\setup\pip_freeze_*.txt`. **Ejecutar UNA vez (con internet)** |
| 3 | `02_PRUEBAS.bat` | Ejecuta la suite completa (877 pruebas) → `logs\tests\run_*.log`. Sale con error si algo falla |
| 4 | `03_COMPILAR.bat` | Pipeline completo con logs en las tres etapas: **pruebas antes** (`logs\tests\pre_build_*.log`) → **compilación PyInstaller** (`logs\build\build_*.log`) → **selftest del ejecutable después** (`logs\tests\post_build_*.log`). Si algo falla, se detiene y muestra el log correspondiente. Genera `dist\ARQ_GEN\ARQ_GEN.exe`. En Linux/macOS/CI existe el equivalente multiplataforma: `python compilar_bundle.py` (usa `ARQ_GEN.spec` y verifica recursos + selftest + catálogo del ejecutable) |
| 5 | `04_EJECUTAR.bat` | Ejecuta la CLI en modo desarrollo (Python local) |
| 6 | `05_EJECUTAR_COMPILADO.bat` | Ejecuta el `ARQ_GEN.exe` compilado |
| 7 | `06_DEMO.bat` | Genera el proyecto demo completo y exporta DXF/XLSX/JSON/CSV a `output\` |
| 8 | `07_LIMPIAR.bat` | Limpia `build\`, `dist\` y cachés (no toca proyectos, backups ni logs) |
| 9 | `08_GUI.bat` | Abre la interfaz gráfica en modo desarrollo (FASE 90, spec 90-93); sin argumentos carga el proyecto de demostración |
| 10 | `09_GUI_COMPILADO.bat` | Abre la **interfaz gráfica del ejecutable compilado** (`ARQ_GEN.exe gui`) — no necesita Python instalado; es la forma recomendada de trabajar a diario |

**Variables opcionales:**
- `set ARQ_PY_EXE=C:\ruta\a\python.exe` — usar un intérprete concreto (ruta completa).
- `set ARQ_ALLOW_OTHER_PYTHON=1` — permitir un Python 3.x distinto de 3.13.
- `set ARQ_NOPAUSE=1` — desactiva las pausas de los .bat (para automatización).
- `set ARQGEN_DWG2DXF=C:\ruta\a\conversor.exe` — conversor DWG→DXF propio (se invoca
  `<exe> <entrada> <salida>`); si no existe la variable se buscan LibreDWG y ODA File Converter.

**DWG de entrada:** para importar planos `.dwg` instale una vez un conversor gratuito local
(ODA File Converter o LibreDWG `dwg2dxf`); ARQ GEN lo detecta solo, convierte a DXF temporal
y sigue el pipeline §94 normal. Sin conversor, el asistente se lo explica y no toca nada.

### Solución de problemas de los .bat (v1.6.4)

**Historial de incidencias resueltas:**

- *v1.6.0 y anteriores* — los .bat se distribuían con fin de línea de Unix (LF): **cmd.exe los abortaba de inmediato —la ventana se cerraba sin hacer nada— y no se creaba ningún log**.
- *v1.6.1* — los textos de error dentro de bloques `if (...)` incluían paréntesis literales, p. ej. `echo [ERROR] Etapa 1 (pruebas...) fallida`. En cmd.exe un `)` sin comillas **cierra el bloque aunque esté dentro del texto**: el pipeline de compilación abortaba justo tras las pruebas previas y **nunca llegaba a compilar** (la carpeta `logs\build\` quedaba vacía).
- *v1.6.2* — ambos defectos corregidos y **congelados por tests**: la suite verifica byte a byte CRLF/ASCII/sin BOM y **parsea los bloques de los 9 scripts** prohibiendo paréntesis literales dentro de ellos.
- *v1.6.3* — la compilación fallaba con `ERROR: Aborting build process due to attempt to collect multiple Qt bindings packages`. **Causa**: la librería ezdxf contiene un import perezoso de Qt (`ezdxf.npshapes` → `ezdxf.addons.xqt`) que PyInstaller detecta en su análisis estático; si en el equipo están instalados **PySide6 y PyQt5 a la vez** (típico en un Python global usado para otros proyectos), PyInstaller se niega a empaquetar ambos. **Solución**: `03_COMPILAR.bat` ahora excluye todos los bindings Qt (`--exclude-module PySide6/PyQt5/PyQt6/PySide2` + sus companions) — ARQ GEN usa Tkinter, no Qt — así que la compilación funciona **independientemente de lo que haya instalado en el equipo**. Verificado reproduciendo el entorno conflictivo (ambos bindings instalados).
- *v1.6.4* — «compila y funciona pero no aparece la interfaz»: el ejecutable es una app de consola; **la ventana gráfica siempre existió pero faltaba la ruta obvia para abrirla**. Desde esta versión: (1) **doble clic sobre `ARQ_GEN.exe` abre la ventana directamente**, (2) nuevo `09_GUI_COMPILADO.bat` que lanza la GUI sin Python, (3) `05_EJECUTAR_COMPILADO.bat` anuncia cómo abrir la GUI en su ayuda. La presencia real de Tkinter en el ejecutable queda verificada en la etapa 3 del pipeline (selftest con ventana Tk real).

**Garantías desde v1.6.4:**

- **La ventana ya no desaparece**: cualquier error queda en pantalla (`pause`) hasta pulsar una tecla.
- **Latido de arranque**: cada .bat escribe `INICIO`/`FIN` en `logs\bat_boot.log` nada más arrancar; si ese archivo no se crea, el script no llegó a ejecutarse (ZIP viejo o bloqueo de SmartScreen).
- **Detección de Python reforzada**: si falta `config\python_home.txt`, los .bat autodetectan el intérprete (`py -3.13` → `python3.13` → `py` → `python` → `python3`), lo normalizan a su **ruta completa** y lo validan (descarta el alias trampa de Microsoft Store y rutas rotas).
- **Rutas con espacios**: todo se invoca entre comillas (funciona con `C:\Program Files\Python313\python.exe`).
- **«Ejecutar como administrador»**: todos los scripts cambian primero al directorio del propio .bat (`cd /d "%~dp0"`).
- **04/05 sin argumentos** muestran la ayuda de la CLI en lugar de cerrarse solos.
- **La interfaz gráfica siempre alcanzable**: doble clic en el exe, `09_GUI_COMPILADO.bat` o `ARQ_GEN.exe gui`; y desde desarrollo con `08_GUI.bat`.
- **Automatización**: `set ARQ_NOPAUSE=1` desactiva las pausas; si PowerShell está bloqueado por política, la marca de tiempo de los logs usa un fallback interno.

Diagnóstico rápido si un .bat fallara:

1. Abra `logs\bat_boot.log`: si su `INICIO` no aparece, está ejecutando un ZIP antiguo — extraiga el ZIP actual en una carpeta nueva.
2. La ventana permanece abierta: lea el mensaje de error final.
3. Consulte el log de la etapa correspondiente en `logs\` (tabla de la sección 5).
4. Si Windows SmartScreen bloquea el script descargado: clic derecho sobre el .bat → **Propiedades** → casilla **Desbloquear** → Aceptar.
5. La integridad de los 10 .bat se verifica automáticamente: `02_PRUEBAS.bat` incluye 18 pruebas de integridad (CRLF, ASCII, BOM, pausas, paréntesis en bloques, latido, exclusión de bindings Qt, lanzador de GUI compilada) y el selftest la comprobación 27 «scripts .bat».
6. Si la compilación mostrara `multiple Qt bindings`, descargue el ZIP **1.6.3 o superior**: las exclusiones Qt van incluidas desde esa versión.

---

## 4. Primeros pasos con la CLI

```bat
06_DEMO.bat
05_EJECUTAR_COMPILADO.bat project info output\demo.arqgen
08_GUI.bat
```

Crear un proyecto desde cero:

```bat
04_EJECUTAR.bat project create proyectos\mi_obra.arqgen --name "Casa Demo" --client "Cliente" --ruleset international_v1
04_EJECUTAR.bat level add proyectos\mi_obra.arqgen --name "Nivel 1" --elevation 0 --height 3
04_EJECUTAR.bat space add proyectos\mi_obra.arqgen --level "Nivel 1" --name Sala --type LIVING_ROOM --polygon 0,0 6,0 6,5 0,5
04_EJECUTAR.bat wall add proyectos\mi_obra.arqgen --level "Nivel 1" --start 0,0 --end 6,0 --thickness 0.2
04_EJECUTAR.bat door add proyectos\mi_obra.arqgen --wall ARQ-WALL-001 --width 0.95 --height 2.10 --offset 1.0
04_EJECUTAR.bat relationships recompute proyectos\mi_obra.arqgen
04_EJECUTAR.bat validate proyectos\mi_obra.arqgen
04_EJECUTAR.bat qto compute proyectos\mi_obra.arqgen
04_EJECUTAR.bat resource add proyectos\mi_obra.arqgen --code BLOQUE-20 --name "Bloque 20" --type MATERIAL --unit und
04_EJECUTAR.bat price set proyectos\mi_obra.arqgen --resource BLOQUE-20 --price 32.50 --list GENERAL
04_EJECUTAR.bat budget compute proyectos\mi_obra.arqgen --template residential_full_v1
04_EJECUTAR.bat export proyectos\mi_obra.arqgen --format dxf --out planos\planta1.dxf
```

Instalaciones desde cero (red eléctrica de ejemplo):

```bat
04_EJECUTAR.bat net add proyectos\mi_obra.arqgen --name "Fuerza" --system POWER
04_EJECUTAR.bat node add proyectos\mi_obra.arqgen --network MEP-NETWORK-001 --kind PANEL --x 0.5 --y 0.5 --attr voltage=220 phases=1 main_breaker_a=63
04_EJECUTAR.bat node add proyectos\mi_obra.arqgen --network MEP-NETWORK-001 --kind PROTECTION --x 1 --y 0.5 --attr rating_a=16 kind_circuit=POWER
04_EJECUTAR.bat node add proyectos\mi_obra.arqgen --network MEP-NETWORK-001 --kind OUTLET --x 4 --y 3 --space ARQ-SPACE-001 --attr power_w=600
04_EJECUTAR.bat link add proyectos\mi_obra.arqgen --network MEP-NETWORK-001 --from MEP-NODE-001 --to MEP-NODE-002 --kind CONDUIT --attr conductors=3 spare_pct=10
04_EJECUTAR.bat link add proyectos\mi_obra.arqgen --network MEP-NETWORK-001 --from MEP-NODE-002 --to MEP-NODE-003 --kind CONDUIT --attr conductors=3 spare_pct=10
04_EJECUTAR.bat net validate proyectos\mi_obra.arqgen --network MEP-NETWORK-001
04_EJECUTAR.bat elec summary proyectos\mi_obra.arqgen --panel MEP-NODE-001
04_EJECUTAR.bat elec check proyectos\mi_obra.arqgen --circuit MEP-NODE-002
04_EJECUTAR.bat qto compute proyectos\mi_obra.arqgen   (las redes alimentan el cómputo)
```

Sanitaria y HVAC:

```bat
04_EJECUTAR.bat san size proyectos\mi_obra.arqgen --network MEP-NETWORK-002   (caudales, diámetros, bombeo)
04_EJECUTAR.bat hvac load proyectos\mi_obra.arqgen --space Sala               (carga térmica + equipo)
04_EJECUTAR.bat hvac loads proyectos\mi_obra.arqgen                            (tabla de los 4 locales)
04_EJECUTAR.bat hvac duct proyectos\mi_obra.arqgen --flow 800 --kind MAIN     (dimensionado puntual)
04_EJECUTAR.bat hvac size-network proyectos\mi_obra.arqgen --network MEP-NETWORK-004
```

### Interfaz gráfica (FASE 90, spec 90-93; editable desde v1.6.0)

Tres formas de abrirla:

- **Ejecutable compilado (recomendado)**: `09_GUI_COMPILADO.bat`, o doble clic sobre `dist\ARQ_GEN\ARQ_GEN.exe` — el exe sin argumentos abre la ventana directamente; no necesita Python.
- **Modo desarrollo**: `08_GUI.bat` o `python main.py gui [archivo] [--demo] [--width N --height N]`.
- **CLI**: `ARQ_GEN.exe gui [archivo] [--demo] [--width N --height N]`.

**Novedades v2.6.0 — CAPA DE REPRESENTACIÓN ARQUITECTÓNICA (cortes, elevaciones, detalles, tramas y columnas)**

- **Columnas según tipología constructiva** (`core/geometry/structural.py`): motor con 4 estrategias reales — malla de pórtico (hormigón monolítico 5,0 m · prefabricado 6,0 m · metálico 6,0 m · losa maciza 5,5 m), columnas de refuerzo/confinamiento (mampostería cada 4,8 m · piedra cada 5,0 m), pilares (madera · galvanizado cada 3,0 m) y autoportante sin columnas (panel sandwich · adobe/tapial). Columnas embutidas en ejes de muros, esquinas del envolvente, encuentros en T/L/cruce y **galería arcada en los patios** para pórticos; jamás caen dentro de un vano de ningún muro (chequeo global de todos los muros que pasan por el punto).
- **Tramas (hatch) por material** (`core/geometry/representation.py`): 8 patrones — mampostería (soga 45°), hormigón (áridos), madera (veta), piedra (sillares), tierra (trama densa), acero (sólido), panel y galvanizado — recortados matemáticamente dentro de cada muro; envolvente hatched y particiones en poché. En SVG se materializan como `<pattern>`.
- **Elevaciones**: las 4 fachadas cardinales con vanos proyectados (puertas y ventanas con parteluz), zócalo, líneas de nivel, **terreno escalonado por el desnivel**, remate según cubierta y alero discontinuo. La fachada principal se marca «(frente)».
- **Cortes transversal y longitudinal**: el transversal cruza el edificio de fachada a fachada por la escalera o el local mayor; el longitudinal va por el pasillo. Muestran zapatas y sobre-cimientos bajo cada muro cortado, losas escalonadas por el desnivel **con vanos reales sobre patios y el hueco de escalera** (el piso del arranque queda sólido), escalera en zigzag con contrahuella/huella, muros de fondo en proyección, cubierta plana (parapeto) / un agua / dos aguas según clima y estilo, y cotas verticales.
- **Detalles constructivos**: biblioteca de nodos por tipología (zapata corrida/aislada, viga collar, esquina confinada o nudo de pórtico, ventana con antepecho y dintel, puerta exterior, alero-cornisa, escalera) con esquema acotado y memoria descriptiva con las medidas reales del proyecto.
- **Selector de vistas en el paso 6** (GUI): Planta / Elevación / Corte / Detalles redibujan el lienzo, con **arcos de giro de puertas**, flecha de **norte** girada según la orientación de la fachada, **cotas totales** y **escala gráfica** en la planta; botón «⤓ SVG» exporta la vista activa (`exporters/view_exporter.py`), con las mismas primitivas que el lienzo.
- **Metadata y avisos**: bloque `representacion` (cubierta, estrategia de columnas, trama, vistas) en el edificio; línea nueva en el resumen; aviso de coherencia sistema estructural ↔ tipología constructiva.
- **Pruebas**: test_113_representacion.py con **50 pruebas nuevas** (tramas recortadas y deterministas, estrategias y dedupe de columnas, columnas fuera de vanos, galería arcada en el patio, 4 elevaciones con frente/lateral y terreno escalonado, cortes con cimentación/losas por nivel/vacío de escalera y patio abierto, biblioteca de detalles por tipología, SVG de las 4 vistas, metadata/resumen/avisos y GUI del selector) — **802 pruebas** en verde y **selftest con check 39**.

**Novedades v2.5.0 — FORMA COMPUESTA + PATIO CENTRAL COMBINADOS y NÚCLEO RÍGIDO EN ESQUINAS (pulido del motor)**

- **Cinco esquemas nuevos «forma compuesta + patio central»**: el motor pasa de 9 a **14 esquemas × espejo = hasta 28 variantes** — **En L con patio abrazado** (la esquina interior se vuelve patio pegado al pasillo y al ala), **En T con patio central** (la espina de circulación se sustituye por un patio que iluminan las dos alas, y la entrada llega por el patio), **En H con patio central**, **En cruz con patio central** (los brazos nacen del patio) y **Articulada con patio central** (el eslabón se vuelve patio). En H/cruz/articulada el patio **se come las bandas de pasillo frente a él**: los locales de ambas barras dan la puerta **directamente a su galería**; si el patio llega hasta la fachada, la entrada principal se abre por el patio. Las afinidades forma↔esquema y la tabla climática heredan la respuesta tropical del patio.
- **Núcleo rígido en esquinas**: nuevo combo del paso 1 **NÚCLEO RÍGIDO EN ESQUINAS** (Automática / Sí, siempre / No) — la caja de **escalera + baños + ductos entre muros estructurales** (3,0 × 4,2 m, tipo CORE) se coloca en la **esquina frontal** de cada planta (en la L remata el ala, siempre en la envolvente), como las escaleras: automática en edificios de varios niveles o con desnivel, forzable o vetable con aviso amable si se veta siendo recomendable. Su metadata registra contenido y condición estructural (`nucleo_rigido: true`), y el resumen del paso 7 lo cuenta por nivel.
- **Puertas sin duplicados y con nombre fiel**: el ensamblado común recuerda las paredes ya perforadas (misma pared = una sola puerta) y la puerta al patio se nombra «→ galería del patio» desde el primer reparto; nada cambia para los esquemas anteriores salvo eliminar vanos repetidos.
- **Pruebas**: test_112_nucleo_patios.py con **20 pruebas nuevas** (catálogo de 14 esquemas, patio con galería en H/cruz/T/L/articulada sin solapes, determinismo, barrido multi-uso con desnivel, decisión automática/siempre/nunca del núcleo, validación, esquina en la envolvente en 11 esquemas, metadata/resumen/avisos, plan clásico con núcleo) — **752 pruebas** en verde y **selftest con check 38**.

**Novedades v2.4.0 — PATIOS EN LAS ALAS, ALEROS DIBUJADOS y MÁS ESTILOS/RELACIONES POR USO**

- **Patios en las alas (refinamiento de las formas)**: las alas largas de las formas **En L, En T, En U y En cruz** ahora ganan un **patio interior** (pozo de luz habitable de ≥ 2 × 2 m) intercalado por la mitad de la pila de locales, siempre con al menos un local a cada lado y la espina/pasillo alargado para cubrirlo. Cada local pegado al patio recibe su **puerta a la galería del patio** y los locales que quedan al otro lado quedan conectados por él (nada de locales aislados). El hospital en cruz saca DOS patios (izquierda y derecha); el patio entra a la puntuación como espacio abierto, igual que el patio central.
- **Aleros dibujados**: el contorno exterior del edificio se calcula de verdad (unión de los rectángulos, `exposed_outline_segments` en core.geometry) y el **alero del paso 5 se dibuja** como línea discontinua ámbar alrededor de la planta en la **vista previa de variantes** (con leyenda «– – – alero 0,60 m»), siempre con la protección solar activada. El **exportador SVG** también lo dibuja leyendo el alero del metadata del edificio (clase `.alero`, degradación amable: si un nivel tiene locales no rectangulares se omite su alero). El trazado se **recorta contra los volúmenes**: en esquinas cóncavas o entre alas próximas la línea muere en el muro y nunca atraviesa el edificio.
- **Estilos arquitectónicos ampliados a 14**: se suman **High-tech**, **Orgánico**, **Posmoderno** y **Sostenible (bioclimático)**, cada uno con su consejo de composición y su **forma en planta preferida** (`STYLE_SHAPE_PREFERENCE`): si eliges Colonial cubano con planta rectangular, el asistente sugiere con amabilidad la forma que luce mejor con ese estilo.
- **Estilo sugerido por uso social**: nuevo `suggested_architectural_style` — Hospital → High-tech, Escuela → Racionalista, Comercio → Art déco, Círculo infantil → Orgánico, Centro comunitario → Posmoderno… El botón «✨ Sugerir según el uso social» fija el estilo **solo si no elegiste uno propio**, igual que la forma.
- **Más relaciones por uso**: `USAGE_DOOR_PAIRS` llega a **todos los usos institucionales** — aulas–baño (escuela y círculo), comedor–cocina (círculo, comedor social y albergue), dormitorio–baño, entrada–sala multiuso, ventas–depósito, consultorio–baño…; y el hospital suma quirófano–enfermería, sala–estar, laboratorio–depósito y farmacia–depósito. Nuevas **adyacencias extra por uso** (`USAGE_EXTRA_PAIRS`) que encadenan lo que el DNA no une solo: aulas en cadena, salas de hospitalización contiguas (WARD–WARD), laboratorio–farmacia, sala multiuso–vestíbulo. Los locales sin DNA (el área de ventas ROOM) ya participan de los pares extra. La Vivienda se queda como siempre: relaciones sin puertas críticas sugeridas.
- **Pruebas**: test_111_patios_alas_aleros.py con **27 pruebas nuevas** (estilos y sugerencia por uso, coherencia estilo↔forma, puertas críticas ampliadas y pares extra, patios de ala en L/T/U/cruz con galería y sin solapes/aislados en el barrido completo de los 11 usos, contorno y alero sin atravesar el edificio, SVG con y sin alero, GUI con aleros y estilo sugerido) — **732 pruebas** en verde y **selftest con check 37** de patios/aleros/estilos/relaciones.

**Novedades v2.3.0 — FORMAS EN PLANTA, ESTILOS, TERRENO CON DESNIVEL y ESCALERAS (la edificación cobra forma)**

- **Paso 1 · Forma en planta (10 formas sugeridas por el uso social)**: nuevo combo **FORMA EN PLANTA** — Rectangular, Cuadrada, Lineal (barra), **En L, En T, En U, En H, En cruz**, **Patio central** y **Articulada (eslabones)** — con descripción de cada una y **sugerencia automática según el uso social** (el Hospital sugiere «En H», la escuela «Articulada», el centro comunitario «Patio central»); el botón «✨ Sugerir según el uso social» ahora también fija la forma.
- **Paso 6 · El motor de variantes crece a 9 ESQUEMAS × espejo = hasta 18 variantes**: las formas en L, T, U, H, cruz y articulada se **trazan de verdad** (barras de locales unidas por pasillos: ala perpendicular, espina central con locales a los lados, alas que abrazan patio trasero, doble barra con puente, brazos cruzados en el núcleo y bloques unidos por eslabón) con el mismo rigor de siempre — muros fusionados, puerta a cada local (locales profundos de las alas conectados **en enfilada**), entrada principal y ventanas en el primer borde exterior donde quepan. Nueva métrica **«Forma elegida»** (20 % de la puntuación): la forma que elegiste puntúa al máximo sin excluir las demás variantes.
- **Paso 1 · Estilos arquitectónicos (10 estilos con consejos)**: Contemporáneo, **Colonial cubano**, **Vernáculo tropical**, Racionalista, Art déco, Neoclásico, Modernista, Minimalista, Brutalista y Ecléctico — cada estilo activa avisos de composición (el colonial pide patio y aleros generosos; el vernáculo pide ventilación cruzada) que se suman al resumen del paso 7.
- **Paso 1 · Orientación a los OCHO puntos cardinales**: la fachada principal ya no se limita a los cuatro cardinales — Noreste, Sureste, Suroeste y Noroeste se suman, con avisos bioclimáticos (fachada al poniente en clima cálido pide aleros profundos o porche; al norte en clima frío, reserva las fachadas soleadas para los locales de uso).
- **Paso 1 · Terreno regular o irregular CON DESNIVEL REAL**: nuevo combo de **TERRENO** — Regular (plano), Irregular con ligera pendiente (**0,75 m**) o pendiente fuerte (**1,50 m**) — la pendiente **obliga a resolver diferentes niveles de piso dentro de una misma planta**: la zona trasera sube a su cota, cada local guarda su **cota_piso_m** en los requerimientos, y el resumen lo explica («Por la pendiente del terreno, N local(es) quedan a la cota +1,50 m»).
- **Escaleras automáticas (STAIR)**: nuevo combo **ESCALERAS** (Automática / Siempre / No) — la escalera se coloca **sola** entre niveles (edificio de dos o más pisos) y dentro de la planta para salvar el desnivel del terreno, con geometría de obra: contrahuella 17,5 cm, huella 28 cm, desarrollo limitado a 2,4–4,8 m, y su metadata registra **escalones estimados y desarrollo**. Si las vetas pero hacen falta, el asistente avisa antes de generar.
- **Tipologías constructivas ampliadas a 10**: se suman Losa maciza de hormigón, Estructura metálica (acero), Muros de piedra, Tierra (adobe o tapial) y Estructura ligera de acero galvanizado + panel.
- **Pruebas**: test_110_formas_estilos_terreno.py con **44 pruebas nuevas** (catálogos, validación de los 4 campos, geometría de escalera, desnivel con cota por local, trazado real de las 6 formas nuevas sin solapes ni locales aislados, métrica «Forma elegida», metadata/resumen/avisos de sitio, plan con escalera y GUI del paso 1) — **705 pruebas** en verde y **selftest con check 36** de formas/estilos/terreno/escaleras.

**Novedades v2.2.0 — TEMA HOSPITALARIO (la red de salud completa en el asistente)**

- **Paso 1 · Dos usos sociales nuevos de salud**: **Policlínico** y **Hospital** se suman al combo de usos, con su texto orientador propio (urgencias junto a imagenología y laboratorio, quirófanos en cadena con esterilización, salas de hospitalización junto a su estación de enfermería).
- **Space DNA extendido a 22 tipos con los locales de salud**: Urgencias / triage (≥ 18 m², acceso de ambulancia), **Quirófano** (≥ 36 m², climatización mecánica con presión positiva y 20 cambios de aire/hora, oxígeno medicinal), Esterilización (extracción forzada), Sala de hospitalización (≥ 28 m², 4 camas), Estación de enfermería, Laboratorio clínico, Sala de imagenología (barrera plomada) y Farmacia. Fix de fondo: `SpaceDNA.from_dict` ahora **conserva la clave `metadata` del JSON** (se fusiona con las claves desconocidas, antes se perdía).
- **Programa MULTI-NIVEL del hospital (LEVEL_PROGRAMS)**: «✨ Sugerir según el uso social» con Hospital reparte 20 locales en 3 niveles — PB accesos/urgencias/farmacia/laboratorio/rayos X, P1 quirófanos + esterilización central + URPA, P2 dos salas de hospitalización + enfermería + sala de estar — y **crea los niveles que faltan** (3,2 m de altura para el plenum de A/C) sin renombrar ni tocar los tuyos; si ya tienes 3 niveles los usa tal cual.
- **Puertas críticas por uso (USAGE_DOOR_PAIRS)**: las relaciones sugeridas ahora llevan PUERTA cuando el par lo pide el uso — quirófano–esterilización, urgencias–rayos X, urgencias–laboratorio, espera–urgencias, espera–farmacia, sala–enfermería, sala–baño, enfermería–carrito de curas. (Fix latente de fondo: las puertas declaradas entre locales consecutivos en la variante de doble crujía/patio ya no rompen el motor de variantes.)
- **Módulos de instalaciones sugeridos por uso**: botón «✨ Sugerir módulos del uso social» en el paso bioclimático — Hospital/Policlínico marcan Eléctrica, Sanitaria, **A/C**, Incendios, Comunicaciones y **Gas (oxígeno medicinal)**.
- **Avisos técnicos hospitalarios sin bloquear**: si hay quirófano y falta A/C, se avisa «activa el módulo Ventilación mecánica / A/C»; lo mismo con oxígeno medicinal (Gas) y radiación (barrera plomada en rayos X). Los requerimientos quedan en el metadata de cada objeto (aire_acondicionado, presion_requerida, oxigeno_medicinal, proteccion_radiologica).
- **Botón «Programa: Policlínico»** en el paso 3 para partir del programa de salud en un nivel con un clic; el mensaje de «Sugerir según el uso social» ahora informa los niveles cargados y refresca combos de nivel y de relaciones.
- **Pruebas**: test_109_hospital.py con 26 pruebas nuevas (usos, programa multi-nivel, DNA, puertas críticas, instalaciones, avisos, validación, trazado en 3 niveles, 6 variantes y resumen) — **661 pruebas** en verde y **selftest con check 35** del tema hospitalario.

**Novedades v2.1.0 — asistente de GENERACIÓN de edificaciones (el flujo que pediste, completo)**

- **Paso 1 · Datos**: además del nombre y el clima, el asistente pide el **USO SOCIAL** (Vivienda, Oficina, Escuela primaria, Círculo infantil, Consultorio médico, Comedor social, Centro comunitario, Albergue, Local comercial), las **dimensiones máximas** de la edificación (ancho y fondo; 0 = sin límite) y la **tipología constructiva** (mampostería de bloque + losa, hormigón, prefabricado, madera, panel).
- **Paso 3 · Locales sugeridos por el uso social**: botón «✨ Sugerir según el uso social» que carga el programa típico del uso elegido (aulas en la escuela, sala de espera + consultorios en el consultorio, dormitorios alrededor del baño común en el albergue…) y sus **relaciones espaciales sugeridas** desde el Space DNA (extendido a 13 tipos: CLASSROOM, CONSULTATION_ROOM, WAITING_ROOM, MULTIUSE_HALL).
- **Paso 5 · Bioclimática e instalaciones**: ventilación cruzada, protección solar con **aleros** configurables y 7 módulos de instalaciones seleccionables (Eléctrica, Sanitaria, Ventilación mecánica / A/C, Protección contra incendios, Comunicaciones, Gas, Energía solar) — todo queda guardado en el metadata de la edificación.
- **Paso 6 · Elige la variante de planta (LO NUEVO)**: el motor genera **6 variantes de planta** — lineal con pasillo posterior, doble crujía con pasillo central y patio central, cada una con su espejo — traza niveles, muros fusionados, puerta a cada local, entrada principal y ventanas en los dos frentes, y PUNTÚA cada variante (0–100) con métricas explicables: adyacencias satisfechas, luz natural, compacidad, ventilación cruzada y afinidad al clima. Las variantes que no caben en tus dimensiones se marcan «No cabe: necesita X × Y m» y quedan al final. **Preview dibujado en el lienzo** (locales coloreados por tipo, patio/pasillo diferenciados, puertas en naranja y ventanas en azul) y descripción con métricas por variante.
- **Paso 7 · Resumen**: menciona la variante elegida con su puntuación, la tipología constructiva, las dimensiones, la bioclimática y las instalaciones antes de generar.
- La generación sigue siendo 100% auditada y deshacible (CommandBus §76, auditoría §71 y eventos §75): edificio, niveles, locales, muros, puertas, ventanas y relaciones llevan los requerimientos completos en su metadata, incluida la variante de planta elegida.
- **635 pruebas** (+33 nuevas: usos sociales y DNA extendido, validación de dimensiones/tipología/aleros/instalaciones, motor de variantes — doble crujía con dos filas y pasillo central, patio habitable, espejos, métricas acotadas, ajuste al lote —, plan/apply con variante y resumen) y **selftest con check 34** del asistente v2.1.0.

**Novedades v2.0.0 — EL SALTO: el catálogo real se convierte en dinero**

- **Motor PRECONS con análisis de precio oficial directo**: los 15981 renglones del catálogo real (RoPres 3.30) ahora se analizan de verdad — `price_analysis` detecta renglones con desglose oficial CUP (sin composición de recursos) y calcula materiales, mano de obra, equipos, transporte, indirectos y beneficio por unidad, cumpliendo siempre `total = unit_price × cantidad`. Antes cualquier análisis sobre el catálogo real devolvía 0.00; hoy `precons analyze --item 011111 --quantity 100` devuelve 2 681,00 CUP.
- **💰 Presupuesto por catálogo PRECONS III (Herramientas ▸ Presupuesto con catálogo PRECONS III)**: nuevo servicio `PreconsBudgetService` con persistencia en el proyecto (tablas estándar de presupuesto): alta/acumulación de renglones por código, fijado de cantidades, quitar/vaciar, capítulos automáticos por sección del catálogo (38 secciones), subtotales por sección, totales con coeficientes de la ruleset (transporte sobre materiales, indirectos y beneficio) y desglose oficial resuelto siempre desde el catálogo (fuente única de verdad). Convive sin conflicto con el presupuesto de plantilla del demo. Nuevo botón **«Añadir al presupuesto →»** en el navegador del catálogo: de la búsqueda al presupuesto en un toque.
- **CLI `precons budget`**: `precons budget <proyecto> --add 011111:500 --add 020112:2 --show --export-csv b.csv --export-pdf b.pdf --chart-png b.png` — presupuesto punta a punta con precios oficiales CUP y exportación triple en un comando.
- **📄 Exportador PDF 100% stdlib (brecha #4 cerrada)**: PDF 1.4 válido sin dependencias — fuentes base Helvetica (WinAnsi con acentos y ñ), tablas con cabecera repetida y salto de página automático con marco por página, presupuesto por secciones y análisis de precio unitario. La GUI exporta el presupuesto a PDF con dos toques.
- **🗺️ Exportador SVG 100% stdlib (brecha #4 cerrada)**: plano del proyecto en SVG escalable (muros con contorno real, vanos con arco de puerta, locales con nombre y área, una capa por nivel, unidades en metros) — registrado también como formato `export SVG` del ExportService y del menú Archivo ▸ Exportar. Validación XML incluida.
- **📊 Exportador PNG 100% stdlib (brecha #4 cerrada)**: gráfico de barras del presupuesto por sección con fuente bitmap 5×7 embebida, formato español de miles, compresión zlib y contenedores IHDR/IDAT/IEND escritos a mano — sin Pillow ni matplotlib.
- **🧭 Asistente de importación §94 en la GUI (brecha #2 cerrada)**: Herramientas ▸ Importar catálogo de precios — elige un XLSX/CSV/JSON externo, ARQ GEN analiza hojas/columnas en un hilo de fondo con barra de progreso, muestra conteos/avisos/errores del informe y aplica el catálogo como ruleset instalado listo para el presupuesto y la CLI (`--ruleset <código>`).
- **Fix en el importador §94**: hojas planas con columna única código/partida ya no fallan con KeyError al resolver roles de columnas.
- **602 pruebas** (+30 nuevas: análisis oficial, presupuesto persistente, PDF/SVG/PNG válidos, flujo del asistente y comando budget) y **selftest extendido** con el check integral del salto v2.0.0.

**Novedades v1.9.1 — importador nativo del libro oficial PRECONS III:**

- **`importar catalogo` entiende el libro oficial RoPres sin mapeo**: el pipeline §94 detecta el shape «precons» (hojas PORTADA, SECCIONES, RENGLONES_PRECONS, MATERIALES, EQUIPOS, MANO_OBRA, PARAMETROS, LIMITES, INSTRUCCIONES) y convierte el XLSX completo en ruleset versionado en un paso — jerarquía sección/capítulo/subcapítulo, desglose oficial CUP, precios y pesos de recursos, parámetros, límites e instrucciones como datos.
- **Auditoría integrada de la importación**: lectura de los conteos declarados en la PORTADA y contraste con lo importado (renglones, materiales, equipos, mano de obra), conteo por sección contra la hoja SECCIONES, deduplicación de renglones y carga estructural validada con PreconsRuleset — todo avisado en el informe del preview.
- **Metadatos de trazabilidad automáticos**: versión RoPres y fecha de generación se extraen de la PORTADA y quedan en `source`/`generated` del ruleset.
- **Certificación 1:1 contra el libro oficial**: el ruleset embebido `precons_iii_rospres_330` fue verificado campo a campo contra el XLSX (15981 renglones + 4383 recursos: código, nombre, unidad, sección, capítulo, subcapítulo, 4 precios, peso) — 100% coincidente, y además corrige 77 descripciones vacías del libro oficial con los nombres del backend RoPres original. La suite incluye una prueba que re-importa el libro completo y valida conteos y metadatos.

**Novedades v1.9.0 — catálogo PRECONS III real completo:**

- **El catálogo oficial completo vive dentro del programa**: los 15981 renglones de listas de costos y los 4383 recursos oficiales (3569 materiales, 671 equipos, 143 mano de obra) del PRECONS III (RoPres 3.30, generado 2026-09-24) están embebidos como ruleset versionado `precons_iii_rospres_330` (datos JSON, espec 59) — sin internet, sin importar nada. Cada renglón lleva su jerarquía (sección, capítulo, subcapítulo), unidad, desglose oficial CUP (materiales / mano de obra / equipos / total) y los 8 parámetros de referencia y 4 límites normativos (Res. 29/2020 MTSS) como datos.
- **📊 Navegador del catálogo (Herramientas ▸ Catálogo PRECONS III)**: busca cualquier renglón por código o descripción (sin acentos ni mayúsculas), filtra por las 38 secciones (movimiento de tierra, cimentaciones, revestimientos, pinturas…), y al seleccionar un renglón ves su precio oficial unitario con desglose. Escribe la cantidad y calcula el importe al instante (formato español: 26 481,00 CUP).
- **CLI nueva**: `precons precio <proyecto> --item 011111 --quantity 100` (precio oficial × cantidad, con desglose) y `precons list` con `--seccion`, `--buscar` y `--limite` (cap por defecto en 50 filas para catálogos grandes).
- **Motor listo para catálogos de 10k+ renglones**: índices de acceso O(1) (la primera carga tarda ~2 s, cada consulta posterior es instantánea), contexto de error acotado (lista 15 códigos, no 15981), y campos nuevos de trazabilidad (fecha de generación, fuentes, instrucciones, parámetros y límites).
- El ruleset demo `precons_cuba_v1` sigue intacto para el flujo analítico con QTO; el catálogo real se consulta por navegación, CLI o análisis de precios oficiales.

**Novedades v1.8.0 — asistente de EDIFICACIÓN completa:**

- **🏠 Asistente de edificación (primer botón de la barra + Herramientas ▸ Asistente de edificación)**: en 5 pasos te levanta un edificio entero: 1) datos generales (nombre, clima del lugar, sistema estructural, orientación de la fachada y notas); 2) niveles con alturas libres (la cota se calcula sola); 3) locales con tipo, ancho, fondo, nivel y ventana — o carga un **programa tipo** (Vivienda u Oficina) con un clic y ajusta; 4) relaciones espaciales entre locales (adyacente, comunicado, separada acústicamente… con o sin puerta) más puertas, ventanas, espesor y pasillo; 5) resumen revisable con avisos del conocimiento técnico antes de generar.
- **Trazado automático inteligente**: los locales quedan en fila con particiones compartidas y el pasillo corre por detrás de la fachada conectando TODOS los locales (cada uno con su puerta), con entrada principal. Si no quieres pasillo, la entrada va al primer local y el resto se comunican en enfilada. Los locales declarados como relacionados se colocan consecutivos para que su puerta tenga pared donde apoyarse.
- **Una pared compartida = UN muro**: los muros se fusionan por eje, así que las particiones no se cuentan dos veces (cantidades honestas). Con «Muros portantes» o «Mixto», los muros de fachada y de pasillo quedan marcados como estructurales; las particiones entre locales, no. Con «Pórtico», ninguno.
- **Requerimientos guardados en cada objeto**: el clima, la ventilación cruzada, el sistema estructural, el área mínima y el ancho mínimo del tipo de local (conocimiento Space DNA ampliado a 9 tipos: Comedor, Entrada/Hall y Depósito nuevos), la accesibilidad, la zona húmeda y tus notas quedan en el metadata del edificio, de cada local, de cada muro y de cada vano. Exportan con el proyecto (JSON/IFC) y se consultan desde el panel de propiedades.
- **Avisos que orientan sin bloquear**: si un local queda por debajo del área mínima sugerida para su tipo, si es zona húmeda (agua, desagüe, ventilación) o si una puerta declarada no puede colocarse, el asistente te lo dice en el resumen — y no te impide generar.
- **Sugerencias del conocimiento técnico**: el botón «Sugerir del conocimiento técnico» del paso 4 propone relaciones de adyacencia según el tipo de cada local (Sala–Cocina, Dormitorio–Baño…) tomadas del DNA.
- Todo por las mismas fachadas oficiales: CommandBus, auditoría `CREATE_ENTITY`/`UPDATE_ENTITY`, eventos, undo con `Ctrl+Z` y niveles reutilizados si ya existen (puedes generar bloques anexos sobre la misma planta).

**Novedades v1.7.2 — asistente dinámico de diseño y español completo:**

- **Corregido (importante): el desplegable de nivel vuelve a listar tus niveles**. Al crear un muro, local o elemento, el formulario partía la palabra interna «levels» en letras sueltas y por eso nunca aparecían los niveles que habías creado. Ahora las opciones dinámicas (niveles, muros, redes) se consultan SIEMPRE en el momento de abrir el formulario: crea un nivel y ábrelo al instante.
- **✨ Asistente de local (botón destacado + Herramientas ▸ Asistente de diseño)**: te pide los datos paso a paso y va armando tu local: 1) nivel (o crea uno nuevo ahí mismo), nombre y tipo; 2) ancho, fondo, esquina y espesor (acepta coma decimal: «3,5»); 3) puerta y ventana con sus lados; 4) resumen revisable. Al crear, deja el local dibujado con sus 4 muros y los vanos centrados, con auditoría y undo igual que cualquier otra creación.
- **Interfaz 100% en español**: los estados del ciclo de vida se muestran como «Borrador (DRAFT)», «Activo (ACTIVE)»…; el diario (pestaña «Registro») cuenta «Objeto creado (OBJECT_CREATED)»; y la tabla de cálculos muestra «Cantidades (QTO)» y «Presupuesto». Los valores internos del spec se conservan para trazabilidad.
- **Validación amable del asistente**: los mensajes hablan en primera persona («necesito un nombre para el local», «la puerta no cabe en el muro Frente (3,00 m)») y bloquean el avance solo cuando falta algo esencial.

**Novedades v1.7.1 — interfaz guiada y tema oscuro:**

- **Tema oscuro moderno con letras claras**: paleta centralizada en `ui/theme.py` (fondo profundo, paneles en capas, acento azul amable, lienzo con rejilla y colores de entidades ajustados para contrastar). Todos los widgets ttk, menús, treeviews, pestañas y scrollbars comparten el mismo lenguaje visual.
- **Ayuda dinámica en cada control**: al detener el cursor sobre cualquier botón, campo o panel aparece un globo de ayuda con una explicación breve Y la misma frase se fija en la barra de estado inferior. Al abrir cualquier menú superior (Archivo, Editar, Ver, Herramientas, Ayuda), la barra de estado explica para qué sirve.
- **Flujo no abrumador**: la barra de estado sugiere siempre el siguiente paso natural (crear el primer local → muros → puertas → calcular → validar → exportar) según el estado real del proyecto. La interfaz habla en tono cercano: «¿Fue un error? Ctrl+Z lo recupera al instante», «Validación limpia: todo en orden».
- **Guía rápida (F1 o botón «Guía rápida»)**: recorrido de 4 pasos que explica la pantalla entera en lenguaje sencillo.
- **Panel de bienvenida**: un proyecto vacío ya no es un lienzo en blanco: muestra una tarjeta con los 4 pasos y la invitación a cargar el proyecto de demostración.
- **Formularios con ayuda por campo**: cada campo de creación y edición muestra su explicación («Espesor del muro en metros (0.2 = 20 cm)»), y los obligatorios están marcados con *.
- **Barra de estado con dos canales**: a la izquierda la orientación dinámica (mensajes y ayudas), a la derecha los datos técnicos (proyecto · disciplina · objetos en el plano) y las coordenadas de mundo bajo el cursor.

Funcionalidad consolidada:

- **Ventana §90**: menú · barra de herramientas (con «🏠 Asistente de edificación» primero y «✨ Asistente de local» al lado) · explorador | lienzo | propiedades · pestañas Avisos/Registro/Estado de cálculos + barra de estado con coordenadas de mundo en metros bajo el cursor.
- **Navegación §91**: las 13 disciplinas; filtro por nivel para Arquitectura.
- **Buscador §92**: los 9 campos del spec; `Enter` busca, `Escape` limpia, `Ctrl+F` salta al buscador.
- **Estados §93**: cambio de estado con transiciones validadas, auditoría y evento.
- **Edición (v1.6.0)**: doble clic en una fila editable (marcada con ✎) o botón «Editar propiedad…» (`Ctrl+E`) modifica campos en lista blanca por tipo (locales, muros, vanos, nodos, materiales, secciones, elementos…). Cada edición audita `UPDATE_ENTITY` con snapshots completos y es reversible con `Ctrl+Z`.
- **Creación (v1.6.0)**: «Nuevo objeto…» abre formularios declarativos por tipo (local, muro, puerta, ventana, nivel, zona, material, sección, elemento, red, nodo), con desplegables dinámicos que se refrescan al abrir (niveles, muros, redes, sistemas — v1.7.2) y por las mismas fachadas que la CLI.
- **Borrado (v1.6.0)**: tecla `Supr` o menú Editar → «Eliminar selección», con confirmación, cascadas (muro→vanos, nodo→tramos, red→todo) y undo persistente.
- **Lienzo**: zoom anclado al cursor con la rueda, desplazamiento con botón central o derecho, clic para seleccionar, doble clic en vacío para encuadrar (`F`), cuadrícula adaptativa de 1/5/25 m.
- **Atajos**: `Ctrl+N/O/S`, `Ctrl+Z/Y`, `Ctrl+F`, `Ctrl+E`, `Supr`, `+`/`−`, `F`, `Escape`, `F1` (**guía rápida**; listados en Ayuda → Atajos de teclado).
- **Herramientas**: validación, recálculo de QTO/presupuesto, «Recalcular todo», e informe del proyecto en Markdown.

### Importación de archivos externos (spec 94, v1.7.0)

El pipeline completo de 9 etapas ya no se limita a instantáneas JSON. Dos puertas de entrada nuevas:

- **Catálogo PRECONS → ruleset** (sin proyecto abierto):

  ```bat
  python main.py importar catalogo Catalogo_PRECONS_III_Completo.xlsx
  python main.py importar catalogo Catalogo_PRECONS_III_Completo.xlsx --code PRECONS_III --out resources\rulesets\precons_iii.json
  ```

  Detecta automáticamente hojas (PARTIDAS/RECURSOS/RENDIMIENTOS/PRECIOS) y columnas por sinónimos (Código, Descripción, UM, Insumo, Rendimiento, Merma…); entiende el formato plano (una fila por partida+insumo) y el multi-hoja. Si el autodetect falla, pase un mapa JSON con `--mapping` (claves `items_sheet`, `resources_sheet`, `indicators_sheet`, `prices_sheet`, `columns`). Sin `--out` solo muestra el PREVIEW; los precios detectados se reportan (se cargan al proyecto con `price set`).
- **DXF → muros y locales** (proyecto abierto):

  ```bat
  python main.py importar dxf plano.dxf --file proyecto.arqgen --nivel PLANTA_1
  python main.py importar dxf plano.dxf --file proyecto.arqgen --nivel PLANTA_1 --aplicar
  ```

  LINE en capas de muro (`muro`/`wall`) → muros; LWPOLYLINE cerrada en capas de local (`local`/`space`/`hab`/`ambiente`) → locales (el nombre sale del TEXT/MTEXT contenido dentro, o `LOCAL-001`); capas explícitas con `--capa-muros`/`--capa-locales`; espesor uniforme con `--espesor`. Sin `--aplicar` es solo PREVIEW (ninguna entidad se crea).

### Referencia de comandos

`project create|info` · `level add|list` · `zone add|list` · `space add|list` · `wall add|list|move` · `door add|list` · `window add|list` · `undo` · `redo` · `relationships recompute|report` · `validate` · `qto compute|show` · `resource add|list` · `price set|history` · `budget compute|show` · `export --format dxf|json|xlsx|csv|ifc|svg` · `import [--approve]` · `importar catalogo|dxf|dwg` · `version save|list|restore|compare|export|branch` · `backup create|list|restore|autosave|incremental|journal|checkpoint|verify|recover` · `audit show|stats|export` · `events show` · `net add|list|show|trace|path|validate|deadends` · `node add|list|move` · `link add|list|remove` · `elec check|summary|balance` · `san size` · `hvac load|loads|duct|size-network` · `plu size` · `gas size|check` · `tel size` · `struct material-add|section-add|element-add|element-list|element-delete|case-add|combo-add|defaults|analyze|truss|connection-check|report` · `sec net|device-add|coverage|network|cabling|fire-check|cause-effect|intrusion-check|access-check|perimeter-check|bom` · `clash run|list|status` · `precons list|precio|analyze|project|compare|import|budget` · `detalles regiones|list|ver|svg|pdf|png|tipologia` · `bim tree|show` · `docs variables|memoria|tecnica|specs|cuadros|listados|informe|module|drawing-add|drawing-list|drawing-delete|template-add|template-render` · `optimize current|pareto|compare` · `plugins validate|info|new` · `benchmark run|caches` · `gui [archivo] [--demo]` · `demo` · `selftest`

Cualquier comando con errores controlados muestra `ERROR [código] mensaje` + sugerencia y devuelve código 1 (útil para automatizar). Los errores inesperados quedan con detalle completo en `logs\app\errors.log`.

---

## 5. Dónde están los registros (logs)

| Ruta | Contenido |
|---|---|
| `logs\bat_boot.log` | **Latido de arranque**: una línea `INICIO`/`FIN` por cada ejecución de cualquier .bat. Si este archivo no aparece, el script ni siquiera llegó a arrancar (archivos viejos o bloqueo de SmartScreen) |
| `logs\setup\env_*.log` | Verificación del entorno (errores de detección de Python) |
| `logs\setup\install_*.log` | Instalación de dependencias (errores de pip) |
| `logs\tests\pre_build_*.log` | Pruebas **antes** de compilar |
| `logs\build\build_*.log` | Compilación PyInstaller (errores **durante**) |
| `logs\tests\post_build_*.log` | Selftest del ejecutable **después** de compilar |
| `logs\tests\run_*.log` | Ejecuciones de la suite con `02_PRUEBAS.bat` |
| `logs\app\arqgen.log` | Log rotativo de ejecución (DEBUG) |
| `logs\app\errors.log` | Solo errores (ERROR/CRITICAL) de ejecución |

---

## 6. Estructura del código

```
ARQ_GEN/
├── main.py                  Punto de entrada
├── app/                     bootstrap, ciclo de vida, logging, CLI, demo, selftest, undo persistente
├── core/                    entidades, ids, unidades, geometría, eventos, comandos, reglas,
│                            validación, grafos, cálculos, auditoría, versionado, permisos,
│                            consola segura para Windows (v3.13.1)
├── domain/                  modelo semántico único + instalaciones + estructura + clash + Space DNA (conocimiento)
│                           + diseño de espacios: mobiliario, cubiertas, accesibilidad (v3.15.0)
+ teclado/puntero AutoCAD + editor de locales: keymap, cursor_acad, editor_espacios (v3.16.0)
├── services/                ProjectService, ArchitectureService, InstallationsService, Security, Coordination,
│                            Structure, Precons, BIM, Analysis (reglas/validación/espacial), Quantity (QTO),
│                            Pricing, Budget, Version, Import, Export, contexto y contenedor DI
├── engines/                 quantity (QTO), pricing, budget, spatial, network (§25), routing (§26),
│                            electrical (§27), sanitary (§28), hvac (§29), stormwater (§30), gas (§31),
│                            telecom (§32), structure (§34), fov (§39), cctv (§41-42), fire (§43-44),
│                            intrusion (§45), access (§46), perimeter (§47), clash (§36), precons (§59-60)
├── persistence/             sqlite (conexión), migraciones reversibles (7), repositorios, backup
├── importers/               Importadores spec §94: tablas (xlsx/csv), catálogo PRECONS (autodetección + mapa), DXF→muros/locales, pasarela DWG→DXF + IFC de entrada (ifc_reader.py, v3.13.0: parser SPF, unidades, colocaciones, extrusiones → niveles/muros/locales/vanos)
├── exporters/               JSON (ida/vuelta) · DXF · XLSX · CSV · IFC4 SPF (vanos en su posición real desde v3.13.0)
├── ARQ_GEN.spec             Receta PyInstaller espejo del .bat (paridad vigilada por pruebas)
├── compilar_bundle.py       Compila y verifica el bundle multiplataforma (recursos + selftest del exe)
├── ui/                      Interfaz gráfica Tkinter (FASE 90): ventana, explorador, lienzo, buscador, estados + theme (tema oscuro), help (ayuda dinámica, guía), wizard (asistente de local), building_wizard (asistente de edificación completa y regeneración) · vista 3D axonométrica (v3.11.0) · presupuesto vivo sobre las variantes (v3.12.0) · sombras solares/orientación (ui/solar.py) y terreno 3D (ui/terreno3d.py) (v3.13.0) · herramientas de edición CAD (ui/cad_tools.py, v3.14.0: paleta con iconos y asistente de modificaciones) · navegador del catálogo PRECONS III · ventanas y paneles ajustables (v3.7.0) con disposición restaurable y doble clic en separadores (v3.8.0) · barra en dos filas y logo de 22 px, plano primero (v3.9.0) · cota de cubierta y proyección en perspectiva con punto de fuga (v3.17.0)
├── plugins/                 API de plugins + 15 integrados (§88 completo: architecture, installations, gas, structure, cctv, fire, intrusion, access, perimeter, qto, budget, bim, documentation, coordination, precons) + externos en plugins\external
├── resources/               rulesets (reglas, causa/efecto fuego, PRECONS demo + PRECONS III real completo), space DNA, plantillas de presupuesto (datos, no código)
├── tests/                   2436 pruebas unittest (pirámide del spec + todas las disciplinas con valores verificados a mano)
└── 00..07 *.bat             pipeline de instalación/pruebas/compilación/ejecución con logs
```

**Principios respetados del spec maestro:** una sola pared (`WALL-001`) consultada por todos los módulos (§111); cambio → detección de dependencias → recálculo incremental → validación → auditoría (§112); trazabilidad de todo número (§105); normas como datos versionados, nunca incrustadas en código (§12); patrón DETECTAR→EXPLICAR→PROPONER→APROBAR→APLICAR→REVALIDAR (§10); un solo UNDO revierte la operación completa (§77).

---

## 7. Datos configurables (sin tocar código)

- `resources\knowledge\space_dna.json` — ADN de tipos de local (áreas mínimas, zonas húmedas, adyacencias preferidas…)
- `resources\rulesets\*.json` — reglas por jurisdicción con severidad INFO/WARNING/ERROR/HARD_BLOCK y parámetros
- `resources\budget_templates\*.json` — estructura del presupuesto: capítulos, partidas, origen de cantidades y rendimientos de recursos

Añada los suyos copiando el formato; el motor no cambia.

---

## 8. Pruebas

```bat
02_PRUEBAS.bat
```

1295 pruebas cubren: proyectos, geometría y reparación, unidades y conversiones seguras, evaluador de fórmulas (incluye rechazo de código peligroso), eventos, undo/redo (en proceso y persistente entre sesiones), migraciones reversibles (9), repositorios, auditoría, relaciones espaciales y DNA, reglas y validación, QTO con números exactos, precios históricos, presupuesto determinista, DXF legible, XLSX/CSV, round-trip JSON, backup/corruptos/recuperación, versionado, permisos, plugins internos y externos, batería completa de la CLI, instalaciones (redes, eléctrico, sanitario, HVAC, pluviales, gas, telecom), **estructura** (secciones, vigas, pilares, cerchas analíticas, uniones, QTO), **seguridad** (FOV, CCTV, fuego con causa/efecto, intrusión, acceso, perímetro, BOM), **coordinación y clash** (seis tipos de interferencia, deduplicación, ciclo de vida), **PRECONS** (takeoff, análisis con coeficientes, variantes, importador con mapa de columnas), **importadores spec 94** (tablas XLSX/CSV con cabeceras y delimitadores, catálogo plano y multi-hoja con autodetección y mapa explícito, shape «precons» del libro oficial PRECONS III con jerarquía, desglose oficial, parámetros/límites, auditoría de conteos PORTADA/SECCIONES y re-import del libro real, precios reportados, DXF→muros/locales con auditoría, CLI preview/aplicar), **BIM/IFC** (proyección de 8 dimensiones, árbol espacial, SPF válido sin referencias colgantes), **documentación** (escalas, elementos de plano, plantillas con variables, memorias deterministas, cuadros, informes, TEST-021), **optimización multiobjetivo** (dominancia de Pareto con valores verificados a mano, 12 objetivos del spec 19), **auditoría filtrada/estadísticas/exportación**, **versiones** (compare/export/branch con backup automático), **backup** (autosave rodante, incremental por hash, journal, verificación, recuperación TEST-024), **plugins** (validación estática, andamiaje, info, registro §88 completo con GAS como plugin de instalaciones §31) y **benchmark** (8 operaciones, inventario de cachés), **regresión con valores dorados** (dos demos independientes idénticas), **GUI FASE 90** (13 disciplinas §91, buscador §92 por 9 campos, estados §93 con transiciones y auditoría, lienzo con primitivas y viewport, ventana Tk real con display o Xvfb — 7 pruebas de ventana omitidas con elegancia sin display) y **GUI editable FASE 90.1** (PropertyEditor con lista blanca y auditoría UPDATE_ENTITY, creación declarativa por fachadas, borrado con cascadas, undo persistente, zoom anclado al cursor, atajos de teclado), **UX v1.7.1** (tema oscuro con estilos ttk aplicados, paleta del lienzo completa, tooltips obligatorios en la barra de herramientas y paneles, ayudas por campo que cubren todos los formularios de creación, mensajes orientadores de los 5 menús, guía rápida de 4 pasos, motor de siguiente paso, tarjeta de bienvenida en proyectos vacíos, ecos de ayuda en la barra de estado) y **v1.7.2** (asistente dinámico de diseño: validación paso a paso, geometría de muros y vanos centrados, plan declarativo y creación end-to-end auditada y eventada; fix del selector de niveles con opciones dinámicas consultadas al abrir el formulario; etiquetas en español de estados §93, diario y tipos de cálculo) y **v1.8.0** (asistente de edificación completa: 5 pasos con datos generales, niveles con cotas, locales con programas tipo, relaciones espaciales del spec §8 con puertas, trazado determinista en fila con pasillo, muros fusionados por eje, puertas automáticas + entrada, ventanas de fachada, reglas de muros portantes por sistema estructural, metadata de requerimientos climáticos/arquitectónicos/estructurales en edificio-locales-muros-vanos, reutilización de niveles y avisos del Space DNA sin bloquear) y **v1.9.0** (catálogo PRECONS III real completo: carga y conteos exactos del ruleset versionado de 15981 renglones y 4383 recursos con tipos oficiales, códigos únicos, unidades y desglose consistente en los 15981 renglones, parámetros y límites normativos como datos, secciones del índice, búsqueda sin acentos por sección con límite, precio oficial con desglose, contexto de error acotado, servicio de consulta, CLI `precons list` filtrado + `precons precio` con cantidades y navegador GUI con carga, búsqueda, desglose por cantidad y mensaje amable sin resultados) y **v2.0.0** (análisis de precio oficial directo del catálogo real con invariantes total=unitario×cantidad, presupuesto por catálogo con persistencia, acumulación, subtotales por sección, coeficientes y convivencia con presupuestos de plantilla, comando `precons budget` punta a punta con exportación CSV/PDF/PNG, PDF stdlib con acentos/tablas multipágina, SVG de plano validado XML con muros/vanos/locales/niveles, PNG del gráfico con firma y dimensiones, flujo del asistente §94 sobre XLSX pequeño y separación entre presupuestos por ruleset_code) y **v2.1.0** (usos sociales con programa de locales sugerido y relaciones del DNA extendido a 13 tipos, dimensiones máximas y tipología constructiva en el paso 1, paso bioclimático con aleros y 7 módulos de instalaciones, motor de variantes de planta con tres esquemas —lineal, doble crujía y patio central— y espejo, métricas explicables de adyacencias, luz, compacidad, ventilación y clima, ajuste a las dimensiones del lote con marcado de las que no caben, preview en canvas y generación auditada con la variante elegida) y **v3.0.0–v3.5.0** (temas oscuro/claro con cambio en vivo y autoguardado; catálogo PRECONS III certificado 1:1 con recertificación autónoma; diseño orgánico con muros curvos y diagonales; vistas SVG/PNG/PDF del asistente; importador DXF en GUI y DWG de entrada por pasarela a conversores locales; bundle PyInstaller con spec en paridad con el .bat y verificación post-compilación del ejecutable; biblioteca de detalles constructivos por ediciones regionales — México, Colombia, Argentina y Cuba — con navegador en la GUI, CLI `detalles` y esquema SVG acotado determinista) y **v3.6.0** (detalle constructivo exportable también en PDF vectorial A4 y PNG 2x deterministas, base universal ampliada a 20 detalles con muro de piedra y muro de tierra, y vínculo tipología-constructiva ↔ detalles recomendados con paridad vigilada entre el asistente y la biblioteca, pre-filtrado desde el asistente y CLI `detalles pdf|png|tipologia`) y **v3.7.0** (ventanas y paneles ajustables: sash de 10 px visible en los PanedWindow, posiciones de los separadores de la ventana principal recordadas en prefs con restauración diferida al mapeo, minsize global 960×600, y las 12 ventanas de la app redimensionables con tamaño mínimo y geometría recordada al cerrar vía `_prepare_dialog`; además, eliminada la regresión de copia superficial en `load_prefs` que compartía los diccionarios anidados de preferencias entre ventanas) y **v3.8.0** (layout restaurable con Ctrl+0 y doble clic en separadores compatible con Tk 9/Tk 8.6; ediciones regionales de detalles España CTE, Perú RNE y Chile DS 61/NCh — 7 en total — con añadidos y reemplazos 1:1 sobre la base universal intacta; memoria y especificaciones con la sección «Detalles constructivos recomendados» según la tipología del asistente adaptada a la edición activa; y exportación PDF determinista de cualquier documento del motor de documentación desde la CLI (`docs memoria --out memoria.pdf`), el servicio y la GUI) y **v3.8.1** (selftest portable al ejecutable: los checks 49/50 omiten al vuelo congelado la verificación de texto del fuente — PyInstaller no embarca los .py — y declaran la omisión, con pruebas que simulan el bundle y exigen RESULTADO: CORRECTO sin ningún FALLO) y **v3.9.0** (interfaz compacta, plano primero: la barra de herramientas muestra el logo a 22 px — el PNG de 256 px solo queda para la barra de título — y se parte en DOS filas, acciones y navegación/filtros, así el selector de niveles y el buscador ya no se cortan con la escala de Windows; separadores de fábrica 240/300/160 y panel de avisos más bajo para dar al plano el mayor espacio posible) y **v3.9.1** (el panel de avisos ya no se come la ventana: migración one-shot de las preferencias heredadas de la v3.8.0 que dejaban el separador inferior a media ventana — formato de prefs v2 con la marca bottom_compact que un archivo antiguo no puede colar —, separador inferior de fábrica 120 px, Notebook de 100 px, textos de 3 líneas y «Estado de cálculos» a 4 filas) y **v3.10.0** (edificación regenerativa: programa editable reconstruido desde el proyecto con mover/añadir/quitar/redimensionar locales y llevarlos a otro nivel, sustitución completa del edificio generado con elección entre las 28 variantes puntuadas del motor, purga ordenada y sin huérfanos de terminales de instalaciones, relaciones, vanos, muros y locales generados — conservando lo dibujado a mano —, niveles reutilizados y creados al vuelo para locales de segundo nivel, instalaciones recalculadas sobre la geometría nueva y diálogo GUI con preview de la variante y sustitución confirmada) y **v3.11.0** (vista 3D axonométrica: cámara con azimut envolvente/elevación sujeta/zoom, extrusión de muros con culling y sombreado por luz de cámara, pisos por tipo de local, vanos a su cota real con antepecho sobre la cara visible, plataformas por nivel, orden del pintor con desempate por emisión, explosión y aislado de niveles, diálogo GUI con gestos de ratón y PNG determinista 100% stdlib con el mismo encuadre que el lienzo) y **v3.12.0** (presupuesto vivo sobre las variantes: estimador paramétrico en `ui/variant_budget.py` que precia el trazado de cada variante con renglones oficiales del catálogo PRECONS III — muros por tipología con vanos descontados y clasificación geométrica exterior/interior por muestreo, losas, cimentación, escaleras, sanitarios por tipo de local y puntos eléctricos —, calidad de acabados Económica/Estándar/Premium que recalcula al vivo sin tocar la obra gruesa, columna de coste en la regeneración y en el asistente, desglose por capítulos, PNG comparativo determinista y estimación derivada que no persiste ni toca el presupuesto del proyecto) y **v3.13.1** (consola a prueba de Windows: el texto impreso de los checks de selftest y de la CLI es codificable en cp1252 — la flecha del check 55 pasaba por UnicodeEncodeError al imprimir el ejecutable —, con `core/consola.py` que reconfigura stdout/stderr a errors="replace" y una prueba que reproduce la consola exacta) y **v3.14.0** (herramientas de edición tipo CAD: motor sin Tk en `ui/cad_tools.py` con mover/copiar/reflejar/girar/recortar/alargar/chaflán/dividir/estirar/paralela/borrar — muros exclusivos por detección geométrica de aristas, vanos re-proyectados o dados de baja con aviso, puertas que cambian de mano al reflejar, muro de unión del chaflán, copias paralelas con vanos —, paleta con iconos y máquina de estados por clics con fantasma y elástico, asistente de modificaciones con vista previa antes/después, marca «editada_a_mano» que hace sobrevivir lo editado a la regeneración, y QTO/instalaciones recalculados tras cada operación) y **v3.15.0** (concepción de espacios: mobiliario por tema y uso social/doméstico con catálogo de 32 piezas, reglas por tipo de local, densidad y paso mínimo entre muebles; cubiertas por estilo con envolvente convexa, alero por offset convexo, cumbrera por el eje largo, faldones en 3D con frontones/hips/parapeto y superficie real con pendiente; accesibilidad con chequeos ARQ-ACC-10x, barandillas de escalera, rampas normativas por tramos y mesetas con pasamanos doble, barras de apoyo junto a los inodoros, y las entidades FURNITURE/ROOF/RAMP/HANDRAIL con migración 009, undo persistente, QTO, renglones PRECONS 126211/124151/072411/072351/094211 y regeneración completa), todo con valores verificados a mano.

---

## 9. Cálculos de instalaciones: método y datos

Los motores de instalaciones son deterministas y todos sus parámetros normativos
viven como datos editables en la cabecera de cada módulo (`engines/*.py`),
documentados con la norma de referencia:

| Motor | Métodos | Valores por defecto (configurables) |
|---|---|---|
| Eléctrico (§27) | I = P/(V·pf) 1φ, P/(√3·V·pf) 3φ; ΔV = 2ρLI/S y √3ρLI/S; protección normalizada IEC; sección con coordinación Ib ≤ In ≤ Iz; conducto al 40%; balance (max−min)/media | ρ Cu 0,0175 Ω·mm²/m; ampacidades IEC 60364-5-52 método C (1,5 mm²→19,5 A … 240 mm²→461 A); caída máx. ramal 3%; factores de demanda por tipo de circuito |
| Sanitario (§28) | simultaneidad k = min(1, 1,8/√n); Hazen-Williams J = 10,67·Q^1,852/(C^1,852·D^4,87); Manning en gravedad con lámina 50%; TDH = estática + rozamiento + residual; P = ρgQH/η | caudales por aparato (WC 0,10 L/s, ducha 0,15…); C PVC 140, acero 100; n PVC 0,011; pendientes mín. tipo IPC (DN50→2,08%…); residual 5 m.c.a.; η bomba 0,70 |
| HVAC (§29) | carga = transmisión + solar + interna + ventilación (y calefacción sin aportes); aire Q = Qs/(ρ·cp·ΔT); ducto A = Q/v con catálogo comercial; selección con margen 10% | ΔT refrigeración 9 K, calefacción 10 K; U muro 2,0 / vidrio 5,8 / cubierta 1,5 W/m²K; solar 180 W/m²; ocupación 10 m²/persona (75 W + 55 W); iluminación 10 + equipos 5 W/m²; infiltración 0,5 ACH; ΔT impulsión 10 K; velocidades MAIN 6 / BRANCH 4 / RETURN 3 m/s |
| Redes (§25-26) | grafo dirigido en dirección de flujo; BFS (saltos) y Dijkstra (longitud/coste); validación árbol radial o convergencia a sumidero; router ortogonal con penalizaciones | cruce de muro 15; obstáculo infranqueable 100; violación de holgura 40; holgura 5 cm; corredor preferente −0,5/m |

Cada cálculo queda registrado en la tabla `calculations` con su hash de entrada
(§102): mismo input → mismo resultado verificable. El selftest comprueba 7180 W
conectados en el panel demo como diana determinista.

## 10. Qué incluye la demo (v1.6.2)

La demo determinista incluye **12 redes** de 6 disciplinas sobre la misma
geometría, coordinadas sin interferencias HARD:

- **Fuerza e Iluminación** (POWER): tablero + 3 circuitos → 7.180 W conectados.
- **Agua Fría Sanitaria** (COLD_WATER): contador + 5 aparatos con
  dimensionado Hazen-Williams.
- **Desagüe Sanitario** (SANITARY_DRAINAGE): 2 aparatos → bajada →
  alcantarillado; colector acumula 0,25 L/s en DN50 al 2,08%.
- **Extracción Baño** (EXHAUST): rejilla 60 m³/h → extractor, DN100 a 2,12 m/s.
- **Pluvial Cubierta** (STORMWATER): 2 sumideros (80 m², C=0,90, i=100 mm/h)
  → canalón → tanque de detención 1.800 L → evacuación 2,2 L/s.
- **Gas Doméstico** (GAS): regulación + 2 válvulas + 2 aparatos (15,5 kW),
  validación completa del spec 31.
- **Telecomunicaciones** (TELECOM): rack 12U, patch panel, switch, 4 rosetas
  y uplink de fibra con presupuesto óptico.
- **Estructura**: 2 pilares de hormigón H-25 con análisis ULS-1, viga de
  acero IPE-300 con flexión y flecha, y **cercha analizada por método de
  nudos** (≈1.875 kg de acero en total).
- **CCTV**: 2 cámaras con FOV por ray casting, switch PoE y NVR; cobertura,
  red (ancho de banda/almacenamiento 30 días) y cableado calculados.
- **Detección de Incendios**: central + 4 detectores por local + pulsador +
  sirena; matriz causa/efecto ejecutada.
- **Intrusión**: central + teclado + 4 PIR en 2 zonas + 2 contactos + sirena.
- **Control de Acceso**: controlador + lector + cerradura fail-safe (0,5 s).
- **Perímetro**: valla de 40 m + 3 sensores + portón + cámara + lector.

La **coordinación** corre detección completa sobre el proyecto (sin choques
HARD); **PRECONS** analiza el proyecto con el ruleset `precons_cuba_v1` y consulta el catálogo oficial completo con `precons precio` / `precons list --buscar --seccion` (ruleset `precons_iii_rospres_330`)
(cimientos, mampostería, enlucido, acero) alimentado por QTO; y la demo se
exporta a **DXF/XLSX/CSV/JSON/IFC**.

Presupuesto con la plantilla `residential_full_v1` (8 capítulos: obra civil,
carpintería, eléctrica, sanitaria, climatización, instalaciones
complementarias, estructura y seguridad): **1.295.093,90 CUP** (valor dorado
verificado por la suite de regresión).
## Apéndice — Compilación automática en GitHub (CI incluido)

El árbol incluye `.github/workflows/compilar.yml`: al subir este código al
repositorio (push a `main`), GitHub Actions compila `ARQ_GEN.exe` en la
nube con Windows + Python 3.13 usando el pipeline completo (suite de
pruebas informativa → PyInstaller con `ARQ_GEN.spec` → selftest del
ejecutable con sus 96 comprobaciones y verificación de recursos) y publica
el resultado como artefacto descargable `ARQ_GEN_Windows_x64` (90 días).
Los pushes de etiquetas `v*` crean además un Release permanente. No hace
falta Python ni PyInstaller en el PC: la guía paso a paso con GitHub
Desktop está en `LEEME_COMPILAR_EN_GITHUB.md`.
