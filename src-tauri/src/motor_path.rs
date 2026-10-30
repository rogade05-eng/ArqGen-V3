//! Resolución del ejecutable del motor, independiente de Tauri.
//!
//! El shell y el motor se llaman ARQ_GEN.exe: nunca debemos tomar el
//! propio shell como sidecar, ni siquiera si se indica con un enlace o
//! mediante ARQ_ENGINE_PATH.

use std::path::{Path, PathBuf};

fn es_motor(candidato: &Path, shell: Option<&Path>) -> bool {
    if !candidato.is_file() {
        return false;
    }
    let Some(shell) = shell else {
        // Sin identificar el shell no podemos garantizar que sea otro archivo.
        return false;
    };
    match (candidato.canonicalize(), shell.canonicalize()) {
        (Ok(candidato), Ok(shell)) => candidato != shell,
        _ => false,
    }
}

/// Busca primero recursos instalados, después la distribución portable y
/// de desarrollo, y finalmente la ruta explícita del usuario.
pub fn buscar_motor(
    recursos: Option<&Path>,
    shell: Option<&Path>,
    ruta_explicita: Option<&Path>,
    nombre: &str,
) -> Option<PathBuf> {
    let mut candidatos = Vec::new();
    if let Some(recursos) = recursos {
        candidatos.push(recursos.join("engine").join(nombre));
    }
    if let Some(dir) = shell.and_then(Path::parent) {
        candidatos.push(dir.join("engine").join(nombre));
        // Solo sirve si el shell tiene otro nombre; es_motor rechaza el propio.
        candidatos.push(dir.join(nombre));
        candidatos.push(dir.join("dist").join("ARQ_GEN").join(nombre));
    }
    if let Some(ruta) = ruta_explicita {
        candidatos.push(ruta.to_path_buf());
    }
    candidatos.into_iter().find(|p| es_motor(p, shell))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use std::time::{SystemTime, UNIX_EPOCH};

    struct Entorno(PathBuf);
    impl Entorno {
        fn nuevo() -> Self {
            let id = SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_nanos();
            let dir = std::env::temp_dir().join(format!("arqgen-motor-{}-{id}", std::process::id()));
            fs::create_dir_all(&dir).unwrap();
            Self(dir)
        }
        fn archivo(&self, relativo: &str) -> PathBuf {
            let ruta = self.0.join(relativo);
            fs::create_dir_all(ruta.parent().unwrap()).unwrap();
            fs::write(&ruta, b"ejecutable de prueba").unwrap();
            ruta
        }
    }
    impl Drop for Entorno {
        fn drop(&mut self) { let _ = fs::remove_dir_all(&self.0); }
    }

    #[test]
    fn nunca_ejecuta_el_shell_como_motor() {
        let env = Entorno::nuevo();
        let shell = env.archivo("ARQ_GEN.exe");
        assert_eq!(buscar_motor(None, Some(&shell), None, "ARQ_GEN.exe"), None);
        assert_eq!(buscar_motor(None, Some(&shell), Some(&shell), "ARQ_GEN.exe"), None);
    }

    #[test]
    fn prefiere_recursos_y_despues_portable() {
        let env = Entorno::nuevo();
        let shell = env.archivo("app/ARQ_GEN.exe");
        let portable = env.archivo("app/engine/ARQ_GEN.exe");
        let instalado = env.archivo("recursos/engine/ARQ_GEN.exe");
        let explicito = env.archivo("otro.exe");
        let recursos = env.0.join("recursos");
        assert_eq!(buscar_motor(Some(&recursos), Some(&shell), Some(&explicito), "ARQ_GEN.exe"), Some(instalado));
        assert_eq!(buscar_motor(None, Some(&shell), Some(&explicito), "ARQ_GEN.exe"), Some(portable));
    }

    #[test]
    fn usa_desarrollo_y_ruta_explicita_si_no_hay_recursos() {
        let env = Entorno::nuevo();
        let shell = env.archivo("app/ARQ_GEN.exe");
        let explicito = env.archivo("motor.exe");
        assert_eq!(buscar_motor(None, Some(&shell), Some(&explicito), "ARQ_GEN.exe"), Some(explicito.clone()));
        let desarrollo = env.archivo("app/dist/ARQ_GEN/ARQ_GEN.exe");
        assert_eq!(buscar_motor(None, Some(&shell), Some(&explicito), "ARQ_GEN.exe"), Some(desarrollo));
    }

    #[test]
    fn acepta_motor_junto_a_shell_con_otro_nombre() {
        let env = Entorno::nuevo();
        let shell = env.archivo("app/shell.exe");
        let motor = env.archivo("app/ARQ_GEN.exe");
        assert_eq!(buscar_motor(None, Some(&shell), None, "ARQ_GEN.exe"), Some(motor.clone()));
        assert_eq!(buscar_motor(None, None, Some(&motor), "ARQ_GEN.exe"), None);
    }

    #[cfg(unix)]
    #[test]
    fn rechaza_enlace_al_shell() {
        let env = Entorno::nuevo();
        let shell = env.archivo("app/ARQ_GEN");
        let enlace = env.0.join("enlace");
        std::os::unix::fs::symlink(&shell, &enlace).unwrap();
        assert_eq!(buscar_motor(None, Some(&shell), Some(&enlace), "ARQ_GEN"), None);
    }
}
