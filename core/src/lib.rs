//! ARQ GEN: a dependency-free, deterministic Rust domain core.
//! One implementation powers the command-line tool and the offline WebAssembly preview.
mod airflow;
mod engine;
mod exhaust;
mod furnishing;
mod geometry;
pub mod json;
pub mod model;
mod pressure;
mod svg;
#[cfg(feature = "declared-vertical-v1")]
mod vertical;

pub use engine::{explore_json, generate_json};
#[cfg(feature = "declared-vertical-v1")]
pub use vertical::declared_vertical_json;

// WebAssembly ABI: input/output are UTF-8 JSON bytes. The high 32 bits of the
// returned u64 contain length; the low 32 bits contain the pointer. The caller
// owns BOTH buffers and must call arq_free(ptr, len) on each exactly once.
#[cfg(target_arch = "wasm32")]
mod wasm {
    #[cfg(feature = "declared-vertical-v1")]
    use super::declared_vertical_json;
    use super::{explore_json, generate_json, model::error_json};

    #[no_mangle]
    pub extern "C" fn arq_alloc(len: usize) -> *mut u8 {
        if len == 0 || len > 256 * 1024 {
            return std::ptr::null_mut();
        }
        let mut bytes = vec![0_u8; len].into_boxed_slice();
        let ptr = bytes.as_mut_ptr();
        std::mem::forget(bytes);
        ptr
    }

    fn send(bytes: Vec<u8>) -> u64 {
        let mut boxed = bytes.into_boxed_slice();
        let len = boxed.len();
        let ptr = boxed.as_mut_ptr();
        std::mem::forget(boxed);
        ((len as u64) << 32) | ptr as u32 as u64
    }

    unsafe fn respond(ptr: *const u8, len: usize, operation: fn(&str) -> String) -> u64 {
        if ptr.is_null() || len == 0 || len > 256 * 1024 {
            return send(error_json("Entrada WASM inválida").stringify().into_bytes());
        }
        let input = std::slice::from_raw_parts(ptr, len);
        let output = match std::str::from_utf8(input) {
            Ok(text) => operation(text),
            Err(_) => error_json("Entrada no codificada en UTF-8").stringify(),
        };
        send(output.into_bytes())
    }

    #[no_mangle]
    pub unsafe extern "C" fn arq_generate(ptr: *const u8, len: usize) -> u64 {
        respond(ptr, len, generate_json)
    }

    // Worker-callable, synchronous and bounded; terminating the worker cancels
    // a still-running batch without blocking the editor's main thread.
    #[no_mangle]
    pub unsafe extern "C" fn arq_explore(ptr: *const u8, len: usize) -> u64 {
        respond(ptr, len, explore_json)
    }

    // Independent vertical declaration; arq_generate still returns EXACTLY v8.
    #[cfg(feature = "declared-vertical-v1")]
    #[no_mangle]
    pub unsafe extern "C" fn arq_vertical(ptr: *const u8, len: usize) -> u64 {
        respond(ptr, len, declared_vertical_json)
    }

    #[no_mangle]
    pub unsafe extern "C" fn arq_free(ptr: *mut u8, len: usize) {
        if !ptr.is_null() && len > 0 {
            drop(Box::from_raw(std::ptr::slice_from_raw_parts_mut(ptr, len)));
        }
    }
}
