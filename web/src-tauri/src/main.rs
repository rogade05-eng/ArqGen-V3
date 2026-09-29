#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    // No IPC commands or plugins: the same locally bundled Rust/WASM core runs
    // in WebView2. Privileged file and network APIs are deliberately not exposed.
    tauri::Builder::default()
        .run(tauri::generate_context!())
        .expect("No se pudo iniciar ARQ GEN en WebView2");
}
