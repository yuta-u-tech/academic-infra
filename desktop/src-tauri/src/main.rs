// Spawns the acenglish FastAPI sidecar (bound to 127.0.0.1:8791 only, see
// scripts/acenglish/api.py::ensure_loopback), waits for /api/health, then
// opens a window against it. The sidecar is killed when the window closes so
// no orphaned Python process is left running.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::time::Duration;

use tauri::{Manager, WebviewUrl, WebviewWindowBuilder};
use tauri_plugin_shell::process::CommandChild;
use tauri_plugin_shell::ShellExt;

const HEALTH_URL: &str = "http://127.0.0.1:8791/api/health";
const APP_URL: &str = "http://127.0.0.1:8791";
const HEALTH_TIMEOUT: Duration = Duration::from_secs(15);
const HEALTH_POLL_INTERVAL: Duration = Duration::from_millis(200);

struct SidecarHandle(std::sync::Mutex<Option<CommandChild>>);

fn wait_for_health() -> bool {
    let client = reqwest::blocking::Client::builder()
        .timeout(Duration::from_millis(500))
        .build()
        .expect("failed to build health-check http client");
    let deadline = std::time::Instant::now() + HEALTH_TIMEOUT;
    while std::time::Instant::now() < deadline {
        if let Ok(response) = client.get(HEALTH_URL).send() {
            if response.status().is_success() {
                return true;
            }
        }
        std::thread::sleep(HEALTH_POLL_INTERVAL);
    }
    false
}

fn kill_sidecar(app_handle: &tauri::AppHandle) {
    if let Some(handle) = app_handle.try_state::<SidecarHandle>() {
        if let Some(child) = handle.0.lock().unwrap().take() {
            // The PyInstaller onefile bootloader forks a worker process; killing
            // just the bootloader PID leaves the worker (and the 8791 listener)
            // orphaned. Kill by PID pattern to catch both, then the direct handle.
            let pid = child.pid();
            let _ = std::process::Command::new("pkill")
                .args(["-P", &pid.to_string()])
                .status();
            let _ = child.kill();
        }
    }
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .setup(|app| {
            let (_rx, child) = app
                .shell()
                .sidecar("acenglish-server")
                .expect("failed to prepare acenglish-server sidecar")
                .spawn()
                .expect("failed to spawn acenglish-server sidecar");

            app.manage(SidecarHandle(std::sync::Mutex::new(Some(child))));

            if !wait_for_health() {
                eprintln!("acenglish-server did not become healthy in time");
            }

            // Standard native title bar. An overlay/hidden-title bar needs a
            // hand-rolled JS drag region (core:window:allow-start-dragging +
            // data-tauri-drag-region) that turned out unreliable to get right
            // without being able to interactively test window dragging in this
            // environment; the native bar drags for free and can't regress.
            WebviewWindowBuilder::new(app, "main", WebviewUrl::External(APP_URL.parse().unwrap()))
                .title("Academic English")
                .inner_size(960.0, 720.0)
                .min_inner_size(720.0, 560.0)
                .build()?;

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building acenglish-desktop")
        .run(|app_handle, event| {
            // Covers window-close AND app-quit (Cmd+Q / dock quit / osascript quit) —
            // on_window_event alone misses the latter, orphaning the sidecar.
            if matches!(
                event,
                tauri::RunEvent::ExitRequested { .. } | tauri::RunEvent::Exit
            ) {
                kill_sidecar(app_handle);
            }
        });
}
