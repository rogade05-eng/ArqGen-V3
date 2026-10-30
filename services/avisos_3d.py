"""Avisos aproximados de interferencia para escaleras y muebles editados.

Comprueba prismas verticales para muros (con vanos rectangulares), muebles,
peldaños y mesetas. No representa estructura, instalaciones, cubiertas,
espacios libres ni superficies curvas exactas; no es certificación normativa.
"""
from __future__ import annotations

import math

_EPS = 1e-8


def _cruz(a, b, c):
    return (b[0]-a[0])*(c[1]-a[1]) - (b[1]-a[1])*(c[0]-a[0])


def _en_segmento(a, b, p):
    return (abs(_cruz(a, b, p)) <= _EPS and
            min(a[0], b[0])-_EPS <= p[0] <= max(a[0], b[0])+_EPS and
            min(a[1], b[1])-_EPS <= p[1] <= max(a[1], b[1])+_EPS)


def _cortan(a, b, c, d):
    u, v, w, z = _cruz(a, b, c), _cruz(a, b, d), _cruz(c, d, a), _cruz(c, d, b)
    return ((u > _EPS and v < -_EPS or u < -_EPS and v > _EPS) and
            (w > _EPS and z < -_EPS or w < -_EPS and z > _EPS)) or any((
                _en_segmento(a, b, c), _en_segmento(a, b, d),
                _en_segmento(c, d, a), _en_segmento(c, d, b)))


def _dentro(p, pol):
    dentro = False
    for a, b in zip(pol, pol[1:] + pol[:1]):
        if _en_segmento(a, b, p):
            return True
        if (a[1] > p[1]) != (b[1] > p[1]):
            if p[0] < (b[0]-a[0]) * (p[1]-a[1]) / (b[1]-a[1]) + a[0]:
                dentro = not dentro
    return dentro


def _solapan(a, b):
    """Intersección genérica de polígonos, incluido el contacto."""
    if len(a) < 3 or len(b) < 3:
        return False
    for p, q in zip(a, a[1:] + a[:1]):
        for r, s in zip(b, b[1:] + b[:1]):
            if _cortan(p, q, r, s):
                return True
    return _dentro(a[0], b) or _dentro(b[0], a)


def _rect(cx, cy, width, depth, rot):
    c, s = math.cos(math.radians(rot)), math.sin(math.radians(rot))
    return [(cx+x*c-y*s, cy+x*s+y*c) for x, y in
            ((-width/2, -depth/2), (width/2, -depth/2),
             (width/2, depth/2), (-width/2, depth/2))]


def _prismas_solapan(a, b):
    """SAT para prismas rectangulares verticales; el mero contacto no choca."""
    pa, za, za1 = a
    pb, zb, zb1 = b
    if min(za1, zb1) - max(za, zb) <= _EPS:
        return False
    # Rechazo barato antes del SAT: importante con muchos peldaños y vanos.
    for i in (0, 1):
        if min(max(p[i] for p in pa), max(p[i] for p in pb)) - max(
                min(p[i] for p in pa), min(p[i] for p in pb)) <= _EPS:
            return False
    for poly in (pa, pb):
        for p, q in zip(poly, poly[1:] + poly[:1]):
            nx, ny = -(q[1]-p[1]), q[0]-p[0]
            largo = math.hypot(nx, ny)
            if largo <= _EPS:
                continue
            nx, ny = nx/largo, ny/largo
            aa = [x*nx+y*ny for x,y in pa]
            bb = [x*nx+y*ny for x,y in pb]
            if min(max(aa), max(bb)) - max(min(aa), min(bb)) <= _EPS:
                return False
    return True


