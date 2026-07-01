#!/usr/bin/env python3
"""
SQLite database models with SQLAlchemy.
Replaces estado.csv as the source of truth.
"""

import json
from datetime import datetime, date
from pathlib import Path

from sqlalchemy import (
    Boolean, Column, Date, DateTime, Float, ForeignKey,
    Integer, String, Text, create_engine, event, text
)
from sqlalchemy.orm import DeclarativeBase, sessionmaker, scoped_session

ROOT = Path(__file__).parent.parent.resolve()
DB_PATH = ROOT / "data" / "pipeline.db"
DB_PATH.parent.mkdir(exist_ok=True)

engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False},
    echo=False,
)

@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_conn, _):
    dbapi_conn.execute("PRAGMA journal_mode=WAL")
    dbapi_conn.execute("PRAGMA foreign_keys=ON")


Session = scoped_session(sessionmaker(bind=engine))


class Base(DeclarativeBase):
    pass


STAGE_CHOICES = (
    "discovered",
    "pending_send",
    "sent",
    "waiting",
    "generating",
    "ready_deploy",
    "deployed",
    "link_sent",
    "completed",
    "error",
)

STAGE_LABELS = {
    "discovered":   "Descubierto",
    "pending_send": "Pendiente de enviar",
    "sent":         "Mensaje enviado",
    "waiting":      "Esperando respuesta",
    "generating":   "Generando web",
    "ready_deploy": "Listo para deploy",
    "deployed":     "Deploy realizado",
    "link_sent":    "Link enviado",
    "completed":    "Completado",
    "error":        "Error",
}


class Lead(Base):
    __tablename__ = "leads"

    id         = Column(Integer, primary_key=True)
    lead_id    = Column(String(64), unique=True, index=True)
    nombre     = Column(String(200), nullable=False, default="")
    telefono   = Column(String(50), unique=True, index=True)
    categoria  = Column(String(100))
    direccion  = Column(String(300))
    ciudad     = Column(String(100), default="Rosario")
    puntaje    = Column(Float)
    resenas    = Column(Integer, default=0)
    score      = Column(Integer, default=0)
    filter_reason = Column(String(300))

    stage      = Column(String(50), default="discovered", index=True)

    # Outreach
    enviado       = Column(Boolean, default=False)
    fecha_envio   = Column(DateTime)
    estado_respuesta = Column(String(50))
    fecha_respuesta  = Column(DateTime)
    mensaje_enviado  = Column(Text)

    # Web generation
    project_path     = Column(String(500))
    website_prompt   = Column(Text)
    website_tokens   = Column(Integer)
    website_duration = Column(Float)
    website_model    = Column(String(100))
    website_version  = Column(Integer, default=0)
    website_error    = Column(Text)

    # Deploy
    live_url      = Column(String(500))
    deploy_commit = Column(String(100))
    deploy_time   = Column(Float)
    deploy_logs   = Column(Text)

    # Link sending
    enviado_links     = Column(Boolean, default=False)
    fecha_envio_links = Column(DateTime)

    # Follow-ups
    followup_stage    = Column(Integer, default=0)
    followup_sent_at  = Column(DateTime)

    # CRM
    fecha_entrega                   = Column(Date)
    fecha_renovacion_web            = Column(Date)
    fecha_renovacion_hosting        = Column(Date)
    fecha_renovacion_mantenimiento  = Column(Date)
    notas        = Column(Text)
    prioridad    = Column(Integer, default=3)
    etiquetas    = Column(Text, default="[]")
    responsable  = Column(String(100))

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self) -> dict:
        def _d(v):
            if isinstance(v, datetime):
                return v.isoformat()
            if isinstance(v, date):
                return v.isoformat()
            return v

        return {
            "id": self.id,
            "lead_id": self.lead_id,
            "nombre": self.nombre,
            "telefono": self.telefono,
            "categoria": self.categoria,
            "direccion": self.direccion,
            "ciudad": self.ciudad,
            "puntaje": self.puntaje,
            "resenas": self.resenas,
            "score": self.score,
            "filter_reason": self.filter_reason,
            "stage": self.stage,
            "enviado": self.enviado,
            "fecha_envio": _d(self.fecha_envio),
            "estado_respuesta": self.estado_respuesta,
            "fecha_respuesta": _d(self.fecha_respuesta),
            "mensaje_enviado": self.mensaje_enviado,
            "project_path": self.project_path,
            "website_tokens": self.website_tokens,
            "website_duration": self.website_duration,
            "website_model": self.website_model,
            "website_version": self.website_version,
            "website_error": self.website_error,
            "live_url": self.live_url,
            "deploy_commit": self.deploy_commit,
            "deploy_time": self.deploy_time,
            "deploy_logs": self.deploy_logs,
            "enviado_links": self.enviado_links,
            "fecha_envio_links": _d(self.fecha_envio_links),
            "followup_stage": self.followup_stage or 0,
            "followup_sent_at": _d(self.followup_sent_at),
            "fecha_entrega": _d(self.fecha_entrega),
            "fecha_renovacion_web": _d(self.fecha_renovacion_web),
            "fecha_renovacion_hosting": _d(self.fecha_renovacion_hosting),
            "fecha_renovacion_mantenimiento": _d(self.fecha_renovacion_mantenimiento),
            "notas": self.notas,
            "prioridad": self.prioridad,
            "etiquetas": json.loads(self.etiquetas) if self.etiquetas else [],
            "responsable": self.responsable,
            "created_at": _d(self.created_at),
            "updated_at": _d(self.updated_at),
        }


