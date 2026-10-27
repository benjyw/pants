// Copyright 2022 Pants project contributors (see CONTRIBUTORS.md).
// Licensed under the Apache License, Version 2.0 (see LICENSE).
use std::path::Path;

use crate::{RelativePath, path_to_slash, path_to_slash_lossy};

#[test]
fn relative_path_ok() {
    assert_eq!(Some("a"), RelativePath::new("a").unwrap().to_str());
    assert_eq!(Some("a"), RelativePath::new("./a").unwrap().to_str());
    assert_eq!(Some("a"), RelativePath::new("b/../a").unwrap().to_str());
    assert_eq!(
        Some("a/c"),
        RelativePath::new("b/../a/././c").unwrap().to_str()
    );
}

#[test]
fn relative_path_err() {
    assert!(RelativePath::new("../a").is_err());
    assert!(RelativePath::new("/a").is_err());
}

#[test]
fn relative_path_normalize() {
    assert_eq!(Some("a"), RelativePath::new("a/").unwrap().to_str());
    assert_eq!(Some(""), RelativePath::new(".").unwrap().to_str());
}

#[test]
fn relative_path_join() {
    let a = RelativePath::new("a").unwrap();
    let bc = RelativePath::new("b/c").unwrap();
    assert_eq!(Some("a/b/c"), a.join(bc.clone()).to_str());
    assert_eq!(Some("b/c"), RelativePath::empty().join(bc.clone()).to_str());
    assert_eq!(Some("a"), a.join(RelativePath::empty()).to_str());
}

#[cfg(windows)]
#[test]
fn relative_path_windows_separators() {
    assert_eq!(
        Some("a/c"),
        RelativePath::new(r"b\..\a\c").unwrap().to_str()
    );
    assert_eq!(Some("a/b/c"), RelativePath::new(r"a\b/c").unwrap().to_str());
    assert!(RelativePath::new(r"C:\a").is_err());
    assert!(RelativePath::new(r"\a").is_err());
}

#[test]
fn path_to_slash_unchanged() {
    assert_eq!(Some("a/b/c"), path_to_slash(Path::new("a/b/c")).as_deref());
    assert_eq!("a/b/c", path_to_slash_lossy(Path::new("a/b/c")));
}

#[test]
fn path_to_slash_joined() {
    // On Windows, `join` inserts `\\`.
    let joined = Path::new("a").join("b").join("c");
    assert_eq!(Some("a/b/c"), path_to_slash(&joined).as_deref());
    assert_eq!("a/b/c", path_to_slash_lossy(&joined));
}

// On unix, `\\` is an ordinary file name character, and must be preserved.
#[cfg(unix)]
#[test]
fn path_to_slash_preserves_backslash_on_unix() {
    assert_eq!(Some(r"a\b"), path_to_slash(Path::new(r"a\b")).as_deref());
}
