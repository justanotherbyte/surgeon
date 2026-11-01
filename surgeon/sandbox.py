"""Run a sub-app script with no sockets, no writes outside one directory, and no signals.

usage: /usr/bin/python3 -I sandbox.py <writable_dir> <script> [args...]

Ubuntu 24.04 blocks user namespaces for unconfined processes, so bwrap can't run from Surgeon's
daemon. Landlock and seccomp need no namespaces and no root:
- Landlock denies every filesystem write except under <writable_dir>. Reads stay allowed.
- seccomp makes socket() fail, which closes the session bus, X11, TCP and every socket file,
  and makes kill/tkill/tgkill/pidfd_send_signal/ptrace/process_vm_writev fail.
Standalone on purpose: it must not import Surgeon's package or anything from the cwd.
"""
import ctypes
import errno
import os
import runpy
import sys

libc = ctypes.CDLL(None, use_errno=True)
libc.syscall.restype = ctypes.c_long

SYS_LANDLOCK_CREATE_RULESET, SYS_LANDLOCK_ADD_RULE, SYS_LANDLOCK_RESTRICT_SELF = 444, 445, 446
PR_SET_NO_NEW_PRIVS = 38
# Landlock write rights: WRITE_FILE, REMOVE_DIR, REMOVE_FILE, MAKE_CHAR, MAKE_DIR, MAKE_REG,
# MAKE_SOCK, MAKE_FIFO, MAKE_BLOCK, MAKE_SYM, then REFER (ABI 2) and TRUNCATE (ABI 3).
WRITE_RIGHTS = (1 << 1) | sum(1 << b for b in range(4, 13))
BLOCKED = {"socket": errno.EACCES, "kill": errno.EPERM, "tkill": errno.EPERM, "tgkill": errno.EPERM,
           "pidfd_send_signal": errno.EPERM, "ptrace": errno.EPERM, "process_vm_writev": errno.EPERM}


class PathBeneath(ctypes.Structure):
    _pack_ = 1
    _fields_ = [("allowed_access", ctypes.c_uint64), ("parent_fd", ctypes.c_int32)]


def fail(msg):
    sys.stderr.write(f"sandbox: {msg}\n")
    sys.exit(3)  # never fall back to running the script unsandboxed


def landlock(writable):
    abi = libc.syscall(SYS_LANDLOCK_CREATE_RULESET, None, ctypes.c_size_t(0), ctypes.c_uint32(1))
    if abi < 1:
        fail("Landlock is not available")
    rights = WRITE_RIGHTS | (1 << 13 if abi >= 2 else 0) | (1 << 14 if abi >= 3 else 0)
    handled = ctypes.c_uint64(rights)  # struct landlock_ruleset_attr, first field only
    rs = libc.syscall(SYS_LANDLOCK_CREATE_RULESET, ctypes.byref(handled), ctypes.c_size_t(8), ctypes.c_uint32(0))
    if rs < 0:
        fail(f"landlock_create_ruleset: {os.strerror(ctypes.get_errno())}")
    fd = os.open(writable, os.O_PATH | os.O_CLOEXEC)
    rule = PathBeneath(rights, fd)
    if libc.syscall(SYS_LANDLOCK_ADD_RULE, ctypes.c_int(rs), ctypes.c_int(1), ctypes.byref(rule), ctypes.c_uint32(0)):
        fail(f"landlock_add_rule: {os.strerror(ctypes.get_errno())}")
    if libc.prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0):
        fail("prctl(NO_NEW_PRIVS) failed")
    if libc.syscall(SYS_LANDLOCK_RESTRICT_SELF, ctypes.c_int(rs), ctypes.c_uint32(0)):
        fail(f"landlock_restrict_self: {os.strerror(ctypes.get_errno())}")
    os.close(fd)
    os.close(rs)


def seccomp():
    sc = ctypes.CDLL("libseccomp.so.2")
    sc.seccomp_init.restype = ctypes.c_void_p
    sc.seccomp_init.argtypes = [ctypes.c_uint32]
    sc.seccomp_rule_add.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int, ctypes.c_uint]
    sc.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
    sc.seccomp_load.argtypes = [ctypes.c_void_p]
    ctx = sc.seccomp_init(0x7FFF0000)  # SCMP_ACT_ALLOW
    if not ctx:
        fail("seccomp_init failed")
    for name, err in BLOCKED.items():
        nr = sc.seccomp_syscall_resolve_name(name.encode())
        if sc.seccomp_rule_add(ctx, 0x00050000 | err, nr, 0):  # SCMP_ACT_ERRNO(err)
            fail(f"seccomp_rule_add {name} failed")
    if sc.seccomp_load(ctx):
        fail("seccomp_load failed")


def main():
    if len(sys.argv) < 3:
        fail("usage: sandbox.py <writable_dir> <script> [args...]")
    writable, script, args = sys.argv[1], sys.argv[2], sys.argv[3:]
    os.closerange(3, 1024)  # inherited sockets would survive the socket() block
    landlock(writable)
    seccomp()
    sys.argv = [script, *args]
    sys.path[0] = os.path.dirname(os.path.abspath(script))
    runpy.run_path(script, run_name="__main__")


if __name__ == "__main__":
    main()
