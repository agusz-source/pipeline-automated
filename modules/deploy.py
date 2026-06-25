#!/usr/bin/env python3
# modules/deploy.py - Despliegue a Vercel

import json
import subprocess
import csv
import re
import requests
from pathlib import Path
from colorama import Fore
from config import config

_VERCEL_AUTH_PATHS = [
    Path.home() / ".local/share/com.vercel.cli/auth.json",
    Path.home() / ".config/com.vercel.cli/auth.json",
]


def _read_vercel_token() -> str:
    for path in _VERCEL_AUTH_PATHS:
        if path.exists():
            try:
                return json.loads(path.read_text()).get("token", "")
            except Exception:
                pass
    return ""


class Deployer:

    def deploy_a_vercel(self, project_path, nombre):
        """Despliega a Vercel y retorna la URL de producción"""
        project_name = nombre.lower().replace(' ', '-')
        project_name = re.sub(r'[^a-z0-9-]', '', project_name)[:52]

        print(f"{Fore.CYAN}🚀 Desplegando a Vercel: {project_name}...")

        try:
            result = subprocess.run(
                ["vercel", "--prod", "--yes", f"--name={project_name}"],
                capture_output=True,
                text=True,
                cwd=str(project_path)
            )

            output = result.stdout + result.stderr
            url = self._extraer_url(output)

            if result.returncode != 0 and not url:
                print(f"{Fore.RED}❌ Vercel error:\n{output[:400]}")
                return ""

            if url:
                self._desactivar_proteccion(project_path)
                print(f"{Fore.GREEN}✅  {nombre}  →  {url}")
            else:
                print(f"{Fore.YELLOW}⚠️  Deploy OK pero no se encontró URL en el output")

            return url

        except FileNotFoundError:
            print(f"{Fore.RED}❌ 'vercel' no está instalado. Instalá con: npm i -g vercel")
            return ""
        except Exception as e:
            print(f"{Fore.RED}❌ Error: {e}")
            return ""

    def _desactivar_proteccion(self, project_path: Path):
        """Llama a la API de Vercel para quitar la protección SSO del proyecto."""
        token = _read_vercel_token()
        if not token:
            print(f"{Fore.YELLOW}   ⚠️  No se encontró token de Vercel — verificá que estés logueado con 'vercel login'")
            return

        vercel_json = project_path / ".vercel" / "project.json"
        if not vercel_json.exists():
            return

        try:
            meta = json.loads(vercel_json.read_text())
        except Exception:
            return

        project_id = meta.get("projectId", "")
        org_id = meta.get("orgId", "")
        if not project_id:
            return

        params = {"teamId": org_id} if org_id.startswith("team_") else {}

        try:
            resp = requests.patch(
                f"https://api.vercel.com/v9/projects/{project_id}",
                json={"ssoProtection": None},
                headers={"Authorization": f"Bearer {token}"},
                params=params,
                timeout=10,
            )
            if resp.status_code == 200:
                print(f"{Fore.GREEN}   🔓 Protección desactivada — sitio público")
            else:
                print(f"{Fore.YELLOW}   ⚠️  No se pudo desactivar protección ({resp.status_code}): {resp.text[:120]}")
        except Exception as e:
            print(f"{Fore.YELLOW}   ⚠️  Error al desactivar protección: {e}")

    def _extraer_url(self, output):
        """Extrae la URL de producción del output de Vercel"""
        # Prioridad: línea "Production: https://..."
        for line in output.splitlines():
            if 'Production:' in line or '✅' in line:
                match = re.search(r'https://\S+\.vercel\.app', line)
                if match:
                    return match.group(0)

        # Fallback: cualquier URL vercel.app en el output
        match = re.search(r'https://\S+\.vercel\.app', output)
        return match.group(0) if match else ""

    def desplegar_interesados(self, status_file, session_paths=None):
        """Lee el CSV, despliega los websites generados y guarda las URLs.

        session_paths: si se pasa, solo despliega esos project_paths (los de esta sesión).
        Si es None, despliega todos los pendientes (útil para --deploy standalone).
        """
        if not Path(status_file).exists():
            print(f"{Fore.RED}❌ Archivo no encontrado: {status_file}")
            return

        with open(status_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            fieldnames = reader.fieldnames

        if session_paths is not None:
            session_set = set(session_paths)
            pendientes = [r for r in rows if r.get('project_path') in session_set and not r.get('live_url')]
        else:
            pendientes = [r for r in rows if r.get('project_path') and not r.get('live_url')]

        if not pendientes:
            print(f"{Fore.YELLOW}⚠️  No hay sitios pendientes de deploy (sin project_path o ya tienen live_url)")
            return

        print(f"\n{'='*60}")
        print(f"🌐 DEPLOY A VERCEL — {len(pendientes)} sitio(s)")
        print(f"{'='*60}")

        actualizados = 0
        rows_por_telefono = {r['telefono']: r for r in rows}

        for row in pendientes:
            project_path = Path(row['project_path'])
            nombre = row['nombre']

            if not project_path.exists():
                print(f"{Fore.YELLOW}⚠️  Carpeta no existe: {project_path}")
                continue

            url = self.deploy_a_vercel(project_path, nombre)

            if url:
                rows_por_telefono[row['telefono']]['live_url'] = url
                actualizados += 1

        if actualizados > 0:
            with open(status_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
            print(f"\n{Fore.GREEN}✅ Deploy completado: {actualizados} sitio(s) — URLs guardadas en {status_file}")
        else:
            print(f"{Fore.YELLOW}⚠️  Ningún sitio desplegado con éxito")
