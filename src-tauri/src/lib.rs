mod process;

use process::{allocate_port, default_data_dir, graceful_shutdown, health_poll, spawn_backend, BackendProcess};
use std::sync::Mutex;
use tauri::{Manager, RunEvent, State, WebviewUrl, WebviewWindowBuilder};

pub struct AppState {
    pub backend_port: u16,
    pub data_dir: String,
    pub backend: Mutex<Option<BackendProcess>>,
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

            health_poll(port)?;

            let app_ui = app.clone();
            let handle = app_ui.clone();
            let _ = app_ui.run_on_main_thread(move || {
                if let Some(splash) = handle.get_webview_window("splash") {
                    let _ = splash.close();
                }
                if let Some(main) = handle.get_webview_window("main") {
                    let _ = main.show();
                    let _ = main.set_focus();
                }
            });

            Ok(())
        })();

        if let Err(err) = startup_result {
            eprintln!("backend startup failed: {err}");
            if let Some(state) = app.try_state::<AppState>() {
                let port = state.backend_port;
                let mut guard = state.backend.lock().expect("backend lock poisoned");
                if let Some(ref mut backend) = *guard {
                    graceful_shutdown(port, backend.child_mut());
                    *guard = None;
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
    let backend_port = allocate_port();
    let data_dir = default_data_dir();

    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .manage(AppState {
            backend_port,
            data_dir: data_dir.clone(),
            backend: Mutex::new(None),
        })
        .invoke_handler(tauri::generate_handler![
            get_backend_port,
            get_data_dir,
            get_app_version
        ])
        .setup(move |app| {
            open_splash(app.handle())?;
            start_backend(app.handle().clone(), backend_port, data_dir);
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app_handle, event| {
            if let RunEvent::Exit = event {
                if let Some(state) = app_handle.try_state::<AppState>() {
                    let port = state.backend_port;
                    let mut guard = state.backend.lock().expect("backend lock poisoned");
                    if let Some(ref mut backend) = *guard {
                        graceful_shutdown(port, backend.child_mut());
                    }
                }
            }
        });
}
