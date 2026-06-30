//! Python sidecar lifecycle: spawn, health polling, graceful shutdown.

use std::net::TcpListener;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::time::Duration;

use tauri::Emitter;

// 200ms × 600 = 120 seconds total (sidecar needs 30+ seconds to start)
const HEALTH_INTERVAL_MS: u64 = 200;
const HEALTH_MAX_ATTEMPTS: u32 = 600;
const SHUTDOWN_GRACE_SECS: u64 = 3;

pub struct BackendProcess {
    child: Child,
}

impl BackendProcess {
    pub fn child_mut(&mut self) -> &mut Child {
        &mut self.child
    }
}

/// Write a log message to both stderr (dev console) and the log file (release debug).
fn log_msg(msg: &str) {
    eprintln!("{msg}");
    if let Some(dir) = std::env::current_exe()
        .ok()
        .and_then(|e| e.parent().map(|p| p.to_path_buf()))
    {
        let log_path = dir.join("nightdiary.log");
        use std::io::Write;
        if let Ok(mut f) = std::fs::OpenOptions::new()
            .create(true)
            .append(true)
            .open(&log_path)
        {
            let _ = writeln!(f, "{msg}");
        }
    }
}

/// Bind to port 0 and return the allocated port number.
pub fn allocate_port() -> u16 {
    let listener = TcpListener::bind("127.0.0.1:0").expect("failed to bind ephemeral port");
    listener.local_addr().expect("failed to read local addr").port()
}

/// Default application data directory (%APPDATA%/night-diary on Windows).
pub fn default_data_dir() -> String {
    #[cfg(target_os = "windows")]
    {
        if let Ok(app_data) = std::env::var("APPDATA") {
            return PathBuf::from(app_data)
                .join("night-diary")
                .to_string_lossy()
                .into_owned();
        }
    }

    #[cfg(not(target_os = "windows"))]
    {
        if let Ok(xdg) = std::env::var("XDG_DATA_HOME") {
            return PathBuf::from(xdg)
                .join("night-diary")
                .to_string_lossy()
                .into_owned();
        }
        if let Ok(home) = std::env::var("HOME") {
            return PathBuf::from(home)
                .join(".local")
                .join("share")
                .join("night-diary")
                .to_string_lossy()
                .into_owned();
        }
    }

    "./data".to_string()
}

fn project_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .expect("src-tauri has a parent directory")
        .to_path_buf()
}

fn server_dir() -> PathBuf {
    project_root().join("server")
}

fn python_executable() -> String {
    // debug/dev: try common Python locations when PATH doesn't include one
    let candidates: &[&str] = if cfg!(windows) {
        &["python", "python3"]
    } else {
        &["python3", "python"]
    };

    for name in candidates {
        if let Ok(path) = std::process::Command::new(name).arg("--version").output() {
            if path.status.success() {
                return name.to_string();
            }
        }
    }

    // PATH lookup failed — try well-known install locations
    if cfg!(windows) {
        for base in common_python_dirs() {
            let exe = base.join("python.exe");
            if exe.exists() {
                return exe.to_string_lossy().into_owned();
            }
        }
    }

    // last resort
    if cfg!(windows) { "python".to_string() } else { "python3".to_string() }
}

fn common_python_dirs() -> Vec<std::path::PathBuf> {
    let mut dirs = Vec::new();
    if let Ok(appdata) = std::env::var("LOCALAPPDATA") {
        // Microsoft Store / official Python
        if let Ok(entries) = std::fs::read_dir(std::path::PathBuf::from(&appdata).join("Programs").join("Python")) {
            for entry in entries.flatten() {
                dirs.push(entry.path());
            }
        }
    }
    // Anaconda / Miniconda
    if let Ok(home) = std::env::var("USERPROFILE") {
        dirs.push(std::path::PathBuf::from(&home).join("anaconda3"));
        dirs.push(std::path::PathBuf::from(&home).join("AppData").join("Local").join("anaconda3"));
        dirs.push(std::path::PathBuf::from(&home).join("miniconda3"));
    }
    // system-wide
    dirs.push("C:\\Python311".into());
    dirs.push("C:\\Python312".into());
    dirs
}