class PipelineJob(Base):
    __tablename__ = "pipeline_jobs"

    id              = Column(Integer, primary_key=True)
    job_id          = Column(String(64), unique=True, index=True)
    stage           = Column(String(50))
    status          = Column(String(20), default="queued")
    progress        = Column(Integer, default=0)
    total_items     = Column(Integer, default=0)
    processed_items = Column(Integer, default=0)
    started_at      = Column(DateTime)
    completed_at    = Column(DateTime)
    error           = Column(Text)
    logs            = Column(Text, default="[]")
    params          = Column(Text, default="{}")
    created_at      = Column(DateTime, default=datetime.utcnow)

    def to_dict(self) -> dict:
        def _d(v):
            return v.isoformat() if isinstance(v, datetime) else v
        return {
            "job_id": self.job_id,
            "stage": self.stage,
            "status": self.status,
            "progress": self.progress,
            "total_items": self.total_items,
            "processed_items": self.processed_items,
            "started_at": _d(self.started_at),
            "completed_at": _d(self.completed_at),
            "error": self.error,
            "logs": json.loads(self.logs) if self.logs else [],
            "params": json.loads(self.params) if self.params else {},
            "created_at": _d(self.created_at),
        }


class ErrorLog(Base):
    __tablename__ = "error_logs"

    id         = Column(Integer, primary_key=True)
    lead_id    = Column(Integer, ForeignKey("leads.id"), nullable=True)
    job_id     = Column(String(64), nullable=True)
    module     = Column(String(100))
    command    = Column(String(200))
    error_type = Column(String(100))
    message    = Column(Text)
    stacktrace = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "lead_id": self.lead_id,
            "job_id": self.job_id,
            "module": self.module,
            "command": self.command,
            "error_type": self.error_type,
            "message": self.message,
            "stacktrace": self.stacktrace,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class ClaudeGeneration(Base):
    __tablename__ = "claude_generations"

    id            = Column(Integer, primary_key=True)
    lead_id       = Column(Integer, ForeignKey("leads.id"))
    prompt        = Column(Text)
    tokens_input  = Column(Integer)
    tokens_output = Column(Integer)
    duration      = Column(Float)
    model         = Column(String(100))
    version       = Column(Integer, default=1)
    success       = Column(Boolean, default=True)
    error         = Column(Text)
    created_at    = Column(DateTime, default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "lead_id": self.lead_id,
            "tokens_input": self.tokens_input,
            "tokens_output": self.tokens_output,
            "duration": self.duration,
            "model": self.model,
            "version": self.version,
            "success": self.success,
            "error": self.error,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Template(Base):
    __tablename__ = "templates"

    id         = Column(Integer, primary_key=True)
    nombre     = Column(String(200))
    contenido  = Column(Text)
    tipo       = Column(String(50), default="outreach")
    activo     = Column(Boolean, default=True)
    usos       = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "nombre": self.nombre,
            "contenido": self.contenido,
            "tipo": self.tipo,
            "activo": self.activo,
            "usos": self.usos,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class AppConfig(Base):
    __tablename__ = "app_config"

    key        = Column(String(100), primary_key=True)
    value      = Column(Text)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Finanza(Base):
    __tablename__ = "finanzas"

    id         = Column(Integer, primary_key=True)
    lead_id    = Column(Integer, ForeignKey("leads.id"), nullable=True)
    nombre     = Column(String(200))
    telefono   = Column(String(50))
    monto      = Column(Float)
    moneda     = Column(String(10), default="ARS")
    estado     = Column(String(20), default="pendiente")
    fecha      = Column(Date)
    servicio   = Column(String(200))
    notas      = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "lead_id": self.lead_id,
            "nombre": self.nombre,
            "telefono": self.telefono,
            "monto": self.monto,
            "moneda": self.moneda,
            "estado": self.estado,
            "fecha": self.fecha.isoformat() if self.fecha else None,
            "servicio": self.servicio,
            "notas": self.notas,
        }


