//! Local backup/restore under `{data_dir}/backups/`.
//!
//! Each backup consists of a `.db` file (SQLite database) and an optional
//! `.chroma/` companion directory (ChromaDB vector index).  Both must be
//! backed up together — without the vector index, AI semantic retrieval stops
//! working after a restore.
//!
//! Old backups are pruned automatically: only the most recent `MAX_BACKUPS`
//! entries are kept.

use std::fs;
use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

use tauri::State;

use crate::AppState;

/// Maximum number of backup files to retain.
const MAX_BACKUPS: usize = 20;

fn backups_dir(data_dir: &str) -> PathBuf {
    PathBuf::from(data_dir).join("backups")
}

fn db_path(data_dir: &str) -> PathBuf {
    PathBuf::from(data_dir).join("night_diary.db")
}

fn chroma_dir(data_dir: &str) -> PathBuf {
    PathBuf::from(data_dir).join("chroma_data")
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

/// Recursively copy a directory tree from `src` to `dst`.
/// Returns `Ok(())` on success, or the first `io::Error` encountered.
fn copy_dir_recursive(src: &Path, dst: &Path) -> std::io::Result<()> {
    if !src.is_dir() {
        return Ok(());
    }
    fs::create_dir_all(dst)?;
    for entry in fs::read_dir(src)? {
        let entry = entry?;
        let file_type = entry.file_type()?;
        let src_path = entry.path();
        let dst_path = dst.join(entry.file_name());
        if file_type.is_dir() {
            copy_dir_recursive(&src_path, &dst_path)?;
        } else {
            fs::copy(&src_path, &dst_path)?;
        }
    }
    Ok(())
}

/// Copy the ChromaDB vector index alongside a `.db` backup.
/// Creates `{backup_filename}.chroma/` next to the `.db` file.
fn backup_chroma(data_dir: &str, backup_dir: &Path, backup_filename: &str) {
    let src = chroma_dir(data_dir);
    if !src.is_dir() {
        return; // no chroma data to back up
    }
    let chroma_name = format!("{}.chroma", backup_filename.trim_end_matches(".db"));
    let dest = backup_dir.join(&chroma_name);
    let _ = copy_dir_recursive(&src, &dest);
}

/// Restore the ChromaDB vector index from a `.chroma/` companion directory.
fn restore_chroma(data_dir: &str, backup_dir: &Path, backup_filename: &str) {
    let chroma_name = format!("{}.chroma", backup_filename.trim_end_matches(".db"));
    let src = backup_dir.join(&chroma_name);
    if !src.is_dir() {
        return; // no chroma companion — legacy backup or chroma didn't exist
    }
    let dest = chroma_dir(data_dir);
    // Remove existing chroma_data before overwriting
    let _ = fs::remove_dir_all(&dest);
    let _ = copy_dir_recursive(&src, &dest);
}

/// Prune old backups beyond `MAX_BACKUPS`, keeping the most recent ones.
/// Also removes orphaned `.chroma/` companion directories.
fn rotate_backups(dir: &Path) {
    let mut names: Vec<String> = match fs::read_dir(dir) {
        Ok(entries) => entries
            .filter_map(|e| e.ok())
            .map(|e| e.file_name().to_string_lossy().into_owned())
            .filter(|n| n.ends_with(".db"))
            .collect(),
        Err(_) => return,
    };
    names.sort_by(|a, b| b.cmp(a)); // newest first

    if names.len() <= MAX_BACKUPS {
        return;
    }

    for old_name in names.into_iter().skip(MAX_BACKUPS) {
        let db_file = dir.join(&old_name);
        let _ = fs::remove_file(&db_file);
        // Remove chroma companion
        let chroma_name = format!("{}.chroma", old_name.trim_end_matches(".db"));
        let chroma_path = dir.join(&chroma_name);
        if chroma_path.is_dir() {
            let _ = fs::remove_dir_all(&chroma_path);
        }
    }
}

/// Copy ``night_diary.db`` (and chroma_data) to ``backups/`` on exit (best-effort).
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
    backup_chroma(data_dir, &dir, &filename);
    rotate_backups(&dir);
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

    // Back up ChromaDB vector index alongside the SQLite file.
    backup_chroma(&state.data_dir, &dir, &filename);

    // Prune old backups to prevent unlimited growth.
    rotate_backups(&dir);

    Ok(filename)
}

#[tauri::command]
pub fn restore_backup(state: State<'_, AppState>, filename: String) -> Result<(), String> {
    if filename.contains('/') || filename.contains('\\') || !filename.ends_with(".db") {
        return Err("无效的备份文件名".into());
    }

    let dir = backups_dir(&state.data_dir);
    let src = dir.join(&filename);
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

    // Restore ChromaDB vector index from companion directory if it exists.
    restore_chroma(&state.data_dir, &dir, &filename);

    Ok(())
}
