#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::process::{Child, Command, Stdio};
use std::sync::Mutex;

use tauri::{AppHandle, Manager};

struct BackendProc(Mutex<Option<Child>>);

fn start_backend() -> Option<Child> {
    // Assumes Python is on PATH.
    // In dev, we run from `desktop/src-tauri` so `../backend` is correct.
    // In packaged builds, this relative path may differ; we'll refine when bundling.
    let mut cmd = Command::new("python");
    cmd.current_dir("../backend")
        .args([
            "-m",
            "uvicorn",
            "main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8000",
        ])
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());

    cmd.spawn().ok()
}

fn stop_backend(app: &AppHandle) {
    let state = app.state::<BackendProc>();
    let mut guard = state.0.lock().unwrap();
    if let Some(mut c) = guard.take() {
        let _ = c.kill();
        let _ = c.wait();
    }
}

fn main() {
    tauri::Builder::default()
        .manage(BackendProc(Mutex::new(None)))
        .setup(|app| {
            let state = app.state::<BackendProc>();
            let mut guard = state.0.lock().unwrap();
            if guard.is_none() {
                *guard = start_backend();
            }
            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { .. } = event {
                stop_backend(&window.app_handle());
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

