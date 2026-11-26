"""Eject the card through the operating system so it can be removed safely."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

BUSY_HINT = (
    "The card is still in use by another program, for example a file manager window or a terminal"
    " that shows a folder on the card. Close it and try again."
)
FALLBACK_HINT = "Eject the card in your file manager instead."


class EjectError(Exception):
    pass


def eject(card_root: Path) -> None:
    """Flush all writes and eject the drive whose mount point is card_root."""
    if hasattr(os, "sync"):
        os.sync()
    if sys.platform == "win32":
        _eject_windows(card_root)
    elif sys.platform == "darwin":
        _eject_macos(card_root)
    else:
        _eject_linux(card_root)


def _run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, timeout=60, check=False)


def _failure(result: subprocess.CompletedProcess) -> EjectError:
    output = (result.stderr or result.stdout).strip()
    if "busy" in output.casefold():
        return EjectError(BUSY_HINT)
    if "not authorized" in output.casefold():
        return EjectError(f"Your system does not allow blackbook to eject the card. {FALLBACK_HINT}")
    return EjectError(f"{output or 'unknown error'}. {FALLBACK_HINT}")


def _unescape_mount(field: str) -> str:
    # /proc/mounts escapes space, tab, newline and backslash as octal
    for code, char in (("\\040", " "), ("\\011", "\t"), ("\\012", "\n"), ("\\134", "\\")):
        field = field.replace(code, char)
    return field


def mount_device(mount_point: Path, mounts_text: str) -> str | None:
    """Device mounted exactly at mount_point according to /proc/mounts content."""
    target = str(mount_point)
    device = None
    for line in mounts_text.splitlines():
        fields = line.split()
        if len(fields) >= 2 and _unescape_mount(fields[1]) == target:
            device = _unescape_mount(fields[0])
    return device


def _eject_linux(card_root: Path) -> None:
    root = card_root.resolve()
    try:
        mounts = Path("/proc/self/mounts").read_text()
    except OSError as exc:
        raise EjectError(f"cannot read the list of drives: {exc}. {FALLBACK_HINT}") from exc
    device = mount_device(root, mounts)
    if device is None or not device.startswith("/dev/"):
        raise EjectError(f"{root} is not a separate drive, there is nothing to eject.")

    udisksctl = shutil.which("udisksctl")
    if udisksctl:
        # --no-user-interaction: never open a password prompt, report the refusal instead
        result = _run([udisksctl, "unmount", "--no-user-interaction", "--block-device", device])
        if result.returncode != 0:
            raise _failure(result)
        # Some built-in card readers cannot be powered off, the card is safe to remove anyway
        _run([udisksctl, "power-off", "--no-user-interaction", "--block-device", device])
        return
    gio = shutil.which("gio")
    if gio:
        result = _run([gio, "mount", "--eject", str(root)])
        if result.returncode != 0:
            raise _failure(result)
        return
    raise EjectError(f"neither udisksctl nor gio is installed. {FALLBACK_HINT}")


def _eject_macos(card_root: Path) -> None:
    root = card_root.resolve()
    if root.parent != Path("/Volumes") or not os.path.ismount(root):
        raise EjectError(f"{root} is not a separate drive, there is nothing to eject.")
    result = _run(["diskutil", "eject", str(root)])
    if result.returncode != 0:
        raise _failure(result)


def _eject_windows(card_root: Path) -> None:
    import ctypes
    from ctypes import wintypes

    drive = card_root.drive.rstrip("\\").upper()
    if len(drive) != 2 or drive[1] != ":" or Path(card_root).resolve() != Path(drive + "\\"):
        raise EjectError(f"{card_root} is not a separate drive, there is nothing to eject.")
    if drive == os.environ.get("SystemDrive", "C:").upper():
        raise EjectError(f"{drive} is the system drive, it cannot be ejected.")

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateFileW.restype = wintypes.HANDLE
    kernel32.CreateFileW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
        wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
    ]
    kernel32.DeviceIoControl.restype = wintypes.BOOL
    kernel32.DeviceIoControl.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD,
        wintypes.LPVOID, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID,
    ]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

    generic_read, generic_write = 0x80000000, 0x40000000
    share_read, share_write = 0x1, 0x2
    open_existing = 3
    fsctl_lock_volume = 0x00090018
    fsctl_dismount_volume = 0x00090020
    ioctl_storage_media_removal = 0x002D4804
    ioctl_storage_eject_media = 0x002D4808
    invalid_handle = wintypes.HANDLE(-1).value

    handle = kernel32.CreateFileW(
        f"\\\\.\\{drive}", generic_read | generic_write, share_read | share_write, None, open_existing, 0, None
    )
    if handle == invalid_handle:
        raise EjectError(f"cannot open drive {drive} (error {ctypes.get_last_error()}). {FALLBACK_HINT}")

    returned = wintypes.DWORD()

    def control(code: int, buffer=None, size: int = 0) -> bool:
        return bool(kernel32.DeviceIoControl(handle, code, buffer, size, None, 0, ctypes.byref(returned), None))

    try:
        for _ in range(20):
            if control(fsctl_lock_volume):
                break
            time.sleep(0.5)
        else:
            raise EjectError(BUSY_HINT)
        if not control(fsctl_dismount_volume):
            raise EjectError(f"cannot dismount drive {drive} (error {ctypes.get_last_error()}). {FALLBACK_HINT}")
        allow_removal = ctypes.c_bool(False)
        control(ioctl_storage_media_removal, ctypes.byref(allow_removal), ctypes.sizeof(allow_removal))
        # Card readers without an eject mechanism refuse this, the volume is dismounted anyway
        control(ioctl_storage_eject_media)
    finally:
        kernel32.CloseHandle(handle)
