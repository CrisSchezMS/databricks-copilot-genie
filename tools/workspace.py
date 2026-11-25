"""Explicit Databricks-first notebook and SQL operations; no background synchronization."""

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
RESOURCE = "2ff814a6-3304-4ab8-85cb-cd0e6f879c1d"
KINDS = {
    "notebooks": (".py", b"# Databricks notebook source", "PYTHON"),
    "sql": (".sql", b"-- Databricks notebook source", "SQL"),
}


def digest(content):
    return hashlib.sha256(content).hexdigest()


def validate_name(name):
    parts = name.split("/")
    if len(parts) < 2 or parts[0] not in KINDS:
        raise ValueError("Nombre requerido: notebooks/<nombre> o sql/<nombre>, sin extension")
    if any(not re.fullmatch(r"[A-Za-z0-9_-]+", part) for part in parts[1:]):
        raise ValueError("Nombre invalido; usa letras, numeros, guiones y guiones bajos")
    return parts


class API:
    def __init__(self, host):
        parsed = urllib.parse.urlsplit(host)
        if (parsed.scheme != "https" or not parsed.hostname
                or not parsed.hostname.endswith(".azuredatabricks.net")
                or parsed.username or parsed.password or parsed.port
                or parsed.path not in ("", "/") or parsed.query or parsed.fragment):
            raise ValueError("DATABRICKS_HOST debe ser la URL HTTPS de Azure Databricks")
        self.host = host.rstrip("/")
        self.token = None
        self.token_time = 0

    def request(self, method, path, body=None, missing_ok=False):
        if self.token is None or time.monotonic() - self.token_time > 600:
            az = "az.cmd" if os.name == "nt" else "az"
            result = subprocess.run(
                [az, "account", "get-access-token", "--resource", RESOURCE, "-o", "json"],
                check=True, capture_output=True, text=True,
            )
            self.token = json.loads(result.stdout)["accessToken"]
            self.token_time = time.monotonic()
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(
            self.host + path, data=data, method=method,
            headers={"Authorization": "Bearer " + self.token, "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            try:
                payload = json.loads(error.read().decode("utf-8", "replace"))
                code = payload.get("error_code", "")
            except json.JSONDecodeError:
                code = ""
            if missing_ok and error.code == 404 and code == "RESOURCE_DOES_NOT_EXIST":
                return None
            raise RuntimeError(f"Databricks HTTP {error.code}: {code or 'request failed'}") from error

    def user(self):
        return self.request("GET", "/api/2.0/preview/scim/v2/Me")["userName"]

    def read(self, remote):
        params = urllib.parse.urlencode({"path": remote})
        status = self.request("GET", "/api/2.0/workspace/get-status?" + params, missing_ok=True)
        if status is None:
            return None
        if status.get("object_type") != "NOTEBOOK":
            raise RuntimeError("El destino no es un notebook")
        params = urllib.parse.urlencode({"path": remote, "format": "SOURCE"})
        result = self.request("GET", "/api/2.0/workspace/export?" + params)
        return base64.b64decode(result["content"], validate=True)

    def write(self, remote, content, language, overwrite):
        self.request("POST", "/api/2.0/workspace/mkdirs", {"path": remote.rsplit("/", 1)[0]})
        self.request("POST", "/api/2.0/workspace/import", {
            "path": remote, "format": "SOURCE", "language": language,
            "content": base64.b64encode(content).decode(), "overwrite": overwrite,
        })


def remote_path(api, name):
    parts = validate_name(name)
    user = api.user()
    if not re.fullmatch(r"[^/\\\x00-\x1f]+", user) or user in (".", ".."):
        raise ValueError("Identidad Databricks invalida")
    return f"/Users/{user}/copilot-databricks-genie/" + "/".join(parts)


def put(api, remote, name, content, expected):
    parts = validate_name(name)
    _, header, language = KINDS[parts[0]]
    content.decode("utf-8")
    if not content.startswith(header):
        raise ValueError("Falta la cabecera Databricks SOURCE")
    actual = api.read(remote)
    if expected == "absent":
        if actual is not None:
            raise RuntimeError("Conflicto: el notebook ya existe")
    elif actual is None or digest(actual) != expected:
        raise RuntimeError("Conflicto: el notebook ha cambiado o no existe")
    api.write(remote, content, language, overwrite=expected != "absent")
    result = api.read(remote)
    if result is None:
        raise RuntimeError("No se pudo verificar el notebook importado")
    if result.replace(b"\r\n", b"\n").rstrip(b"\n") != content.replace(b"\r\n", b"\n").rstrip(b"\n"):
        raise RuntimeError("El contenido exportado no coincide con lo enviado; revisa el notebook")
    return digest(result)


def export_approved(api, remote, name, expected, root=ROOT):
    parts = validate_name(name)
    actual = api.read(remote)
    if actual is None or digest(actual) != expected:
        raise RuntimeError("El notebook remoto ya no coincide con la version aprobada")
    extension = KINDS[parts[0]][0]
    target = root / "databricks" / Path(*parts)
    target = target.with_suffix(extension)
    base = (root / "databricks").resolve()
    if not base.is_relative_to(root.resolve()) or not target.resolve().is_relative_to(base):
        raise ValueError("El destino local esta fuera de databricks")
    relative = target.relative_to(root)
    status = subprocess.run(
        ["git", "-C", str(root), "status", "--porcelain", "--", str(relative)],
        check=True, capture_output=True, text=True,
    )
    if status.stdout.strip():
        raise RuntimeError("El destino local tiene cambios; no se sobrescribira")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(actual)
    return relative


def run_sql(api, warehouse, statement):
    if not re.fullmatch(r"[0-9a-fA-F]+", warehouse):
        raise ValueError("Identificador de warehouse invalido")
    response = api.request("POST", "/api/2.0/sql/statements", {
        "warehouse_id": warehouse, "statement": statement, "wait_timeout": "10s",
        "row_limit": 100, "byte_limit": 1000000,
    })
    statement_id = response["statement_id"]
    deadline = time.monotonic() + 180
    while response.get("status", {}).get("state") in ("PENDING", "RUNNING"):
        if time.monotonic() >= deadline:
            raise RuntimeError(f"Consulta aun en curso: {statement_id}; revisala en Databricks")
        time.sleep(2)
        response = api.request("GET", "/api/2.0/sql/statements/" + urllib.parse.quote(statement_id, safe=""))
    if response.get("status", {}).get("state") != "SUCCEEDED":
        raise RuntimeError("SQL no completado: " + json.dumps(response.get("status", {})))
    return response


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    read = commands.add_parser("read", help="Leer un notebook remoto y su SHA-256")
    read.add_argument("name")
    write = commands.add_parser("write", help="Actualizar el notebook remoto explicitamente")
    write.add_argument("name")
    write.add_argument("--expected", required=True, help="SHA-256 leido o absent")
    write.add_argument("--source", required=True, help="Archivo SOURCE o - para stdin UTF-8")
    export = commands.add_parser("export", help="Copiar a Git una version explicitamente aprobada")
    export.add_argument("name")
    export.add_argument("--approved-sha256", required=True)
    sql = commands.add_parser("sql", help="Ejecutar SQL explicitamente en un warehouse")
    sql.add_argument("--warehouse-id", required=True)
    sql.add_argument("--statement", required=True)
    sql.add_argument("--confirm-execution", action="store_true", required=True)
    args = parser.parse_args()
    api = API(os.environ.get("DATABRICKS_HOST", ""))
    if args.command == "sql":
        print(json.dumps(run_sql(api, args.warehouse_id, args.statement), ensure_ascii=False))
        return
    remote = remote_path(api, args.name)
    if args.command == "read":
        content = api.read(remote)
        if content is None:
            print(json.dumps({"path": remote, "sha256": None, "content": None}))
        else:
            print(json.dumps({"path": remote, "sha256": digest(content), "content": content.decode("utf-8")}, ensure_ascii=False))
    elif args.command == "write":
        content = sys.stdin.buffer.read() if args.source == "-" else Path(args.source).read_bytes()
        print(json.dumps({"path": remote, "sha256": put(api, remote, args.name, content, args.expected)}))
    else:
        target = export_approved(api, remote, args.name, args.approved_sha256)
        print(json.dumps({"exported": str(target), "sha256": args.approved_sha256}))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, OSError, subprocess.SubprocessError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)