def init_db():
    Base.metadata.create_all(engine)
    _migrate_followup_columns()
    _seed_templates()


def _migrate_followup_columns():
    with engine.connect() as conn:
        for col, typedef in [
            ("followup_stage", "INTEGER DEFAULT 0"),
            ("followup_sent_at", "DATETIME"),
        ]:
            try:
                conn.execute(text(f"ALTER TABLE leads ADD COLUMN {col} {typedef}"))
                conn.commit()
            except Exception:
                pass  # Column already exists


def _seed_templates():
    from modules.outreach import PLANTILLAS  # noqa: import from parent

    session = Session()
    try:
        if session.query(Template).count() == 0:
            for i, txt in enumerate(PLANTILLAS, 1):
                session.add(Template(nombre=f"Template #{i}", contenido=txt, tipo="outreach"))
            session.commit()
    except Exception:
        session.rollback()
    finally:
        session.close()


def _infer_stage(row: dict) -> str:
    enviado_links = row.get("enviado_links", "").upper() == "SI"
    live_url      = bool(row.get("live_url", "").strip())
    project_path  = bool(row.get("project_path", "").strip())
    estado        = row.get("estado_respuesta", "").strip()
    enviado       = row.get("enviado", "").upper() == "SI"

    INTEREST = {"interest", "positive_intent", "price_request", "follow_up"}

    if enviado_links and live_url:
        return "link_sent"
    if live_url:
        return "deployed"
    if project_path:
        return "ready_deploy"
    if estado in INTEREST:
        return "waiting"
    if estado == "rejection":
        return "completed"
    if enviado:
        return "sent"
    return "discovered"


def migrate_from_csv(csv_path: Path) -> int:
    """Import estado.csv into the SQLite database. Returns number of rows imported."""
    import csv
    import uuid

    if not csv_path.exists():
        return 0

    session = Session()
    imported = 0
    try:
        with open(csv_path, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                telefono = row.get("telefono", "").strip()
                if not telefono:
                    continue
                existing = session.query(Lead).filter_by(telefono=telefono).first()
                if existing:
                    continue

                def _dt(s: str):
                    s = s.strip()
                    if not s:
                        return None
                    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
                        try:
                            return datetime.strptime(s, fmt)
                        except ValueError:
                            pass
                    return None

                def _date(s: str):
                    d = _dt(s)
                    return d.date() if d else None

                lead = Lead(
                    lead_id   = row.get("lead_id") or str(uuid.uuid4()),
                    nombre    = row.get("nombre", ""),
                    telefono  = telefono,
                    categoria = row.get("categoria", ""),
                    direccion = row.get("direccion", ""),
                    puntaje   = float(row["puntaje"]) if row.get("puntaje") else None,
                    resenas   = int(row["resenas"]) if row.get("resenas") else 0,
                    score     = int(row["score"]) if row.get("score") else 0,
                    filter_reason = row.get("filter_reason", ""),
                    stage     = _infer_stage(row),
                    enviado   = row.get("enviado", "").upper() == "SI",
                    fecha_envio  = _dt(row.get("fecha_envio", "")),
                    estado_respuesta = row.get("estado_respuesta", "") or None,
                    fecha_respuesta  = _dt(row.get("fecha_respuesta", "")),
                    project_path = row.get("project_path", "") or None,
                    live_url     = row.get("live_url", "") or None,
                    enviado_links = row.get("enviado_links", "").upper() == "SI",
                    fecha_envio_links = _dt(row.get("fecha_envio_links", "")),
                    fecha_entrega = _date(row.get("fecha_entrega", "")),
                    fecha_renovacion_web = _date(row.get("fecha_renovacion_web", "")),
                    fecha_renovacion_hosting = _date(row.get("fecha_renovacion_hosting", "")),
                    fecha_renovacion_mantenimiento = _date(row.get("fecha_renovacion_mantenimiento", "")),
                    notas = row.get("notas", "") or None,
                )
                session.add(lead)
                imported += 1

        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    return imported
