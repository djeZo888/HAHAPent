"""Durable JSON, directory ownership and conservative transaction primitives."""

import hashlib
import json
import os
import re
import shutil
import stat
import uuid
from pathlib import Path

from .catalog import ManagerError, load_catalog, validate_document
from .downloads import MAX_EXTRACT_BYTES, MAX_FILES


def no_symlink(path):
    path = Path(path)
    if path.is_symlink():
        raise ManagerError("unsafe_filesystem_path")
    for parent in path.parents:
        if parent.is_symlink():
            raise ManagerError("unsafe_filesystem_path")


def fsync_dir(path):
    descriptor = os.open(str(path), os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_json(path, value):
    path = Path(path)
    no_symlink(path)
    data = (json.dumps(value, ensure_ascii=True, indent=2, allow_nan=False) + "\n").encode()
    temporary = path.with_name("." + path.name + "." + uuid.uuid4().hex)
    try:
        descriptor = os.open(str(temporary), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(str(temporary), str(path))
        fsync_dir(path.parent)
    finally:
        if temporary.exists():
            temporary.unlink()


def read_document(path, kind, default=None):
    no_symlink(path)
    try:
        value = load_catalog(path)
    except FileNotFoundError:
        if default is None:
            raise ManagerError("missing_" + kind) from None
        value = default
    except (OSError, ValueError, RecursionError):
        raise ManagerError("invalid_" + kind) from None
    return validate_document(value, kind)


def hash_tree(path):
    path = Path(path)
    no_symlink(path)
    if not path.is_dir():
        raise ManagerError("ownership_conflict")
    result, total, nodes = {}, 0, 0
    for root, directories, files in os.walk(str(path), followlinks=False):
        for name in sorted(directories + files):
            child = Path(root) / name
            relative = child.relative_to(path).as_posix()
            metadata = child.lstat()
            nodes += 1
            if nodes > MAX_FILES * 2:
                raise ManagerError("ownership_conflict")
            if not re.fullmatch(r"[A-Za-z0-9_./-]+", relative) or stat.S_ISLNK(metadata.st_mode):
                raise ManagerError("ownership_conflict")
            parts = child.relative_to(path).parts
            if "__pycache__" in parts:
                cache_index = parts.index("__pycache__")
                if stat.S_ISDIR(metadata.st_mode):
                    if cache_index != len(parts) - 1:
                        raise ManagerError("ownership_conflict")
                    continue
                match = re.fullmatch(
                    r"([A-Za-z0-9_]+)\.cpython-[0-9]{2,3}(?:\.opt-[12])?\.pyc", name
                )
                if not stat.S_ISREG(metadata.st_mode) or cache_index != len(parts) - 2 or not match:
                    raise ManagerError("ownership_conflict")
                source = child.parent.parent / (match.group(1) + ".py")
                if not source.is_file() or source.is_symlink():
                    raise ManagerError("ownership_conflict")
                continue
            if stat.S_ISDIR(metadata.st_mode):
                result[relative + "/"] = "directory"
            elif stat.S_ISREG(metadata.st_mode):
                total += metadata.st_size
                if total > MAX_EXTRACT_BYTES:
                    raise ManagerError("ownership_conflict")
                digest = hashlib.sha256()
                with child.open("rb") as stream:
                    for block in iter(lambda: stream.read(65536), b""):
                        digest.update(block)
                result[relative] = digest.hexdigest()
            else:
                raise ManagerError("ownership_conflict")
            if len(result) > MAX_FILES:
                raise ManagerError("ownership_conflict")
    return result


def verify_tree(path, expected):
    if hash_tree(path) != expected:
        raise ManagerError("ownership_conflict")


def sync_tree(path):
    for root, _directories, files in os.walk(str(path)):
        for name in files:
            with (Path(root) / name).open("rb") as stream:
                os.fsync(stream.fileno())
        fsync_dir(root)


def copy_owned(source, destination, expected):
    verify_tree(source, expected)
    no_symlink(destination)
    if destination.exists():
        raise ManagerError("backup_conflict")
    shutil.copytree(
        str(source), str(destination), symlinks=False, ignore=shutil.ignore_patterns("__pycache__")
    )
    verify_tree(destination, expected)
    sync_tree(destination)
    fsync_dir(Path(destination).parent)


def remove_owned(path, expected):
    verify_tree(path, expected)
    shutil.rmtree(str(path))
    fsync_dir(Path(path).parent)
