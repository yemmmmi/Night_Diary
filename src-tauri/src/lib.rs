mod backup;
mod process;

use backup::{auto_backup_on_exit, create_backup, list_backups, restore_backup};

use process::{
    allocate_port, default_data_dir, graceful_shutdown, health_check_once, health_poll,
    spawn_backend, try_attach_dev_backend, BackendProcess,
};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Mutex;
use tauri::{Emitter, Manager, RunEvent, State, WebviewUrl, WebviewWindowBuilder};

pub struct AppState {
    pub backend_port: u16,
    pub data_dir: String,
    pub backend: Mutex<Option<BackendProcess>>,
    /// Uvicorn listening (/health OK) — frontend shell may show.
    pub backend_ready: AtomicBool,
    /// Attached to external dev backend — do not spawn or shutdown on exit.
    pub external_backend: AtomicBool,
    /// Whether auto-backup on exit is enabled (set by frontend via set_auto_backup).
    pub auto_backup_enabled: AtomicBool,
}

#[tauri::command]
fn set_auto_backup(enabled: bool, state: State<'_, AppState>) {
    state.auto_backup_enabled.store(enabled, Ordering::SeqCst);
}

#[tauri::command]
fn get_backend_port(state: State<'_, AppState>) -> u16 {
    state.backend_port
}

#[tauri::command]
fn get_data_dir(state: State<'_, AppState>) -> String {
    state.data_dir.clone()
}

#[tauri::command]
fn get_app_version(app: tauri::AppHandle) -> String {
    app.package_info().version.to_string()
}

#[tauri::command]
fn check_backend_health(state: State<'_, AppState>) -> bool {
    if state.backend_ready.load(Ordering::SeqCst) {
        return true;
    }
    health_check_once(state.backend_port)
}

#[tauri::command]
fn is_backend_ready(state: State<'_, AppState>) -> bool {
    state.backend_ready.load(Ordering::SeqCst)
}

#[tauri::command]
fn is_core_ready(state: State<'_, AppState>) -> bool {
    if state.external_backend.load(Ordering::SeqCst) || state.backend_ready.load(Ordering::SeqCst) {
        return ready_check_once(state.backend_port);
    }
    false
}

fn ready_check_once(port: u16) -> bool {
    let url = format!("http://127.0.0.1:{port}/ready");
    reqwest::blocking::Client::builder()
        .timeout(std::time::Duration::from_millis(300))
        .no_proxy()
        .build()
        .ok()
        .and_then(|client| client.get(&url).send().ok())
        .is_some_and(|r| r.status().is_success())
}

fn splash_path() -> std::path::PathBuf {
    std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("resources/splash.html")
}

fn open_splash(app: &tauri::AppHandle) -> tauri::Result<()> {
    let splash_file = splash_path();
    let splash_url = WebviewUrl::External(
        url::Url::from_file_path(&splash_file)
            .map_err(|_| tauri::Error::Io(std::io::Error::other("invalid splash.html path")))?,
    );

    WebviewWindowBuilder::new(app, "splash", splash_url)
        .title("夜记")
        .inner_size(480.0, 320.0)
        .center()
        .decorations(false)
        .always_on_top(true)
        .resizable(false)
        .skip_taskbar(true)
        .build()?;

    Ok(())
}

fn finish_external_attach(app: tauri::AppHandle, port: u16) {
    if let Some(state) = app.try_state::<AppState>() {
        state.backend_ready.store(true, Ordering::SeqCst);
        state.external_backend.store(true, Ordering::SeqCst);
    }
    let _ = app.emit("backend-ready", port);
    let handle = app.clone();
    let _ = app.run_on_main_thread(move || {
        if let Some(splash) = handle.get_webview_window("splash") {
            let _ = splash.close();
        }
        if let Some(main) = handle.get_webview_window("main") {
            let _ = main.set_focus();
        }
    });
}

fn start_backend(app: tauri::AppHandle, port: u16, data_dir: String) {
    std::thread::spawn(move || {
        let startup_result = (|| -> Result<(), String> {
            let mut backend = spawn_backend(port, &data_dir)?;
            if let Some(state) = app.try_state::<AppState>() {
                *state.backend.lock().expect("backend lock poisoned") = Some(backend);
            } else {
                graceful_shutdown(port, backend.child_mut());
                return Err("application state unavailable".to_string());
            }

            health_poll(port, Some(&app))?;

            if let Some(state) = app.try_state::<AppState>() {
                state.backend_ready.store(true, Ordering::SeqCst);
            }
            let _ = app.emit("backend-ready", port);

            let app_ui = app.clone();
            let handle = app_ui.clone();
            let _ = app_ui.run_on_main_thread(move || {
                if let Some(splash) = handle.get_webview_window("splash") {
                    let _ = splash.close();
                }
                if let Some(main) = handle.get_webview_window("main") {
                    let _ = main.set_focus();
                }
            });

            Ok(())
        })();

        if let Err(err) = startup_result {
            eprintln!("backend startup failed: {err}");
            if let Some(state) = app.try_state::<AppState>() {
                if !state.external_backend.load(Ordering::SeqCst) {
                    let port = state.backend_port;
                    let mut guard = state.backend.lock().expect("backend lock poisoned");
                    if let Some(ref mut backend) = *guard {
                        graceful_shutdown(port, backend.child_mut());
                    }
                }
            }
            let app_ui = app.clone();
            let handle = app_ui.clone();
            let _ = app_ui.run_on_main_thread(move || {
                if let Some(splash) = handle.get_webview_window("splash") {
                    let _ = splash.close();
                }
                if let Some(main) = handle.get_webview_window("main") {
                    let _ = main.show();
                }
            });
        }
    });
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let data_dir = default_data_dir();
    let (backend_port, use_external) = match try_attach_dev_backend() {
        Some(port) => (port, true),
        None => (allocate_port(), false),
    };

    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .manage(AppState {
            backend_port,
            data_dir: data_dir.clone(),
            backend: Mutex::new(None),
            backend_ready: AtomicBool::new(false),
            external_backend: AtomicBool::new(use_external),
            auto_backup_enabled: AtomicBool::new(true), // default: auto-backup on
        })
        .invoke_handler(tauri::generate_handler![
            get_backend_port,
            get_data_dir,
            get_app_version,
            check_backend_health,
            is_backend_ready,
            is_core_ready,
            list_backups,
            create_backup,
            restore_backup,
            set_auto_backup,
        ])
        .setup(move |app| {
            open_splash(app.handle())?;
            if let Some(main) = app.get_webview_window("main") {
                let _ = main.show();
            }
            if use_external {
                finish_external_attach(app.handle().clone(), backend_port);
            } else {
                start_backend(app.handle().clone(), backend_port, data_dir);
            }
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app_handle, event| {
            if let RunEvent::Exit = event {
                if let Some(state) = app_handle.try_state::<AppState>() {
                    if !state.external_backend.load(Ordering::SeqCst) {
                        // Shutdown backend FIRST to flush all pending SQLite writes,
                        // then backup to avoid half-consistent database snapshots.
                        let port = state.backend_port;
                        let mut guard = state.backend.lock().expect("backend lock poisoned");
                        if let Some(ref mut backend) = *guard {
                            graceful_shutdown(port, backend.child_mut());
                        }
                        drop(guard); // release lock before backup
                        // Only backup if autoBackup is enabled (set by frontend)
                        if state.auto_backup_enabled.load(Ordering::SeqCst) {
                            let _ = auto_backup_on_exit(&state.data_dir);
                        }
                    }
                }
            }
        });
}
