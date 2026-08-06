"""Running install scripts inside a freshly created container.

Proxmox exposes no exec endpoint for LXC guests, so this goes over SSH to the
*node* and uses `pct push` + `pct exec` — the script is uploaded as a file
rather than interpolated into a command line, so quoting inside the script can
never change the command being run.

Output is streamed line by line into the job log as it happens: a 4,000-line
apt install that only appears once it finishes is not a log, it is a receipt.
"""
from __future__ import annotations

import importlib.util
import re
import shlex
from pathlib import Path
from typing import Callable, Iterable

# a script can legitimately take a long time (GitLab's reconfigure is minutes)
DEFAULT_TIMEOUT = 1800

# CSI/OSC sequences and the braille spinner frames npm and apt emit under a PTY.
# The log pane renders text, not a terminal, so these would appear as literal
# noise like "[1G[0K⠦" around every progress update.
_ANSI = re.compile(
    "\x1b\\[[0-9;?]*[ -/]*[@-~]"              # CSI: colour, cursor moves, erase
    "|\x1b\\][^\x07\x1b]*(?:\x07|\x1b\\\\)"   # OSC: window title and friends
    "|\x1b."                                  # anything else two-char, e.g. ESC 7
)
# dpkg draws its progress bar between save-cursor and restore-cursor, then puts
# the real message after it. The whole overlay is transient, so drop it and keep
# what follows: "ESC7 Progress: [ 89%] [###..] ESC8 Setting up gpgsm" -> the setup.
_OVERLAY = re.compile("\x1b7.*?\x1b8")
_SPINNER = re.compile("[⠀-⣿]")


def clean_output(line: str) -> str:
    """Strip terminal control sequences from a captured line.

    A carriage return means "redraw this line", so only the last segment is
    the state the user would have seen. Deleting the \\r instead would splice
    every intermediate frame together: "0% [Working]0% [Working]0% [Working]".

    The trailing CR must go first: a PTY turns every \\n into \\r\\n, so after
    splitting the stream on \\n *every* line ends in \\r and taking the last
    segment would leave nothing but empty strings.
    """
    line = line.rstrip("\r").split("\r")[-1]
    line = _OVERLAY.sub("", line)
    line = _ANSI.sub("", line)
    line = _SPINNER.sub("", line)
    return line.rstrip()


