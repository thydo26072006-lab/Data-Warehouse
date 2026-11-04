"""Start a project-local PostgreSQL instance; no Windows service is installed."""
from pathlib import Path
import argparse
import os
import secrets
import subprocess
import time
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / ".runtime"
BIN = RUNTIME / "pgsql" / "bin"
DATA = RUNTIME / "pgdata"
URL = "https://get.enterprisedb.com/postgresql/postgresql-17.11-3-windows-x64-binaries.zip"
PORT = "55432"

def run(args, check=True, env=None):
    return subprocess.run([str(a) for a in args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", check=check, env=env,
                          creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stop", action="store_true")
    args = parser.parse_args()
    RUNTIME.mkdir(exist_ok=True)
    if args.stop:
        result = run([BIN/"pg_ctl.exe","-D",DATA,"-m","fast","-w","stop"])
        print(result.stdout)
        return
    if not (BIN/"postgres.exe").exists():
        archive = RUNTIME/"postgresql-17.11-3-windows-x64-binaries.zip"
        if not archive.exists():
            print("Downloading official PostgreSQL binaries...", flush=True)
            urllib.request.urlretrieve(URL, archive)
        with zipfile.ZipFile(archive) as z:
            for name in z.namelist():
                if name.startswith(("pgsql/bin/","pgsql/lib/","pgsql/share/")) and not name.endswith("/"):
                    if not (RUNTIME/name).resolve().is_relative_to(RUNTIME.resolve()):
                        raise ValueError("Unsafe archive member.")
                    z.extract(name, RUNTIME)
    password_file = RUNTIME/"password.txt"
    if not password_file.exists():
        password_file.write_text(secrets.token_urlsafe(32)+"\n", encoding="utf-8")
    password = password_file.read_text(encoding="utf-8").strip()
    passfile = RUNTIME/"pgpass.conf"
    passfile.write_text(f"127.0.0.1:{PORT}:*:superstore:{password}\n", encoding="utf-8")
    if os.name != "nt":
        passfile.chmod(0o600)
    if not (DATA/"PG_VERSION").exists():
        result = run([BIN/"initdb.exe","-D",DATA,"-U","superstore","-E","UTF8",
                      "--locale=C","--auth-host=scram-sha-256",
                      "--auth-local=scram-sha-256",f"--pwfile={password_file}"])
        (RUNTIME/"initdb.log").write_text(result.stdout+result.stderr, encoding="utf-8")
    status = run([BIN/"pg_ctl.exe","-D",DATA,"status"], check=False)
    if status.returncode != 0:
        # A detached server can inherit pipe handles on Windows; use a file here.
        with (RUNTIME/"startup.log").open("w",encoding="utf-8") as log:
            started = subprocess.run([str(BIN/"pg_ctl.exe"),"-D",str(DATA),"-l",str(RUNTIME/"postgres.log"),
                            "-o",f"-h 127.0.0.1 -p {PORT}","-w","start"],
                           stdout=log,stderr=subprocess.STDOUT,check=False,
                           creationflags=subprocess.CREATE_NO_WINDOW if os.name=="nt" else 0)
        if started.returncode:
            startup = (RUNTIME/"startup.log").read_text(encoding="utf-8", errors="replace")
            if os.name != "nt" or "could not create restricted token" not in startup:
                raise RuntimeError("PostgreSQL startup failed; see .runtime/startup.log")
            # Some unprivileged Windows environments cannot create the additional
            # restricted token used by pg_ctl. postgres can run as the current
            # unprivileged user without changing service or system permissions.
            with (RUNTIME/"postgres.log").open("a", encoding="utf-8") as log:
                server = subprocess.Popen([str(BIN/"postgres.exe"), "-D", str(DATA),
                                           "-h", "127.0.0.1", "-p", PORT],
                                          stdout=log, stderr=subprocess.STDOUT,
                                          close_fds=True, creationflags=subprocess.CREATE_NO_WINDOW)
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                if server.poll() is not None:
                    raise RuntimeError("PostgreSQL exited during startup; see .runtime/postgres.log")
                pid_file = DATA/"postmaster.pid"
                try:
                    own_pid = pid_file.read_text().splitlines()[0] == str(server.pid)
                except (OSError, IndexError):
                    own_pid = False
                if own_pid and run([BIN/"pg_isready.exe", "-h", "127.0.0.1", "-p", PORT], check=False).returncode == 0:
                    break
                time.sleep(0.25)
            else:
                raise RuntimeError("PostgreSQL did not become ready; see .runtime/postgres.log")
            print("Started PostgreSQL directly as the current unprivileged Windows user.")
    env = os.environ.copy()
    env.update(PGPASSFILE=str(passfile), PGCLIENTENCODING="UTF8", PGCONNECT_TIMEOUT="10")
    maintenance = f"postgresql://superstore@127.0.0.1:{PORT}/postgres?sslmode=disable"
    command = [BIN/"psql.exe","-X","-q","-v","ON_ERROR_STOP=1","-d",maintenance]
    exists = run(command+["-At","-c","SELECT 1 FROM pg_database WHERE datname='superstore_dw'"],env=env)
    if exists.stdout.strip() != "1":
        run(command+["-c","CREATE DATABASE superstore_dw"],env=env)
    print(f"PostgreSQL ready: 127.0.0.1:{PORT}, database=superstore_dw, user=superstore")
    print("Credentials stay in .runtime/pgpass.conf. No Windows service was installed.")

if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as error:
        print(error.stdout or "")
        print(error.stderr or "")
        raise SystemExit(error.returncode)