def _piezas(ctx, obj, niveles, vanos):
    """Prismas aproximados en coordenadas globales, también entre niveles."""
    nivel_z = niveles.get(obj.level_id)
    if nivel_z is None:
        return []
    meta = obj.metadata or {}
    offset = float(meta.get("editor_base_offset_m", 0.0) or 0.0)
    if obj.ENTITY_TYPE == "FURNITURE":
        z = nivel_z + 0.02 + offset
        return [(_rect(obj.x, obj.y, obj.width_m, obj.depth_m, obj.rotation_deg), z, z+obj.height_m)]
    if obj.ENTITY_TYPE == "STAIR":
        cajas = []
        for paso in meta.get("pasos") or []:
            z0, z1 = float(paso["z0"]), float(paso["z1"])
            if z1 <= z0 + 1e-9:
                z1 = z0 + 0.04
            cajas.append((_rect(obj.x+float(paso["cx"]), obj.y+float(paso["cy"]),
                                float(paso["dx"]), float(paso["dy"]), float(paso.get("rot", 0.0))),
                          nivel_z+offset+z0, nivel_z+offset+z1))
        return cajas
    if obj.ENTITY_TYPE == "WALL":
        (x1,y1), (x2,y2) = obj.start, obj.end
        longitud = math.hypot(x2-x1, y2-y1)
        if longitud <= _EPS:
            return []
        base = nivel_z + float(getattr(obj, "base_offset_m", 0.0) or 0.0)
        huecos = []
        for v in vanos.get(obj.id, []):
            lo = max(0.0, min(longitud, float(v.offset_m)))
            hi = max(lo, min(longitud, lo + float(v.width_m)))
            z0 = max(0.0, float(v.sill_height_m or 0.0))
            z1 = min(float(obj.height_m), z0 + float(v.height_m))
            if hi > lo and z1 > z0:
                huecos.append((lo, hi, z0, z1))
        cortes_x = sorted({0.0, longitud} | {x for h in huecos for x in h[:2]})
        cortes_z = sorted({0.0, float(obj.height_m)} | {z for h in huecos for z in h[2:]})
        ux, uy = (x2-x1)/longitud, (y2-y1)/longitud
        nx, ny = -uy*obj.thickness_m/2, ux*obj.thickness_m/2
        cajas = []
        for a,b in zip(cortes_x, cortes_x[1:]):
            for c,d in zip(cortes_z, cortes_z[1:]):
                if any(h[0] <= (a+b)/2 <= h[1] and h[2] <= (c+d)/2 <= h[3] for h in huecos):
                    continue
                pa, pb = (x1+ux*a,y1+uy*a), (x1+ux*b,y1+uy*b)
                pol = [(pa[0]+nx,pa[1]+ny),(pb[0]+nx,pb[1]+ny),
                       (pb[0]-nx,pb[1]-ny),(pa[0]-nx,pa[1]-ny)]
                cajas.append((pol, base+c, base+d))
        return cajas
    return []


def _piezas_validas(ctx, obj, niveles, vanos):
    cajas = _piezas(ctx, obj, niveles, vanos)
    for pol, z0, z1 in cajas:
        if (len(pol) != 4 or not math.isfinite(z0) or not math.isfinite(z1)
                or z1 <= z0 or any(not math.isfinite(v) for p in pol for v in p)):
            raise ValueError("Prisma inválido")
    return cajas


def avisos_objeto(ctx, obj):
    """Posibles choques 3D de los tipos cubiertos, sin bloquear la edición."""
    niveles = {n.id: float(n.elevation_m) for n in ctx.architecture.list("LEVEL", ctx.project.id)}
    vanos = {}
    for v in ctx.architecture.list("OPENING", ctx.project.id):
        vanos.setdefault(v.wall_id, []).append(v)
    try:
        propias = _piezas_validas(ctx, obj, niveles, vanos)
    except (ValueError, TypeError, KeyError, IndexError, OverflowError, AttributeError):
        return ["No se pueden comprobar interferencias: geometría o metadatos inválidos."]
    if not propias:
        return ["No hay geometría o nivel para comprobar interferencias del elemento."]
    choques = []
    incompletos = 0
    for tipo in ("WALL", "FURNITURE", "STAIR"):
        for otro in ctx.architecture.list(tipo, ctx.project.id):
            if otro.id == obj.id:
                continue
            try:
                cajas = _piezas_validas(ctx, otro, niveles, vanos)
            except (ValueError, TypeError, KeyError, IndexError, OverflowError, AttributeError):
                incompletos += 1
                continue
            if not cajas:
                incompletos += 1
            if any(_prismas_solapan(a, b) for a in propias for b in cajas):
                choques.append(otro.code)
    avisos = []
    if incompletos:
        avisos.append(f"Comprobación incompleta: {incompletos} elemento(s) sin geometría o nivel válido.")
    if choques:
        ejemplos = ", ".join(choques[:8]) + ("…" if len(choques) > 8 else "")
        avisos.append(f"Posibles interferencias 3D con {len(choques)} elemento(s): {ejemplos}.")
    if obj.ENTITY_TYPE == "STAIR":
        espacio = ctx.architecture.get("SPACE", obj.space_id) if obj.space_id else None
        try:
            outline = meta_outline(obj)
        except (ValueError, TypeError, KeyError, IndexError, OverflowError, AttributeError):
            outline = []
            avisos.append("No se puede comprobar el contorno de la escalera: metadatos inválidos.")
        if espacio is not None and espacio.level_id == obj.level_id:
            recinto = list(espacio.boundary or [])
            if len(recinto) >= 3 and outline and not all(_dentro(p, recinto) for p in outline):
                avisos.append("El contorno de la escalera sale del recinto asociado en planta.")
    return avisos


def meta_outline(escalera):
    return [(float(x)+escalera.x, float(y)+escalera.y) for x,y in
            ((escalera.metadata or {}).get("outline") or [])]


def avisos_escalera(ctx, escalera):
    return avisos_objeto(ctx, escalera)
