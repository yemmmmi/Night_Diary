//! Local SQLite backup/restore under `{data_dir}/backups/`.

use std::fs;
use std::path::PathBuf;
use std::time::{SystemTime, UNIX_EPOCH};

use tauri::State;

use crate::AppState;

fn backups_dir(data_dir: &str) -> PathBuf {
    PathBuf::from(data_dir).join("backups")
}

fn db_path(data_dir: &str) -> PathBuf {
    PathBuf::from(data_dir).join("night_diary.db")
}

fn backup_stamp() -> String {
    let secs = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0);
    format!("backup-{secs}.db")
}

/// Auto backup filename per E-1 spec: ``YYYY-MM-DDTHHmmss-auto.db``.
fn auto_backup_stamp() -> String {
    let now = chrono::Local::now();
    format!("{}-auto.db", now.format("%Y-%m-%dT%H%M%S"))
}

/// Copy ``night_diary.db`` to ``backups/`` on application exit (best-effort).
pub fn auto_backup_on_exit(data_dir: &str) -> Option<String> {
    let src = db_path(data_dir);
    if !src.is_file() {
        return None;
    }

    let dir = backups_dir(data_dir);
    if fs::create_dir_all(&dir).is_err() {
        return None;
    }

    let filename = auto_backup_stamp();
    let dest = dir.join(&filename);
    fs::copy(&src, &dest).ok()?;
    Some(filename)
}

#[tauri::command]
pub fn list_backups(state: State<'_, AppState>) -> Result<Vec<String>, String> {
    let dir = backups_dir(&state.data_dir);
    if !dir.exists() {
        return Ok(vec![]);
    }

    let mut names: Vec<String> = fs::read_dir(&dir)
        .map_err(|e| e.to_string())?
        .filter_map(|entry| entry.ok())
        .map(|entry| entry.file_name().to_string_lossy().into_owned())
        .filter(|name| name.ends_with(".db"))
        .collect();
    names.sort_by(|a, b| b.cmp(a));
    Ok(names)
}

#[tauri::command]
pub fn create_backup(state: State<'_, AppState>) -> Result<String, String> {
    let src = db_path(&state.data_dir);
    if !src.exists() {
        return Err("数据库文件不存在，请先写一篇日记".into());
    }

    let dir = backups_dir(&state.data_dir);
    fs::create_dir_all(&dir).map_err(|e| e.to_string())?;

    let filename = backup_stamp();
    let dest = dir.join(&filename);
    fs::copy(&src, &dest).map_err(|e| format!("备份失败：{e}"))?;
    Ok(filename)
}

#[tauri::command]
pub fn restore_backup(state: State<'_, AppState>, filename: String) -> Result<(), String> {
    if filename.contains('/') || filename.contains('\\') || !filename.ends_with(".db") {
        return Err("无效的备份文件名".into());
    }

    let src = backups_dir(&state.data_dir).join(&filename);
    if !src.is_file() {
        return Err("备份文件不存在".into());
    }

    let dest = db_path(&state.data_dir);
    if let Some(parent) = dest.parent() {
        fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    }

    let temp = dest.with_extension("db.restore-tmp");
    fs::copy(&src, &temp).map_err(|e| format!("恢复失败：{e}"))?;
    fs::rename(&temp, &dest).map_err(|e| format!("恢复失败：{e}"))?;
    Ok(())
}
