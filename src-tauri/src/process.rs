//! Python sidecar lifecycle: spawn, health polling, graceful shutdown.

use std::net::TcpListener;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::time::Duration;

const HEALTH_INTERVAL_MS: u64 = 200;
const HEALTH_MAX_ATTEMPTS: u32 = 150;
const SHUTDOWN_GRACE_SECS: u64 = 3;

pub struct BackendProcess {
    child: Child,
}

impl BackendProcess {
    pub fn child_mut(&mut self) -> &mut Child {
        &mut self.child
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

    std::env::current_exe()
        .ok()
        .and_then(|path| path.parent().map(|dir| dir.join(exe_name)))
        .filter(|path| path.exists())
}

/// Spawn the Python FastAPI sidecar on the given port and data directory.
pub fn spawn_backend(port: u16, data_dir: &str) -> Result<BackendProcess, String> {
    std::fs::create_dir_all(data_dir).map_err(|err| format!("create data dir: {err}"))?;

    let child = if cfg!(debug_assertions) {
        spawn_dev_backend(port, data_dir)?
    } else if let Some(sidecar) = sidecar_executable() {
        spawn_release_backend(&sidecar, port, data_dir)?
    } else {
        spawn_dev_backend(port, data_dir)?
    };

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
    eprintln!("[tauri] starting backend: {python} -m app.main --port {port} --data-dir {data_dir}");

    let mut child = Command::new(&python)
        .args([
            "-m",
            "app.main",
            "--port",
            &port.to_string(),
            "--data-dir",
            data_dir,
        ])
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
                    eprintln!("[python] {line}");
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
                    eprintln!("[python:out] {line}");
                }
            }
        });
    }

    Ok(child)
}

fn spawn_release_backend(sidecar: &Path, port: u16, data_dir: &str) -> Result<Child, String> {
    Command::new(sidecar)
        .args(["--port", &port.to_string(), "--data-dir", data_dir])
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|err| format!("spawn sidecar binary: {err}"))
}

/// Poll GET /health until success or timeout.
pub fn health_poll(port: u16) -> Result<(), String> {
    let url = format!("http://127.0.0.1:{port}/health");
    let client = reqwest::blocking::Client::builder()
        .timeout(Duration::from_millis(500))
        .no_proxy()
        .build()
        .map_err(|err| format!("create HTTP client: {err}"))?;

    for attempt in 1..=HEALTH_MAX_ATTEMPTS {
        match client.get(&url).send() {
            Ok(response) if response.status().is_success() => return Ok(()),
            Ok(response) => eprintln!(
                "backend health attempt {attempt}/{HEALTH_MAX_ATTEMPTS}: HTTP {}",
                response.status()
            ),
            Err(err) => eprintln!(
                "backend health attempt {attempt}/{HEALTH_MAX_ATTEMPTS}: {err}"
            ),
        }
        std::thread::sleep(Duration::from_millis(HEALTH_INTERVAL_MS));
    }

    Err(format!(
        "backend health check timed out after {} ms",
        HEALTH_MAX_ATTEMPTS as u64 * HEALTH_INTERVAL_MS
    ))
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