fn sidecar_executable() -> Option<PathBuf> {
    let exe_name = if cfg!(windows) {
        "nightdiary-backend.exe"
    } else {
        "nightdiary-backend"
    };

    let current_exe = std::env::current_exe().ok();
    log_msg(&format!("[tauri] current_exe: {:?}", current_exe));

    // ONEDIR: prefer bundled resources/nightdiary-backend/ directory
    if let Some(ref exe) = current_exe {
        if let Some(parent) = exe.parent() {
            let resource_path = parent.join("resources").join("nightdiary-backend").join(exe_name);
            log_msg(&format!(
                "[tauri] checking onedir path: {} (exists={})",
                resource_path.display(),
                resource_path.exists()
            ));
            if resource_path.exists() {
                log_msg(&format!("[tauri] sidecar found at: {}", resource_path.display()));
                return Some(resource_path);
            }
        }
    }

    // Fallback: old externalBin layout (same dir as main exe)
    if let Some(ref exe) = current_exe {
        if let Some(parent) = exe.parent() {
            let fallback = parent.join(exe_name);
            log_msg(&format!(
                "[tauri] checking fallback path: {} (exists={})",
                fallback.display(),
                fallback.exists()
            ));
            if fallback.exists() {
                log_msg(&format!("[tauri] sidecar found at fallback: {}", fallback.display()));
                return Some(fallback);
            }
        }
    }

    log_msg("[tauri] ERROR: sidecar executable not found in any location!");
    None
}

/// Spawn the Python FastAPI sidecar on the given port and data directory.
pub fn spawn_backend(port: u16, data_dir: &str) -> Result<BackendProcess, String> {
    std::fs::create_dir_all(data_dir).map_err(|err| format!("create data dir: {err}"))?;

    let child = if cfg!(debug_assertions) {
        log_msg("[tauri] spawn mode: DEV (debug assertions enabled)");
        spawn_dev_backend(port, data_dir)?
    } else if let Some(sidecar) = sidecar_executable() {
        log_msg("[tauri] spawn mode: RELEASE (sidecar found)");
        spawn_release_backend(&sidecar, port, data_dir)?
    } else {
        log_msg("[tauri] spawn mode: DEV FALLBACK (no sidecar found, trying python)");
        spawn_dev_backend(port, data_dir)?
    };

    log_msg(&format!(
        "[tauri] backend process spawned (pid={}), waiting for /health on port {port}",
        child.id()
    ));

    Ok(BackendProcess { child })
}

fn spawn_dev_backend(port: u16, data_dir: &str) -> Result<Child, String> {
    let server = server_dir();
    if !server.join("app").join("main.py").exists() {
        return Err(format!(
            "server entry not found at {}",
            server.join("app").join("main.py").display()
        ));
    }

    let python = python_executable();
    log_msg(&format!(
        "[tauri] starting backend: {python} -m app.main --port {port} --data-dir {data_dir}"
    ));

    let mut child = Command::new(&python)
        .args([
            "-m",
            "app.main",
            "--port",
            &port.to_string(),
            "--data-dir",
            data_dir,
        ])
        .env("NO_PROXY", "127.0.0.1,localhost")
        .env("no_proxy", "127.0.0.1,localhost")
        .env("HTTP_PROXY", "")
        .env("HTTPS_PROXY", "")
        .env("PYTHONUNBUFFERED", "1")
        .current_dir(&server)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|err| format!("spawn python backend: {err}"))?;

    // Drain stderr in background so we can see Python errors
    if let Some(stderr) = child.stderr.take() {
        std::thread::spawn(move || {
            use std::io::BufRead;
            let reader = std::io::BufReader::new(stderr);
            for line in reader.lines() {
                if let Ok(line) = line {
                    log_msg(&format!("[python] {line}"));
                }
            }
        });
    }
    // Drain stdout to prevent pipe buffer from blocking the process
    if let Some(stdout) = child.stdout.take() {
        std::thread::spawn(move || {
            use std::io::BufRead;
            let reader = std::io::BufReader::new(stdout);
            for line in reader.lines() {
                if let Ok(line) = line {
                    log_msg(&format!("[python:out] {line}"));
                }
            }
        });
    }

    Ok(child)
}

fn spawn_release_backend(sidecar: &Path, port: u16, data_dir: &str) -> Result<Child, String> {
    log_msg(&format!(
        "[tauri] starting sidecar: {} --port {} --data-dir {}",
        sidecar.display(),
        port,
        data_dir
    ));

    let sidecar_dir = sidecar.parent().unwrap_or(Path::new(".")).to_path_buf();

    let mut child = match Command::new(sidecar)
        .args(["--port", &port.to_string(), "--data-dir", data_dir])
        .env("NO_PROXY", "127.0.0.1,localhost")
        .env("no_proxy", "127.0.0.1,localhost")
        .env("HTTP_PROXY", "")
        .env("HTTPS_PROXY", "")
        .env("PYTHONUNBUFFERED", "1")
        .current_dir(&sidecar_dir)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
    {
        Ok(c) => c,
        Err(err) => {
            log_msg(&format!("[tauri] FAILED to spawn sidecar: {err}"));
            return Err(format!("spawn sidecar binary: {err}"));
        }
    };
    log_msg(&format!("[tauri] sidecar process started (pid={})", child.id()));

    // Check if process exited immediately (crash detection)
    std::thread::sleep(Duration::from_millis(500));
    match child.try_wait() {
        Ok(Some(status)) => {
            log_msg(&format!(
                "[tauri] CRITICAL: sidecar exited immediately with code {status}"
            ));
            return Err(format!("sidecar exited immediately: {status}"));
        }
        Ok(None) => {
            log_msg("[tauri] sidecar process is running");
        }
        Err(err) => {
            log_msg(&format!("[tauri] failed to check sidecar status: {err}"));
        }
    }

    // Drain stderr/stdout in background to prevent pipe buffer from blocking
    if let Some(stderr) = child.stderr.take() {
        std::thread::spawn(move || {
            use std::io::BufRead;
            let reader = std::io::BufReader::new(stderr);
            for line in reader.lines() {
                if let Ok(line) = line {
                    log_msg(&format!("[python] {line}"));
                }
            }
        });
    }
    if let Some(stdout) = child.stdout.take() {
        std::thread::spawn(move || {
            use std::io::BufRead;
            let reader = std::io::BufReader::new(stdout);
            for line in reader.lines() {
                if let Ok(line) = line {
                    log_msg(&format!("[python:out] {line}"));
                }
            }
        });
    }

    Ok(child)
}

