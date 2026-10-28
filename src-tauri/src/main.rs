// ============================================================================
//  ARQ GEN - Shell Tauri 2 (FASE A + FASE C)
//  Arquitectura del «ARQ GEN TAURI.txt» v3.0: el RAZONAMIENTO vive en el
//  motor Python (sidecar); este shell Rust solo lanza el proceso, habla
//  JSON-RPC por stdin/stdout y expone `invoke('rpc', ...)` a la web.
//  FASE C: además resuelve la carpeta de descargas del usuario para que
//  la UI web pueda EXPORTAR (IFC/DXF/XLSX/...) sin plugins nativos.
//  Sin red, sin plugins externos: std + tauri + serde_json.
// ============================================================================

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use serde_json::Value;
use std::io::{BufRead, BufReader, Write};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use tauri::Manager;

/// Estado global: el proceso del motor (nace perezoso en la 1a llamada).
struct Motor(Mutex<Option<Child>>);

#[cfg(windows)]
use std::os::windows::process::CommandExt;

/// Resuelve la ruta del binario del motor con la cadena de fallback:
///   1) recurso empaquetado  <resource_dir>/engine/ARQ_GEN.exe
///   2) junto al shell       <exe_dir>/ARQ_GEN.exe
///   3) dist de desarrollo   <exe_dir>/dist/ARQ_GEN/ARQ_GEN.exe
///   4) variable de entorno  ARQ_ENGINE_PATH
fn ruta_motor(app: &tauri::AppHandle) -> Result<std::path::PathBuf, String> {
    let exe = if cfg!(windows) { "ARQ_GEN.exe" } else { "ARQ_GEN" };

    if let Ok(res) = app.path().resource_dir() {
        let p = res.join("engine").join(exe);
        if p.is_file() {
            return Ok(p);
        }
    }
    if let Ok(cur) = std::env::current_exe() {
        if let Some(dir) = cur.parent() {
            let p = dir.join(exe);
            if p.is_file() {
                return Ok(p);
            }
            let dev = dir.join("dist").join("ARQ_GEN").join(exe);
            if dev.is_file() {
                return Ok(dev);
            }
        }
    }
    if let Ok(envp) = std::env::var("ARQ_ENGINE_PATH") {
        let p = std::path::PathBuf::from(envp);
        if p.is_file() {
            return Ok(p);
        }
    }
    Err("No encuentro el motor ARQ_GEN (sidecar). Compila el motor \
         (PyInstaller ARQ_GEN.spec) o define ARQ_ENGINE_PATH."
        .to_string())
}

/// Lanza el sidecar si no vive (o lo relanza si murio).
fn encender(app: &tauri::AppHandle, estado: &Motor) -> Result<(), String> {
    let mut guard = estado.0.lock().map_err(|_| "mutex del motor envenenado")?;
    if let Some(child) = guard.as_mut() {
        match child.try_wait() {
            Ok(None) => return Ok(()), // sigue vivo
            _ => *guard = None,        // murio: relanzar
        }
    }
    let ruta = ruta_motor(app)?;
    let mut cmd = Command::new(&ruta);
    cmd.arg("rpc")
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::null());
    #[cfg(windows)]
    cmd.creation_flags(0x0800_0000); // CREATE_NO_WINDOW: sin consola visible
    let child = cmd
        .spawn()
        .map_err(|e| format!("no pude lanzar el motor ({}): {e}", ruta.display()))?;
    *guard = Some(child);
    Ok(())
}

/// Comando expuesto a la web: `invoke('rpc', { method, params })`.
/// Escribe UNA linea JSON-RPC en stdin y espera UNA linea de respuesta.
#[tauri::command]
fn rpc(
    app: tauri::AppHandle,
    estado: State<Motor>,
    method: String,
    params: Value,
) -> Result<Value, String> {
    encender(&app, &estado)?;
    let mut guard = estado.0.lock().map_err(|_| "mutex del motor envenenado")?;
    let child = guard.as_mut().ok_or("el motor no arranco")?;

    let peticion = serde_json::json!({
        "jsonrpc": "2.0", "id": 1, "method": method, "params": params
    });
    let mut linea = peticion.to_string();
    linea.push('\n');

    let stdin = child.stdin.as_mut().ok_or("stdin del motor no disponible")?;
    stdin
        .write_all(linea.as_bytes())
        .map_err(|e| format!("stdin del motor roto: {e}"))?;
    stdin.flush().map_err(|e| format!("stdin flush: {e}"))?;

    let stdout = child.stdout.as_mut().ok_or("stdout del motor no disponible")?;
    let mut lector = BufReader::new(stdout);
    let mut respuesta = String::new();
    lector
        .read_line(&mut respuesta)
        .map_err(|e| format!("stdout del motor roto: {e}"))?;
    if respuesta.trim().is_empty() {
        return Err("el motor cerro el canal (murio el sidecar)".to_string());
    }
    let v: Value = serde_json::from_str(&respuesta)
        .map_err(|e| format!("respuesta no es JSON: {e}"))?;
    if let Some(err) = v.get("error") {
        // Propaga el error JSON-RPC tal cual (-32601, -32602, ...) a la UI
        return Err(err.to_string());
    }
    Ok(v.get("result").cloned().unwrap_or(Value::Null))
}

/// Comando de diagnostico: donde esta el motor (para la barra de estado).
#[tauri::command]
fn motor_ruta(app: tauri::AppHandle) -> Result<String, String> {
    ruta_motor(&app).map(|p| p.to_string_lossy().into_owned())
}

/// FASE C: carpeta de descargas del usuario (destino por defecto de la
/// exportación). Sin plugins: el path resolver es núcleo de Tauri 2.
#[tauri::command]
fn carpeta_descargas(app: tauri::AppHandle) -> Result<String, String> {
    app.path()
        .download_dir()
        .map(|p| p.to_string_lossy().into_owned())
        .map_err(|e| format!("no pude resolver la carpeta de descargas: {e}"))
}

fn main() {
    tauri::Builder::default()
        .manage(Motor(Mutex::new(None)))
        .invoke_handler(tauri::generate_handler![rpc, motor_ruta, carpeta_descargas])
        .run(tauri::generate_context!())
        .expect("error al arrancar el shell Tauri de ARQ GEN");
}
