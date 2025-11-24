// Copyright 2025 Pants project contributors (see CONTRIBUTORS.md).
// Licensed under the Apache License, Version 2.0 (see LICENSE).

use std::fs;
use std::io::{self, ErrorKind};
use std::os::unix::fs::PermissionsExt;
use std::path::{Path, PathBuf};
use std::sync::Arc;

use async_trait::async_trait;

use crate::directory::SymlinkBehavior;
use crate::gitignore::GitignoreStyleExcludes;
use crate::{Dir, DirectoryListing, File, Link, PathMetadata, PathMetadataKind, Stat, Vfs};

#[derive(Clone)]
pub struct WinFS {
    root: Dir,
    ignore: Arc<GitignoreStyleExcludes>,
    executor: task_executor::Executor,
    symlink_behavior: SymlinkBehavior,
}

// Non-public functions used internally by the public functions below.
impl WinFS {
    pub fn new<P: AsRef<Path>>(
        root: P,
        ignorer: Arc<GitignoreStyleExcludes>,
        executor: task_executor::Executor,
    ) -> Result<Self, String> {
        Self::new_with_symlink_behavior(root, ignorer, executor, SymlinkBehavior::Aware)
    }

    pub fn new_with_symlink_behavior<P: AsRef<Path>>(
        root: P,
        ignorer: Arc<GitignoreStyleExcludes>,
        executor: task_executor::Executor,
        symlink_behavior: SymlinkBehavior,
    ) -> Result<Self, String> {
        let root: &Path = root.as_ref();
        let canonical_root = root
            .canonicalize()
            .and_then(|canonical| {
                canonical.metadata().and_then(|metadata| {
                    if metadata.is_dir() {
                        Ok(Dir(canonical))
                    } else {
                        Err(io::Error::new(
                            io::ErrorKind::InvalidInput,
                            "Not a directory.",
                        ))
                    }
                })
            })
            .map_err(|e| format!("Could not canonicalize root {root:?}: {e:?}"))?;

        Ok(Self {
            root: canonical_root,
            ignore: ignorer,
            executor: executor,
            symlink_behavior: symlink_behavior,
        })
    }
}

// Public functions used externally.
impl WinFS {
    pub async fn scandir(&self, dir_relative_to_root: Dir) -> Result<DirectoryListing, io::Error> {
        let vfs = self.clone();
        self.executor
            .spawn_blocking(move || vfs.scandir_sync(&dir_relative_to_root))
            .await?
            .map_err(|e| io::Error::other(format!("Synchronous scandir failed: {e}")))
    }

    pub fn is_ignored(&self, stat: &Stat) -> bool {
        self.ignore.is_ignored(stat)
    }

    pub fn file_path(&self, file: &File) -> PathBuf {
        self.root.0.join(&file.path)
    }

    pub async fn read_link(&self, link: &Link) -> Result<PathBuf, io::Error> {
        let link_parent = link.path.parent().map(Path::to_owned);
        let link_abs = self.root.0.join(link.path.as_path());
        tokio::fs::read_link(&link_abs)
            .await
            .and_then(|path_buf| {
                if path_buf.is_absolute() {
                    Err(io::Error::new(
                        io::ErrorKind::InvalidData,
                        format!("Absolute symlink: {path_buf:?}"),
                    ))
                } else {
                    link_parent
                        .map(|parent| parent.join(&path_buf))
                        .ok_or_else(|| {
                            io::Error::new(
                                io::ErrorKind::InvalidData,
                                format!("Symlink without a parent?: {path_buf:?}"),
                            )
                        })
                }
            })
            .map_err(|e| io::Error::new(e.kind(), format!("Failed to read link {link_abs:?}: {e}")))
    }

    ///
    /// Returns a Stat relative to its containing directory.
    ///
    /// NB: This method is synchronous because it is used to stat all files in a directory as one
    /// blocking operation as part of `scandir_sync` (as recommended by the `tokio` documentation, to
    /// avoid many small spawned tasks).
    ///
    pub fn stat_sync(&self, relative_path: &Path) -> Result<Option<Stat>, io::Error> {
        if cfg!(debug_assertions) && relative_path.is_absolute() {
            return Err(io::Error::new(
                io::ErrorKind::InvalidInput,
                format!(
                    "Argument relative_path to PosixFS::stat_sync must be relative path, got {relative_path:?}"
                ),
            ));
        }
        let abs_path = self.root.0.join(relative_path);
        let metadata = match self.symlink_behavior {
            SymlinkBehavior::Aware => fs::symlink_metadata(&abs_path),
            SymlinkBehavior::Oblivious => fs::metadata(&abs_path),
        };
        metadata
            .and_then(|metadata| {
                PosixFS::stat_internal(&abs_path, metadata.file_type(), || Ok(metadata))
            })
            .or_else(|err| match err.kind() {
                io::ErrorKind::NotFound => Ok(None),
                _ => Err(err),
            })
    }

    pub async fn path_metadata(&self, path: PathBuf) -> Result<Option<PathMetadata>, io::Error> {
        let abs_path = self.root.0.join(&path);
        match tokio::fs::symlink_metadata(&abs_path).await {
            Ok(metadata) => {
                let (kind, symlink_target) = match metadata.file_type() {
                    ft if ft.is_symlink() => {
                        let symlink_target = tokio::fs::read_link(&abs_path).await.map_err(|e| io::Error::other(format!("path {abs_path:?} was previously a symlink but read_link failed: {e}")))?;
                        (PathMetadataKind::Symlink, Some(symlink_target))
                    }
                    ft if ft.is_dir() => (PathMetadataKind::Directory, None),
                    ft if ft.is_file() => (PathMetadataKind::File, None),
                    _ => unreachable!("std::fs::FileType was not a symlink, directory, or file"),
                };

                #[cfg(target_family = "unix")]
                let (unix_mode, is_executable) = {
                    let mode = metadata.permissions().mode();
                    (Some(mode), (mode & 0o111) != 0)
                };

                Ok(Some(PathMetadata {
                    path,
                    kind,
                    length: metadata.len(),
                    is_executable,
                    unix_mode,
                    accessed: metadata.accessed().ok(),
                    created: metadata.created().ok(),
                    modified: metadata.modified().ok(),
                    symlink_target,
                }))
            }
            Err(err) if err.kind() == ErrorKind::NotFound => Ok(None),
            Err(err) => Err(err),
        }
    }
}

#[async_trait]
impl Vfs<io::Error> for Arc<WinFS> {
    async fn read_link(&self, link: &Link) -> Result<PathBuf, io::Error> {
        PosixFS::read_link(self, link).await
    }

    async fn scandir(&self, dir: Dir) -> Result<Arc<DirectoryListing>, io::Error> {
        Ok(Arc::new(WinFS::scandir(self, dir).await?))
    }

    async fn path_metadata(&self, path: PathBuf) -> Result<Option<PathMetadata>, io::Error> {
        WinFS::path_metadata(self, path).await
    }

    fn is_ignored(&self, stat: &Stat) -> bool {
        WinFS::is_ignored(self, stat)
    }

    fn mk_error(msg: &str) -> io::Error {
        io::Error::other(msg)
    }
}