def load_scripts(path: str | Path) -> dict[str, str]:
    """Import INSTALL_SCRIPTS from the legacy install_scripts.py."""
    path = Path(path)
    spec = importlib.util.spec_from_file_location("_bothy_install_scripts", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    raw = getattr(mod, "INSTALL_SCRIPTS", {})
    return {k: v for k, v in raw.items() if isinstance(v, str) and v.strip()}


def render(script: str, env: dict[str, str] | None = None) -> str:
    """Prepend exports for the definition's environment variables.

    Values are quoted with shlex, so a password containing a space, a quote or
    a `$` cannot break out into the surrounding shell.
    """
    if not env:
        return script
    lines = ["#!/bin/bash", "# environment supplied by Bothy"]
    for k, v in env.items():
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", k):
            continue          # never export a name that is not a valid identifier
        lines.append(f"export {k}={shlex.quote(str(v))}")
    body = script
    if body.startswith("#!"):
        body = body.split("\n", 1)[1] if "\n" in body else ""
    return "\n".join(lines) + "\n" + body


def secrets_in(env_vars: Iterable[dict]) -> list[str]:
    """Names of env vars a definition marks secret, for log redaction."""
    return [e.get("name", "") for e in env_vars or [] if e.get("secret")]


def redact(line: str, secrets: dict[str, str]) -> str:
    """Never let a resolved secret reach the log verbatim."""
    for name, value in secrets.items():
        if value and len(value) > 3 and value in line:
            line = line.replace(value, f"$({name})")
    return line


def scrub(line: str, secrets: dict[str, str]) -> str:
    """Everything a captured line needs before it is safe and readable."""
    return redact(clean_output(line), secrets)


class NodeSSH:
    """Thin paramiko wrapper for one Proxmox node."""

    def __init__(self, host: str, user: str = "root", password: str = "",
                 key_path: str = "", port: int = 22):
        self.host, self.user, self.password = host, user, password
        self.key_path, self.port = key_path, port
        self._client = None

    def connect(self):
        if self._client is not None:
            return self._client
        import paramiko

        c = paramiko.SSHClient()
        c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        kwargs = dict(hostname=self.host, port=self.port, username=self.user, timeout=20)
        if self.key_path:
            kwargs["key_filename"] = self.key_path
        else:
            kwargs["password"] = self.password
        c.connect(**kwargs)
        self._client = c
        return c

    def close(self) -> None:
        if self._client is not None:
            try:
                self._client.close()
            finally:
                self._client = None

    def put(self, content: str, remote_path: str) -> None:
        c = self.connect()
        sftp = c.open_sftp()
        try:
            with sftp.file(remote_path, "w") as f:
                f.write(content)
            sftp.chmod(remote_path, 0o700)
        finally:
            sftp.close()

    def run(self, command: str, on_line: Callable[[str], None] | None = None,
            timeout: int = DEFAULT_TIMEOUT) -> int:
        """Run a command, streaming combined output. Returns the exit status."""
        c = self.connect()
        chan = c.get_transport().open_session()
        chan.settimeout(timeout)
        chan.get_pty()                    # merge stderr so ordering is preserved
        chan.exec_command(command)
        buf = ""
        # Read until EOF, not until the process exits. Polling exit_status_ready()
        # wins the race against data still sitting in the channel buffer, which
        # silently truncated a six-minute install down to one line. recv() returns
        # b"" only once the process has exited AND everything has been delivered.
        while True:
            data = chan.recv(4096)
            if not data:
                break
            buf += data.decode("utf-8", "replace")
            while "\n" in buf:
                line, buf = buf.split("\n", 1)
                if on_line:
                    on_line(line)
        if buf and on_line:
            on_line(buf)
        return chan.recv_exit_status()


def filtered(on_line: Callable[[str, str], None],
             secrets: dict[str, str]) -> Callable[[str], None]:
    """Scrub a streamed line and drop the noise before it reaches the log.

    apt and npm under a PTY redraw constantly: one `apt-get update` produced
    5,504 lines, nearly all of them the same warning repeated. Blank lines and
    consecutive duplicates carry no information a reader can use.
    """
    last = [""]

    def sink(raw: str) -> None:
        text = scrub(raw, secrets)
        if not text or text == last[0]:
            return
        last[0] = text
        on_line("detail", text)
    return sink


def run_install(ssh: NodeSSH, vmid: int, script: str,
                on_line: Callable[[str, str], None],
                secrets: dict[str, str] | None = None,
                timeout: int = DEFAULT_TIMEOUT) -> None:
    """Upload and execute a script inside the guest. Raises on non-zero exit."""
    secrets = secrets or {}
    staged = f"/tmp/bothy-install-{vmid}.sh"
    inside = "/root/bothy-install.sh"

    ssh.put(script, staged)
    on_line("detail", f"uploaded install script ({len(script.splitlines())} lines)")

    rc = ssh.run(f"pct push {vmid} {shlex.quote(staged)} {shlex.quote(inside)} --perms 700",
                 filtered(on_line, secrets))
    if rc != 0:
        raise RuntimeError(f"pct push failed with exit {rc}")

    on_line("cmd", f"pct exec {vmid} -- bash {inside}")
    rc = ssh.run(f"pct exec {vmid} -- bash {shlex.quote(inside)}",
                 filtered(on_line, secrets), timeout=timeout)
    if rc != 0:
        raise RuntimeError(f"install script failed with exit {rc}")

    # tidy the staging copy on the node; leave the in-guest copy for debugging
    ssh.run(f"rm -f {shlex.quote(staged)}")
    on_line("ok", "install script completed")
