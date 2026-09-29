//! Explicit 2D gross/clear plan partition for the limited two-strip MVP-0.1 layouts.
//! These bands are geometric allowances, not a structural wall specification.
use crate::model::{Entrance, PlanGeometry, Rect, Room, Rules, Side, EPS};

pub fn gross_corridor_width(rules: &Rules) -> f64 {
    // Reserve for the thicker of a half-partition and an exterior band on either side.
    // Otherwise a valid, thicker partition could silently shrink the clear corridor.
    rules.corridor_width + 2.0 * rules.exterior_wall.max(rules.partition_wall / 2.0)
}

pub fn clear_room(cell: Rect, side: Side, first: bool, last: bool, rules: &Rules) -> Rect {
    let inside = rules.partition_wall / 2.0;
    let top = if first { rules.exterior_wall } else { inside };
    let bottom = if last { rules.exterior_wall } else { inside };
    let x = if side == Side::Left {
        cell.x + rules.exterior_wall
    } else {
        cell.x + inside
    };
    Rect {
        x,
        y: cell.y + top,
        w: cell.w - rules.exterior_wall - inside,
        h: cell.h - top - bottom,
    }
}

/// The corridor has a constant gross cell, but a variable clear width where a
/// room ends. Its free-space slices are contiguous in y and do not overlap.
pub fn clear_corridor(corridor: Rect, rooms: &[Room], rules: &Rules) -> Vec<Rect> {
    let start = corridor.y + rules.exterior_wall;
    let end = corridor.bottom() - rules.exterior_wall;
    if end <= start + EPS {
        return Vec::new();
    }
    let mut cuts = vec![start, end];
    for room in rooms {
        for y in [room.rect.y, room.rect.bottom()] {
            if y > start + EPS && y < end - EPS {
                cuts.push(y);
            }
        }
    }
    cuts.sort_by(f64::total_cmp);
    cuts.dedup_by(|a, b| (*a - *b).abs() <= EPS);
    cuts.windows(2)
        .filter(|pair| pair[1] > pair[0] + EPS)
        .map(|pair| {
            let y = (pair[0] + pair[1]) / 2.0;
            let inset = |side| {
                if rooms
                    .iter()
                    .any(|r| r.side == side && r.rect.y <= y && r.rect.bottom() >= y)
                {
                    rules.partition_wall / 2.0
                } else {
                    rules.exterior_wall
                }
            };
            let left = inset(Side::Left);
            let right = inset(Side::Right);
            Rect {
                x: corridor.x + left,
                y: pair[0],
                w: corridor.w - left - right,
                h: pair[1] - pair[0],
            }
        })
        .collect()
}

// Four nonoverlapping bands: full-width front/rear + side bands within clear height.
fn wall_bands(cell: Rect, clear: Rect, walls: &mut Vec<Rect>) {
    let candidates = [
        Rect {
            x: cell.x,
            y: cell.y,
            w: cell.w,
            h: clear.y - cell.y,
        },
        Rect {
            x: cell.x,
            y: clear.bottom(),
            w: cell.w,
            h: cell.bottom() - clear.bottom(),
        },
        Rect {
            x: cell.x,
            y: clear.y,
            w: clear.x - cell.x,
            h: clear.h,
        },
        Rect {
            x: clear.right(),
            y: clear.y,
            w: cell.right() - clear.right(),
            h: clear.h,
        },
    ];
    walls.extend(
        candidates
            .into_iter()
            .filter(|band| band.w > EPS && band.h > EPS),
    );
}

pub fn assemble(rooms: Vec<Room>, corridor: Rect, rules: &Rules) -> Result<PlanGeometry, String> {
    let corridor_usable = clear_corridor(corridor, &rooms, rules);
    if corridor_usable.is_empty()
        || corridor_usable
            .iter()
            .any(|r| !r.valid() || r.w + EPS < rules.corridor_width)
    {
        return Err("El pasillo libre después de muros no alcanza el ancho mínimo.".into());
    }
    let mut walls = Vec::new();
    for room in &rooms {
        if !room.rect.valid() || !room.usable.valid() || !room.rect.contains(room.usable) {
            return Err("Los muros consumen la superficie útil de un local.".into());
        }
        wall_bands(room.rect, room.usable, &mut walls);
    }
    let clear_start = corridor.y + rules.exterior_wall;
    let clear_end = corridor.bottom() - rules.exterior_wall;
    walls.push(Rect {
        x: corridor.x,
        y: corridor.y,
        w: corridor.w,
        h: rules.exterior_wall,
    });
    walls.push(Rect {
        x: corridor.x,
        y: clear_end,
        w: corridor.w,
        h: rules.exterior_wall,
    });
    for slice in &corridor_usable {
        walls.push(Rect {
            x: corridor.x,
            y: slice.y,
            w: slice.x - corridor.x,
            h: slice.h,
        });
        walls.push(Rect {
            x: slice.right(),
            y: slice.y,
            w: corridor.right() - slice.right(),
            h: slice.h,
        });
    }
    if walls.iter().any(|w| !w.valid()) || clear_end <= clear_start {
        return Err("Espesores de muro incompatibles con las dimensiones del pasillo.".into());
    }
    let entrance_x = corridor.x + corridor.w / 2.0;
    let entrance = Entrance {
        width: rules.main_door,
        opening: Rect {
            x: entrance_x - rules.main_door / 2.0,
            y: corridor.y,
            w: rules.main_door,
            h: rules.exterior_wall,
        },
        swing: Rect {
            x: entrance_x - rules.main_door / 2.0,
            y: clear_start,
            w: rules.main_door,
            h: rules.main_door,
        },
    };
    let built_area = corridor.area() + rooms.iter().map(|r| r.rect.area()).sum::<f64>();
    let circulation_usable_area = corridor_usable.iter().map(|r| r.area()).sum::<f64>();
    let usable_area = circulation_usable_area + rooms.iter().map(|r| r.usable.area()).sum::<f64>();
    let wall_allowance_area = walls.iter().map(|r| r.area()).sum::<f64>();
    Ok(PlanGeometry {
        rooms,
        corridor,
        corridor_usable,
        wall_zones: walls,
        entrance,
        built_area,
        usable_area,
        circulation_usable_area,
        wall_allowance_area,
    })
}

pub fn covered_by(rect: Rect, disjoint: &[Rect]) -> bool {
    rect.valid()
        && (disjoint
            .iter()
            .map(|r| r.intersection_area(rect))
            .sum::<f64>()
            - rect.area())
        .abs()
            <= 1e-5
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn bands_do_not_overlap_and_conserve_area() {
        let gross = Rect {
            x: 0.0,
            y: 0.0,
            w: 4.0,
            h: 5.0,
        };
        let clear = Rect {
            x: 0.18,
            y: 0.18,
            w: 3.76,
            h: 4.70,
        };
        let mut bands = Vec::new();
        wall_bands(gross, clear, &mut bands);
        assert!(
            (gross.area() - clear.area() - bands.iter().map(|r| r.area()).sum::<f64>()).abs() < EPS
        );
        for (i, a) in bands.iter().enumerate() {
            assert!(!clear.overlaps_interior(*a));
            for b in bands.iter().skip(i + 1) {
                assert!(!a.overlaps_interior(*b));
            }
        }
    }
}