fn health_client() -> Result<reqwest::blocking::Client, String> {
    reqwest::blocking::Client::builder()
        .timeout(Duration::from_millis(300))
        .connect_timeout(Duration::from_millis(200))
        .no_proxy()
        .build()
        .map_err(|err| format!("create HTTP client: {err}"))
}

/// Single GET /health probe (used by Tauri invoke — bypasses WebView CORS).
pub fn health_check_once(port: u16) -> bool {
    let url = format!("http://127.0.0.1:{port}/health");
    let Ok(client) = health_client() else {
        return false;
    };
    client
        .get(&url)
        .send()
        .ok()
        .is_some_and(|response| response.status().is_success())
}

/// Poll GET /health until success or timeout.
pub fn health_poll(port: u16, app: Option<&tauri::AppHandle>) -> Result<(), String> {
    let client = health_client()?;
    let url = format!("http://127.0.0.1:{port}/health");
    log_msg(&format!(
        "[tauri] health_poll start: polling {} up to {} attempts ({}s timeout)",
        url,
        HEALTH_MAX_ATTEMPTS,
        HEALTH_MAX_ATTEMPTS as u64 * HEALTH_INTERVAL_MS / 1000
    ));

    for attempt in 1..=HEALTH_MAX_ATTEMPTS {
        if let Some(handle) = app {
            let _ = handle.emit("backend-startup-progress", attempt);
        }
        match client.get(&url).send() {
            Ok(response) if response.status().is_success() => {
                log_msg(&format!(
                    "[tauri] health_poll: OK on attempt {attempt}/{HEALTH_MAX_ATTEMPTS}"
                ));
                return Ok(());
            }
            Ok(response) => {
                if attempt <= 5 || attempt % 50 == 0 {
                    log_msg(&format!(
                        "backend health attempt {attempt}/{HEALTH_MAX_ATTEMPTS}: HTTP {}",
                        response.status()
                    ));
                }
            }
            Err(err) => {
                if attempt <= 5 || attempt % 50 == 0 {
                    log_msg(&format!(
                        "backend health attempt {attempt}/{HEALTH_MAX_ATTEMPTS}: {err}"
                    ));
                }
            }
        }
        std::thread::sleep(Duration::from_millis(HEALTH_INTERVAL_MS));
    }

    log_msg(&format!(
        "[tauri] health_poll: TIMED OUT after {} attempts",
        HEALTH_MAX_ATTEMPTS
    ));
    Err(format!(
        "backend health check timed out after {} ms",
        HEALTH_MAX_ATTEMPTS as u64 * HEALTH_INTERVAL_MS
    ))
}

/// Dev-only: port for attaching to a running `make dev-api` backend.
pub fn dev_backend_port() -> Option<u16> {
    if !cfg!(debug_assertions) {
        return None;
    }
    std::env::var("NIGHTDIARY_DEV_BACKEND")
        .ok()
        .and_then(|v| v.parse().ok())
        .or(Some(8000))
}

/// If a dev backend already listens on the configured port, return its port.
pub fn try_attach_dev_backend() -> Option<u16> {
    let port = dev_backend_port()?;
    if health_check_once(port) {
        log_msg(&format!("[tauri] attached to existing dev backend on port {port}"));
        Some(port)
    } else {
        None
    }
}

/// Ask the backend to shut down gracefully, then terminate the child process.
pub fn graceful_shutdown(port: u16, child: &mut Child) {
    let shutdown_url = format!("http://127.0.0.1:{port}/shutdown");
    let _ = reqwest::blocking::Client::builder()
        .timeout(Duration::from_secs(1))
        .no_proxy()
        .build()
        .and_then(|client| client.post(&shutdown_url).send());

    std::thread::sleep(Duration::from_secs(SHUTDOWN_GRACE_SECS));

    let _ = child.kill();
    let _ = child.wait();
}
