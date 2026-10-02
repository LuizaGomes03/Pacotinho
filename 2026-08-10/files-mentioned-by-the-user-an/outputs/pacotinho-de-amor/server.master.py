"""Servidor local do Pacotinho de Amor conectado ao MongoDB Atlas."""

import hashlib
import json
import os
import secrets
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from http.cookies import SimpleCookie
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse
from urllib.request import Request as UrlRequest, urlopen

from pymongo import MongoClient
from pymongo.server_api import ServerApi


# ============================================================
# CONFIGURAÇÃO
# ============================================================

ROOT = Path(__file__).resolve().parent


def load_env():
    env_file = ROOT / ".env"

    if not env_file.exists():
        return

    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()

        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)

        os.environ.setdefault(
            key.strip(),
            value.strip().strip('"').strip("'")
        )


load_env()


def send_adoption_confirmation(application):
    if not all(os.getenv(name) for name in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD")):
        return "not_configured"
    recipient = str(application.get("email", "")).strip()
    if not recipient or "@" not in recipient:
        return "invalid_recipient"
    interview = application.get("adoption_interview") or {}
    message = EmailMessage()
    message["Subject"] = f"Recebemos seu processo de adoção de {application.get('animal_name', 'animal selecionado')}"
    message["From"] = os.getenv("SMTP_FROM", os.getenv("SMTP_USER"))
    message["To"] = recipient
    message.set_content(
        f"Olá, {application.get('applicant_name', '')}!\n\n"
        f"Recebemos seu formulário para adoção de {application.get('animal_name', 'animal selecionado')}. "
        "O processo está em análise e a equipe entrará em contato pelo WhatsApp.\n\n"
        "O preenchimento não garante a aprovação. A contribuição mínima é de R$ 250 e a sugerida é de R$ 350.\n\n"
        f"WhatsApp: {application.get('phone', '')}\n"
        f"Moradia: {interview.get('moradia', '')}\n"
        f"Arquivos do lar: {len(interview.get('fotos_lar', []))}\n\n"
        "Pacotinho de Amor"
    )
    try:
        with smtplib.SMTP(os.environ["SMTP_HOST"], int(os.getenv("SMTP_PORT", "587")), timeout=20) as smtp:
            if os.getenv("SMTP_TLS", "true").lower() != "false":
                smtp.starttls()
            smtp.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
            smtp.send_message(message)
    except (OSError, smtplib.SMTPException):
        return "failed"
    return "sent"

PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
WHATSAPP_ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN", "").strip()
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "").strip()
WHATSAPP_API_VERSION = os.getenv("WHATSAPP_API_VERSION", "v23.0").strip()
WHATSAPP_TEMPLATE_FIRST_PHASE = os.getenv("WHATSAPP_TEMPLATE_FIRST_PHASE", "").strip()
WHATSAPP_TEMPLATE_APPROVED = os.getenv("WHATSAPP_TEMPLATE_APPROVED", "").strip()
WHATSAPP_TEMPLATE_PASSWORD_RESET = os.getenv("WHATSAPP_TEMPLATE_PASSWORD_RESET", "").strip()
WHATSAPP_TEMPLATE_LANGUAGE = os.getenv("WHATSAPP_TEMPLATE_LANGUAGE", "pt_BR").strip()

MONGODB_URI = os.getenv("MONGODB_URI")

if not MONGODB_URI:
    raise RuntimeError(
        "Crie o arquivo .env com MONGODB_URI antes de iniciar o servidor."
    )


client = MongoClient(
    MONGODB_URI,
    server_api=ServerApi("1")
)

db = client.get_database("pacotinho_de_amor")


# Sessões locais.
# Em produção, o ideal é usar Redis ou outro armazenamento de sessão.
SESSIONS = {}


ALLOWED_ORIGINS = {
    "http://127.0.0.1:5500",
    "http://localhost:5500",
    "http://127.0.0.1:8000",
    "http://localhost:8000",
    "http://127.0.0.1:8765",
    "http://localhost:8765",
}


# ============================================================
# FUNÇÕES AUXILIARES
# ============================================================

def now():
    return datetime.now(timezone.utc).isoformat()


def serialize(doc):
    """Converte ObjectId para string sem alterar o documento original."""
    if not doc:
        return None

    result = dict(doc)

    if "_id" in result:
        result["id"] = str(result.pop("_id"))

    # Nunca enviar hash de senha para o navegador.
    result.pop("password_hash", None)
    result.pop("password", None)
    # Campo usado somente pelo TTL do MongoDB para limpar histórico após 30 dias.
    result.pop("history_expires_at", None)

    return result


def hash_password(password, salt=None):
    """Gera um hash PBKDF2-SHA256 para armazenar a senha."""
    if not isinstance(password, str) or not password:
        raise ValueError("Senha inválida.")

    if salt is None:
        salt = secrets.token_hex(16)

    password_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        100_000,
    ).hex()

    return f"{salt}${password_hash}"


def verify_password(password, stored_hash):
    """Verifica uma senha contra um hash armazenado."""
    if not password or not stored_hash:
        return False

    try:
        salt, password_hash = stored_hash.split("$", 1)

        calculated_hash = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            100_000,
        ).hex()

        return secrets.compare_digest(
            calculated_hash,
            password_hash,
        )

    except (ValueError, AttributeError):
        return False


def create_session(user_id, user_type):
    """Cria uma sessão local e retorna o token."""
    token = secrets.token_urlsafe(32)

    SESSIONS[token] = {
        "user_id": str(user_id),
        "user_type": user_type,
        "created_at": now(),
    }

    return token


def get_session(handler):
    """Lê o cookie de sessão enviado pelo navegador."""
    raw_cookie = handler.headers.get("Cookie", "")

    if not raw_cookie:
        return None

    cookie = SimpleCookie()

    try:
        cookie.load(raw_cookie)
    except Exception:
        return None

    session_cookie = cookie.get("pa_session")

    if not session_cookie:
        return None

    token = session_cookie.value

    return SESSIONS.get(token)


def delete_session(handler):
    """Remove a sessão atual."""
    raw_cookie = handler.headers.get("Cookie", "")

    if not raw_cookie:
        return

    cookie = SimpleCookie()

    try:
        cookie.load(raw_cookie)
    except Exception:
        return

    session_cookie = cookie.get("pa_session")

    if session_cookie:
        SESSIONS.pop(session_cookie.value, None)


def get_adopter_from_session(handler):
    """Retorna o adotante autenticado."""
    session = get_session(handler)

    if not session:
        return None

    if session.get("user_type") != "adopter":
        return None

    try:
        from bson import ObjectId

        adopter = db.adopters.find_one(
            {"_id": ObjectId(session["user_id"])}
        )

        return adopter

    except Exception:
        return None



def get_volunteer_from_session(handler):
    """Retorna o voluntário autenticado."""
    session = get_session(handler)

    if not session or session.get("user_type") != "volunteer":
        return None

    try:
        from bson import ObjectId

        return db.volunteers.find_one(
            {"_id": ObjectId(session["user_id"])}
        )
    except Exception:
        return None


def get_master_from_session(handler):
    """Retorna a conta MASTER autenticada na coleção accounts."""
    session = get_session(handler)

    if not session or session.get("user_type") != "master":
        return None

    try:
        from bson import ObjectId

        return db.accounts.find_one(
            {"_id": ObjectId(session["user_id"])}
        )
    except Exception:
        return None


def is_master(handler):
    """Somente a conta com role MASTER pode administrar eventos."""
    master = get_master_from_session(handler)

    if not master:
        return False

    return str(master.get("role", "")).upper() == "MASTER"


def object_id(value):
    """Converte um ID recebido pela API para ObjectId."""
    from bson import ObjectId

    try:
        return ObjectId(str(value))
    except Exception:
        return None


def serialize_list(cursor):
    return [serialize(item) for item in cursor]


def get_event_request_counts(event_id):
    """Retorna quantos voluntários/animais já foram aprovados no evento."""
    approved = list(
        db.event_requests.find(
            {
                "event_id": str(event_id),
                "status": "approved",
            }
        )
    )

    return {
        "approvedRequests": len(approved),
        "approvedAnimals": len(approved),
    }


def init_event_indexes():
    """Índices para os eventos e solicitações."""
    db.events.create_index(
        "date",
        name="event_date",
    )

    db.events.create_index(
        "status",
        name="event_status",
    )

    db.events.create_index(
        "createdBy",
        name="event_created_by",
    )

    db.event_requests.create_index(
        [
            ("event_id", 1),
            ("volunteer_id", 1),
            ("animal_id", 1),
        ],
        unique=True,
        name="unique_event_volunteer_animal",
    )

    db.event_requests.create_index(
        [
            ("event_id", 1),
            ("status", 1),
        ],
        name="event_request_status",
    )


def init_db():
    """Verifica a conexão e cria dados iniciais necessários."""
    client.admin.command("ping")

    # Não criar animais ou usuários de demonstração automaticamente.
    # Todos os dados devem vir do MongoDB Atlas.

    # Índices para evitar contas duplicadas.
    db.adopters.create_index(
        "email",
        unique=True,
        name="unique_adopter_email",
    )

    db.adopters.create_index(
        "cpf",
        unique=True,
        name="unique_adopter_cpf",
    )

    # Solicitações recusadas ficam disponíveis para reversão por 30 dias.
    # Depois disso, o MongoDB remove o documento automaticamente.
    db.volunteer_requests.create_index(
        "history_expires_at",
        expireAfterSeconds=0,
        name="volunteer_request_history_ttl",
    )

    init_event_indexes()


def normalizar_telefone_whatsapp(value):
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    if digits.startswith("55") and len(digits) >= 12:
        return digits
    if len(digits) in (10, 11):
        return "55" + digits
    return digits


def _whatsapp_post(payload):
    if not WHATSAPP_ACCESS_TOKEN or not WHATSAPP_PHONE_NUMBER_ID:
        return {
            "sent": False,
            "message": "API do WhatsApp não configurada."
        }

    request = UrlRequest(
        f"https://graph.facebook.com/{WHATSAPP_API_VERSION}/{WHATSAPP_PHONE_NUMBER_ID}/messages",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=20) as response:
            body = response.read().decode("utf-8", errors="replace")
        return {"sent": True, "response": body, "message": "Mensagem enviada pelo WhatsApp."}
    except Exception as exc:
        return {"sent": False, "message": f"Não foi possível enviar pelo WhatsApp: {exc}"}


def _enviar_template(telefone, template_name, components=None):
    numero = normalizar_telefone_whatsapp(telefone)
    if not numero:
        return {"sent": False, "message": "Telefone inválido para WhatsApp."}
    if not template_name:
        return {"sent": False, "message": "Template do WhatsApp não configurado."}

    template = {
        "name": template_name,
        "language": {"code": WHATSAPP_TEMPLATE_LANGUAGE},
    }
    if components:
        template["components"] = components

    return _whatsapp_post({
        "messaging_product": "whatsapp",
        "to": numero,
        "type": "template",
        "template": template,
    })


def enviar_whatsapp_primeira_fase(telefone, nome):
    # Para mensagem iniciada pelo projeto, use template aprovado pela Meta.
    if WHATSAPP_TEMPLATE_FIRST_PHASE:
        return _enviar_template(
            telefone,
            WHATSAPP_TEMPLATE_FIRST_PHASE,
            [{
                "type": "body",
                "parameters": [{"type": "text", "text": nome}],
            }],
        )

    # Fallback local apenas para teste/desenvolvimento.
    numero = normalizar_telefone_whatsapp(telefone)
    mensagem = (
        f"Olá, {nome}! 💜\n\n"
        "Você passou para a primeira fase do processo de voluntariado do "
        "Pacotinho de Amor! 🐾\n\n"
        "O próximo passo é uma breve entrevista com nossa equipe."
    )
    return {
        "sent": False,
        "whatsapp_url": f"https://wa.me/{numero}?text={quote(mensagem)}" if numero else None,
        "message": "Configure WHATSAPP_TEMPLATE_FIRST_PHASE para envio automático.",
    }


def enviar_whatsapp_conta_criada(telefone, nome, email, activation_token):
    link = f"{PUBLIC_BASE_URL}/primeiro-acesso-voluntario.html?token={quote(activation_token)}"

    if WHATSAPP_TEMPLATE_APPROVED:
        return _enviar_template(
            telefone,
            WHATSAPP_TEMPLATE_APPROVED,
            [{
                "type": "body",
                "parameters": [
                    {"type": "text", "text": nome},
                    {"type": "text", "text": link},
                ],
            }],
        )

    numero = normalizar_telefone_whatsapp(telefone)
    mensagem = (
        f"Olá, {nome}! 💜\n\n"
        "Sua aprovação final como voluntário(a) do Pacotinho de Amor foi concluída. "
        "Sua conta já foi criada com o seu e-mail.\n\n"
        f"E-mail: {email}\n\n"
        "Para criar sua senha e ativar o acesso, use este link:\n"
        f"{link}\n\n"
        "Você não precisa criar outro cadastro. Seus dados já foram registrados pela equipe."
    )
    return {
        "sent": False,
        "whatsapp_url": f"https://wa.me/{numero}?text={quote(mensagem)}" if numero else None,
        "message": "Configure WHATSAPP_TEMPLATE_APPROVED para envio automático.",
        "first_access_url": link,
    }


def enviar_whatsapp_recuperacao(telefone, nome, token):
    link = f"{PUBLIC_BASE_URL}/primeiro-acesso-voluntario.html?token={quote(token)}&mode=reset"
    if WHATSAPP_TEMPLATE_PASSWORD_RESET:
        return _enviar_template(
            telefone,
            WHATSAPP_TEMPLATE_PASSWORD_RESET,
            [{
                "type": "body",
                "parameters": [
                    {"type": "text", "text": nome},
                    {"type": "text", "text": link},
                ],
            }],
        )
    return {"sent": False, "message": "Configure WHATSAPP_TEMPLATE_PASSWORD_RESET para recuperação automática.", "first_access_url": link}


# ============================================================
# SERVIDOR
# ============================================================

class App(SimpleHTTPRequestHandler):

    def end_headers(self):
        origin = self.headers.get("Origin")

        if origin in ALLOWED_ORIGINS:
            self.send_header(
                "Access-Control-Allow-Origin",
                origin,
            )
            self.send_header(
                "Access-Control-Allow-Credentials",
                "true",
            )
            self.send_header(
                "Vary",
                "Origin",
            )

        self.send_header(
            "Access-Control-Allow-Headers",
            "Content-Type",
        )

        self.send_header(
            "Access-Control-Allow-Methods",
            "GET, POST, PUT, DELETE, OPTIONS",
        )

        super().end_headers()


    def send_json(self, code, data, extra_headers=None):
        raw = json.dumps(
            data,
            ensure_ascii=False,
        ).encode("utf-8")

        self.send_response(code)

        self.send_header(
            "Content-Type",
            "application/json; charset=utf-8",
        )

        self.send_header(
            "Content-Length",
            str(len(raw)),
        )

        if extra_headers:
            for key, value in extra_headers.items():
                self.send_header(key, value)

        self.end_headers()

        self.wfile.write(raw)


    def send_session_cookie(self, token):
        cookie = SimpleCookie()

        cookie["pa_session"] = token
        cookie["pa_session"]["httponly"] = True
        cookie["pa_session"]["samesite"] = "Lax"
        cookie["pa_session"]["path"] = "/"

        self.send_header(
            "Set-Cookie",
            cookie.output(header="").strip(),
        )


    def clear_session_cookie(self):
        cookie = SimpleCookie()

        cookie["pa_session"] = ""
        cookie["pa_session"]["httponly"] = True
        cookie["pa_session"]["samesite"] = "Lax"
        cookie["pa_session"]["path"] = "/"
        cookie["pa_session"]["max-age"] = 0

        self.send_header(
            "Set-Cookie",
            cookie.output(header="").strip(),
        )


    def body(self):
        try:
            length = int(
                self.headers.get(
                    "Content-Length",
                    0,
                )
            )

            raw = self.rfile.read(length)

            if not raw:
                return {}

            return json.loads(
                raw.decode("utf-8")
            )

        except (
            ValueError,
            TypeError,
            json.JSONDecodeError,
        ):
            return {}


    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()


    # ========================================================
    # GET
    # ========================================================

    def do_GET(self):
        path = urlparse(self.path).path


        if path == "/api/health":
            return self.send_json(
                200,
                {
                    "ok": True,
                    "database": "MongoDB Atlas",
                },
            )


        if path == "/api/animals":
            animals = db.animals.find().sort(
                "created_at",
                -1,
            )

            return self.send_json(
                200,
                [
                    serialize(animal)
                    for animal in animals
                ],
            )


        if path == "/api/applications":
            applications = db.applications.find().sort(
                "created_at",
                -1,
            )

            return self.send_json(
                200,
                [
                    serialize(application)
                    for application in applications
                ],
            )


        if path == "/api/adopters/me":
            adopter = get_adopter_from_session(self)

            if not adopter:
                return self.send_json(
                    401,
                    {
                        "ok": False,
                        "message": "Você precisa estar conectado.",
                    },
                )

            return self.send_json(
                200,
                {
                    "ok": True,
                    "user": serialize(adopter),
                },
            )



        # ----------------------------------------------------
        # SOLICITAÇÕES DE VOLUNTÁRIOS - MASTER
        # ----------------------------------------------------

        if path == "/api/volunteer-requests":
            if not is_master(self):
                return self.send_json(
                    403,
                    {
                        "ok": False,
                        "message": "Somente a conta Master pode consultar solicitações de voluntários.",
                    },
                )

            requests = db.volunteer_requests.find().sort(
                "created_at",
                -1,
            )

            return self.send_json(
                200,
                serialize_list(requests),
            )


        # ----------------------------------------------------
        # EVENTOS
        # ----------------------------------------------------

        if path == "/api/events":
            cutoff = datetime.now(timezone.utc) - timedelta(days=7)
            old_events = list(db.events.find({"date": {"$lt": cutoff.date().isoformat()}}))
            for old_event in old_events:
                report = dict(old_event)
                report.pop("_id", None)
                report["event_id"] = str(old_event["_id"])
                report["closed_at"] = report.get("closed_at") or datetime.now(timezone.utc)
                db.event_reports.update_one({"event_id": report["event_id"]}, {"$set": report}, upsert=True)
            if old_events:
                db.events.delete_many({"_id": {"$in": [item["_id"] for item in old_events]}})
            events = db.events.find().sort(
                [
                    ("date", 1),
                    ("startTime", 1),
                ]
            )

            return self.send_json(
                200,
                [
                    serialize(event)
                    for event in events
                ],
            )

        if path == "/api/event-reports":
            if not get_session(self):
                return self.send_json(401, {"ok": False, "message": "Faça login para consultar os relatórios."})
            return self.send_json(200, serialize_list(db.event_reports.find().sort("date", -1)))


        if path == "/api/event-requests":
            query = parse_qs(
                urlparse(self.path).query
            )

            volunteer_id = (
                query.get("volunteerId", [None])[0]
            )

            event_id = (
                query.get("eventId", [None])[0]
            )

            session = get_session(self)

            if not session:
                return self.send_json(
                    401,
                    {
                        "ok": False,
                        "message": "Você precisa estar conectado.",
                    },
                )

            if session.get("user_type") not in {"volunteer", "master"}:
                return self.send_json(
                    403,
                    {
                        "ok": False,
                        "message": "Apenas a equipe autorizada pode acessar solicitações de eventos.",
                    },
                )

            current_volunteer_id = str(
                session["user_id"]
            )

            # O voluntário só pode consultar as próprias solicitações.
            if session.get("user_type") == "volunteer" and volunteer_id and volunteer_id != current_volunteer_id:
                return self.send_json(
                    403,
                    {
                        "ok": False,
                        "message": "Você só pode consultar suas próprias solicitações.",
                    },
                )

            request_filter = {} if session.get("user_type") == "master" else {"volunteer_id": current_volunteer_id}

            if event_id:
                request_filter["event_id"] = event_id

            requests = db.event_requests.find(
                request_filter
            ).sort(
                "created_at",
                -1,
            )

            return self.send_json(
                200,
                serialize_list(requests),
            )

        if path == "/api/auth/me":
            session = get_session(self)

            if not session:
                return self.send_json(
                    401,
                    {
                        "ok": False,
                        "authenticated": False,
                    },
                )

            if session["user_type"] == "adopter":
                user = get_adopter_from_session(self)

            elif session["user_type"] == "volunteer":
                user = get_volunteer_from_session(self)

            elif session["user_type"] == "master":
                user = get_master_from_session(self)

            else:
                user = None

            if not user:
                return self.send_json(
                    401,
                    {
                        "ok": False,
                        "authenticated": False,
                    },
                )

            return self.send_json(
                200,
                {
                    "ok": True,
                    "authenticated": True,
                    "user_type": session["user_type"],
                    "user": serialize(user),
                },
            )


        if path == "/api/auth/volunteer-first-access":
            query = parse_qs(urlparse(self.path).query)
            token = query.get("token", [""])[0].strip()
            mode = query.get("mode", ["first"])[0].strip().lower()
            if not token:
                return self.send_json(400, {"ok": False, "message": "Token de acesso ausente."})

            if mode == "reset":
                volunteer = db.volunteers.find_one({
                    "password_reset_token": token,
                    "password_reset_expires_at": {"$gt": datetime.now(timezone.utc)},
                })
            else:
                volunteer = db.volunteers.find_one({"activation_token": token, "first_access_completed": False})

            if not volunteer:
                return self.send_json(404, {"ok": False, "message": "Link inválido, expirado ou já utilizado."})

            return self.send_json(200, {
                "ok": True,
                "mode": mode,
                "user": {"name": volunteer.get("name", ""), "email": volunteer.get("email", "")},
            })

        if path == "/api/auth/volunteer-password-help":
            email = str(parse_qs(urlparse(self.path).query).get("email", [""])[0]).strip().lower()
            if not email:
                return self.send_json(400, {"ok": False, "message": "Informe seu e-mail."})
            volunteer = db.volunteers.find_one({"email": email})
            # Resposta genérica para não revelar se o e-mail existe.
            if not volunteer:
                return self.send_json(200, {"ok": True, "message": "Se houver uma conta de voluntário com este e-mail, enviaremos um link pelo WhatsApp cadastrado."})
            token = secrets.token_urlsafe(32)
            expires = datetime.now(timezone.utc) + timedelta(minutes=30)
            db.volunteers.update_one({"_id": volunteer["_id"]}, {"$set": {"password_reset_token": token, "password_reset_expires_at": expires}})
            whatsapp = enviar_whatsapp_recuperacao(volunteer.get("phone", ""), volunteer.get("name", "voluntário(a)"), token)
            return self.send_json(200, {"ok": True, "message": "Se houver uma conta de voluntário com este e-mail, enviaremos um link pelo WhatsApp cadastrado.", "whatsapp_sent": whatsapp.get("sent", False)})

        return super().do_GET()


    # ========================================================
    # POST
    # ========================================================

    def do_POST(self):
        path = urlparse(self.path).path
        data = self.body()

        # ----------------------------------------------------
        # PRIMEIRO ACESSO DO VOLUNTÁRIO
        # ----------------------------------------------------
        if path == "/api/auth/volunteer-first-access":
            token = str(data.get("token", "")).strip()
            senha = str(data.get("senha", ""))
            mode = str(data.get("mode", "first")).strip().lower()

            if not token or len(senha) < 8:
                return self.send_json(400, {"ok": False, "message": "Informe um link válido e uma senha com pelo menos 8 caracteres."})

            if mode == "reset":
                volunteer = db.volunteers.find_one({
                    "password_reset_token": token,
                    "password_reset_expires_at": {"$gt": datetime.now(timezone.utc)},
                })
                if not volunteer:
                    return self.send_json(404, {"ok": False, "message": "Link inválido ou expirado."})
                unset = {"password_reset_token": "", "password_reset_expires_at": ""}
                first_access = bool(volunteer.get("first_access_completed"))
            else:
                volunteer = db.volunteers.find_one({"activation_token": token, "first_access_completed": False})
                if not volunteer:
                    return self.send_json(404, {"ok": False, "message": "Link de primeiro acesso inválido ou já utilizado."})
                unset = {"activation_token": ""}
                first_access = True

            updates = {
                "password_hash": hash_password(senha),
                "first_access_completed": True,
                "first_access_completed_at": now(),
            }
            db.volunteers.update_one({"_id": volunteer["_id"]}, {"$set": updates, "$unset": unset})

            return self.send_json(200, {
                "ok": True,
                "message": "Senha criada com sucesso. Agora você pode entrar com seu e-mail e senha."
            })


        # ----------------------------------------------------
        # CADASTRO DE VOLUNTÁRIO - PÚBLICO
        # ----------------------------------------------------

        if path == "/api/volunteer-requests":
            nome = str(data.get("nome", "")).strip()
            email = str(data.get("email", "")).strip().lower()
            telefone = str(data.get("telefone", "")).strip()
            disponibilidade = str(
                data.get("disponibilidade", "")
            ).strip()

            modalidades = data.get("modalidades", [])

            if not isinstance(modalidades, list):
                modalidades = [modalidades] if modalidades else []

            modalidades = [
                str(item).strip()
                for item in modalidades
                if str(item).strip()
            ]

            modalidades_permitidas = {
                "Feirinha de adoção",
                "Táxi Dog",
                "Passeador(a)",
            }

            if any(
                item not in modalidades_permitidas
                for item in modalidades
            ):
                return self.send_json(
                    400,
                    {
                        "ok": False,
                        "message": "Uma ou mais formas de voluntariado são inválidas.",
                    },
                )

            if not nome or len(nome.split()) < 2 or not email or len("".join(c for c in telefone if c.isdigit())) < 10 or not disponibilidade:
                return self.send_json(
                    400,
                    {
                        "ok": False,
                        "message": "Informe nome completo, e-mail, WhatsApp válido e disponibilidade.",
                    },
                )

            if not modalidades:
                return self.send_json(
                    400,
                    {
                        "ok": False,
                        "message": "Selecione pelo menos uma forma de voluntariado.",
                    },
                )

            if "@" not in email:
                return self.send_json(
                    400,
                    {
                        "ok": False,
                        "message": "Informe um e-mail válido.",
                    },
                )

            if not bool(data.get("aceiteTermo")) or not bool(
                data.get("aceiteLGPD")
            ):
                return self.send_json(
                    400,
                    {
                        "ok": False,
                        "message": "É necessário aceitar o Termo e confirmar a ciência sobre o tratamento dos dados.",
                    },
                )

            pendente = db.volunteer_requests.find_one(
                {
                    "email": email,
                    "status": "pending",
                }
            )

            if pendente:
                return self.send_json(
                    409,
                    {
                        "ok": False,
                        "message": "Já existe um cadastro de voluntariado pendente para este e-mail.",
                    },
                )

            request = {
                "name": nome,
                "email": email,
                "phone": telefone,
                "modalidades": modalidades,
                "disponibilidade": disponibilidade,
                "tipoDisponibilidade": str(data.get("tipoDisponibilidade", "")).strip()[:80],
                "detalhesDisponibilidade": str(data.get("detalhesDisponibilidade", "")).strip()[:1000],
                "aceiteTermo": True,
                "aceiteLGPD": True,
                "aceiteImagem": bool(
                    data.get("aceiteImagem")
                ),
                "termoEnviado": bool(
                    data.get("termoEnviado")
                ),
                "documento_assinado": str(
                    data.get("documento_assinado")
                    or data.get("document_url")
                    or data.get("termo_url")
                    or (data.get("termoArquivo") or {}).get("data", "")
                    or ""
                ).strip()[:1_500_000],
                "status": "pending",
                "created_at": now(),
            }

            result = db.volunteer_requests.insert_one(
                request
            )

            return self.send_json(
                201,
                {
                    "ok": True,
                    "id": str(result.inserted_id),
                    "message": "Cadastro de voluntário enviado com sucesso.",
                },
            )


        # ----------------------------------------------------
        # CADASTRO DE ADOTANTE
        # ----------------------------------------------------

        if path == "/api/adopters":

            required = [
                "nome",
                "email",
                "telefone",
                "cpf",
                "data_nascimento",
                "senha",
            ]

            if any(
                not str(data.get(field, "")).strip()
                for field in required
            ):
                return self.send_json(
                    400,
                    {
                        "ok": False,
                        "message": (
                            "Preencha todos os campos obrigatórios."
                        ),
                    },
                )


            nome = str(
                data["nome"]
            ).strip()

            email = str(
                data["email"]
            ).strip().lower()

            telefone = str(
                data["telefone"]
            ).strip()

            cpf = str(
                data["cpf"]
            ).strip()

            data_nascimento = str(
                data["data_nascimento"]
            ).strip()

            senha = str(
                data["senha"]
            )


            if len(senha) < 8:
                return self.send_json(
                    400,
                    {
                        "ok": False,
                        "message": (
                            "A senha deve ter pelo menos 8 caracteres."
                        ),
                    },
                )


            if "@" not in email:
                return self.send_json(
                    400,
                    {
                        "ok": False,
                        "message": "Informe um e-mail válido.",
                    },
                )


            if db.adopters.find_one(
                {"email": email}
            ):
                return self.send_json(
                    409,
                    {
                        "ok": False,
                        "message": (
                            "Este e-mail já possui uma conta."
                        ),
                    },
                )


            if db.adopters.find_one(
                {"cpf": cpf}
            ):
                return self.send_json(
                    409,
                    {
                        "ok": False,
                        "message": (
                            "Este CPF já possui uma conta."
                        ),
                    },
                )


            adopter = {
                "name": nome,
                "email": email,
                "phone": telefone,
                "cpf": cpf,
                "birth_date": data_nascimento,
                "password_hash": hash_password(senha),
                "created_at": now(),
            }


            try:
                result = db.adopters.insert_one(
                    adopter
                )

            except Exception as error:
                # Protege contra corrida/índice único.
                if "duplicate key" in str(error).lower():
                    return self.send_json(
                        409,
                        {
                            "ok": False,
                            "message": (
                                "Já existe uma conta com esses dados."
                            ),
                        },
                    )

                raise


            return self.send_json(
                201,
                {
                    "ok": True,
                    "id": str(
                        result.inserted_id
                    ),
                    "message": (
                        "Conta criada com sucesso."
                    ),
                },
            )


        # ----------------------------------------------------
        # LOGIN DO ADOTANTE
        # ----------------------------------------------------

        if path == "/api/auth/adopter-login":

            email = str(
                data.get("email", "")
            ).strip().lower()

            password = str(
                data.get("password", "")
            )


            if not email or not password:
                return self.send_json(
                    400,
                    {
                        "ok": False,
                        "message": (
                            "E-mail e senha são obrigatórios."
                        ),
                    },
                )


            adopter = db.adopters.find_one(
                {"email": email}
            )


            if not adopter:
                return self.send_json(
                    401,
                    {
                        "ok": False,
                        "message": (
                            "E-mail ou senha inválidos."
                        ),
                    },
                )


            valid = verify_password(
                password,
                adopter.get(
                    "password_hash"
                ),
            )


            if not valid:
                return self.send_json(
                    401,
                    {
                        "ok": False,
                        "message": (
                            "E-mail ou senha inválidos."
                        ),
                    },
                )


            token = create_session(
                adopter["_id"],
                "adopter",
            )


            self.send_response(200)

            self.send_header(
                "Content-Type",
                "application/json; charset=utf-8",
            )

            self.send_session_cookie(token)

            self.end_headers()

            response = {
                "ok": True,
                "message": "Acesso autorizado.",
                "user": serialize(adopter),
            }

            self.wfile.write(
                json.dumps(
                    response,
                    ensure_ascii=False,
                ).encode("utf-8")
            )

            return


        # ----------------------------------------------------
        # LOGIN MASTER / VOLUNTÁRIO
        # ----------------------------------------------------

        if path == "/api/auth/login":

            email = str(
                data.get("email", "")
            ).strip().lower()

            password = str(
                data.get("password", "")
            )

            # MASTER: a conta fica na coleção accounts.
            master = db.accounts.find_one({"email": email})

            if master and str(master.get("role", "")).upper() == "MASTER":
                valid = False

                if master.get("password_hash"):
                    valid = verify_password(
                        password,
                        master.get("password_hash"),
                    )
                elif master.get("password"):
                    valid = secrets.compare_digest(
                        str(master.get("password")),
                        password,
                    )

                    if valid:
                        db.accounts.update_one(
                            {"_id": master["_id"]},
                            {
                                "$set": {
                                    "password_hash": hash_password(password)
                                },
                                "$unset": {"password": ""},
                            },
                        )

                if not valid:
                    return self.send_json(
                        401,
                        {
                            "ok": False,
                            "message": "E-mail ou senha inválidos.",
                        },
                    )

                token = create_session(
                    master["_id"],
                    "master",
                )

                self.send_response(200)
                self.send_header(
                    "Content-Type",
                    "application/json; charset=utf-8",
                )
                self.send_session_cookie(token)
                self.end_headers()
                self.wfile.write(
                    json.dumps(
                        {
                            "ok": True,
                            "message": "Acesso Master autorizado.",
                            "user": serialize(master),
                        },
                        ensure_ascii=False,
                    ).encode("utf-8")
                )
                return

            # VOLUNTÁRIO: contas comuns ficam na coleção volunteers.
            volunteer = db.volunteers.find_one({"email": email})

            if not volunteer:
                return self.send_json(
                    401,
                    {
                        "ok": False,
                        "message": "E-mail ou senha inválidos.",
                    },
                )

            valid = False

            if volunteer.get("password_hash"):
                valid = verify_password(
                    password,
                    volunteer.get("password_hash"),
                )
            elif volunteer.get("password"):
                valid = secrets.compare_digest(
                    str(volunteer.get("password")),
                    password,
                )

                if valid:
                    db.volunteers.update_one(
                        {"_id": volunteer["_id"]},
                        {
                            "$set": {
                                "password_hash": hash_password(password)
                            },
                            "$unset": {"password": ""},
                        },
                    )

            if not valid:
                return self.send_json(
                    401,
                    {
                        "ok": False,
                        "message": "E-mail ou senha inválidos.",
                    },
                )

            token = create_session(
                volunteer["_id"],
                "volunteer",
            )

            self.send_response(200)
            self.send_header(
                "Content-Type",
                "application/json; charset=utf-8",
            )
            self.send_session_cookie(token)
            self.end_headers()
            self.wfile.write(
                json.dumps(
                    {
                        "ok": True,
                        "message": "Acesso autorizado.",
                        "user": serialize(volunteer),
                    },
                    ensure_ascii=False,
                ).encode("utf-8")
            )
            return


        # ----------------------------------------------------
        # LOGOUT
        # ----------------------------------------------------

        if path == "/api/auth/logout":

            delete_session(self)

            self.send_response(200)

            self.send_header(
                "Content-Type",
                "application/json; charset=utf-8",
            )

            self.clear_session_cookie()

            self.end_headers()

            self.wfile.write(
                json.dumps(
                    {
                        "ok": True,
                        "message": "Sessão encerrada.",
                    },
                    ensure_ascii=False,
                ).encode("utf-8")
            )

            return



        # ----------------------------------------------------
        # CRIAÇÃO DE EVENTO - MASTER
        # ----------------------------------------------------

        if path == "/api/events":

            if not is_master(self):
                return self.send_json(
                    403,
                    {
                        "ok": False,
                        "message": "Somente a conta Master pode criar eventos.",
                    },
                )

            required = [
                "title",
                "description",
                "date",
                "startTime",
                "endTime",
                "location",
                "spaceDescription",
                "animalLimit",
                "volunteerLimit",
                "spaceLimit",
            ]

            if any(
                data.get(field) in (None, "")
                for field in required
            ):
                return self.send_json(
                    400,
                    {
                        "ok": False,
                        "message": "Preencha todos os campos obrigatórios do evento.",
                    },
                )

            try:
                animal_limit = int(data["animalLimit"])
                volunteer_limit = int(data["volunteerLimit"])
                space_limit = int(data["spaceLimit"])
            except (ValueError, TypeError):
                return self.send_json(
                    400,
                    {
                        "ok": False,
                        "message": "Os limites do evento devem ser números inteiros.",
                    },
                )

            if (
                animal_limit <= 0
                or volunteer_limit <= 0
                or space_limit <= 0
            ):
                return self.send_json(
                    400,
                    {
                        "ok": False,
                        "message": "Os limites do evento devem ser maiores que zero.",
                    },
                )

            session = get_session(self)

            event = {
                "title": str(data["title"]).strip(),
                "description": str(data["description"]).strip(),
                "date": str(data["date"]).strip(),
                "startTime": str(data["startTime"]).strip(),
                "endTime": str(data["endTime"]).strip(),
                "location": str(data["location"]).strip(),
                "spaceDescription": str(data["spaceDescription"]).strip(),
                "animalLimit": animal_limit,
                "volunteerLimit": volunteer_limit,
                "spaceLimit": space_limit,
                "status": "published",
                "createdBy": str(session["user_id"]),
                "createdAt": now(),
            }

            result = db.events.insert_one(event)

            event["_id"] = result.inserted_id

            return self.send_json(
                201,
                {
                    "ok": True,
                    "event": serialize(event),
                    "message": "Evento publicado com sucesso.",
                },
            )


        # ----------------------------------------------------
        # SOLICITAÇÃO DE VAGA EM EVENTO - VOLUNTÁRIO
        # ----------------------------------------------------

        if path == "/api/event-requests":

            volunteer = get_volunteer_from_session(self)

            if not volunteer:
                return self.send_json(
                    401,
                    {
                        "ok": False,
                        "message": "Você precisa estar conectado como voluntário.",
                    },
                )

            event_id = str(
                data.get("eventId", "")
            ).strip()

            animal_id = str(
                data.get("animalId", "")
            ).strip()

            observation = str(
                data.get("observation", "")
            ).strip()

            if not event_id or not animal_id:
                return self.send_json(
                    400,
                    {
                        "ok": False,
                        "message": "Evento e animal são obrigatórios.",
                    },
                )

            event = db.events.find_one(
                {
                    "_id": object_id(event_id)
                }
            )

            if not event:
                return self.send_json(
                    404,
                    {
                        "ok": False,
                        "message": "Evento não encontrado.",
                    },
                )

            if event.get("status") != "published":
                return self.send_json(
                    400,
                    {
                        "ok": False,
                        "message": "Este evento não está recebendo solicitações.",
                    },
                )

            existing = db.event_requests.find_one(
                {
                    "event_id": event_id,
                    "volunteer_id": str(volunteer["_id"]),
                    "animal_id": animal_id,
                }
            )

            if existing:
                return self.send_json(
                    409,
                    {
                        "ok": False,
                        "message": "Este animal já possui uma solicitação para este evento.",
                    },
                )

            counts = get_event_request_counts(
                event_id
            )

            if (
                counts["approvedAnimals"]
                >= int(event.get("animalLimit", 0))
            ):
                return self.send_json(
                    409,
                    {
                        "ok": False,
                        "message": "O limite de animais deste evento já foi atingido.",
                    },
                )

            if (
                counts["approvedRequests"]
                >= int(event.get("volunteerLimit", 0))
            ):
                return self.send_json(
                    409,
                    {
                        "ok": False,
                        "message": "O limite de voluntários deste evento já foi atingido.",
                    },
                )

            request = {
                "event_id": event_id,
                "volunteer_id": str(volunteer["_id"]),
                "animal_id": animal_id,
                "status": "pending",
                "observation": observation,
                "created_at": now(),
            }

            try:
                result = db.event_requests.insert_one(
                    request
                )
            except Exception as error:
                if "duplicate key" in str(error).lower():
                    return self.send_json(
                        409,
                        {
                            "ok": False,
                            "message": "Esta solicitação já existe.",
                        },
                    )
                raise

            request["_id"] = result.inserted_id

            return self.send_json(
                201,
                {
                    "ok": True,
                    "request": serialize(request),
                    "message": "Solicitação enviada e aguardando aprovação.",
                },
            )


        # ----------------------------------------------------
        # SOLICITAÇÕES DE ADOÇÃO
        # ----------------------------------------------------

        if path == "/api/applications":

            if (
                not data.get("applicant_name")
                or not data.get("email")
                or not str(data.get("phone", "")).strip()
            ):
                return self.send_json(
                    400,
                    {
                        "ok": False,
                        "message": (
                            "Nome, e-mail e WhatsApp são obrigatórios para contato."
                        ),
                    },
                )

            if str(data.get("contact_type", "")).lower() == "adocao":
                entrevista = data.get("adoption_interview")
                campos_obrigatorios = (
                    "cpf", "data_nascimento", "estado_civil", "profissao",
                    "empresa", "endereco", "adultos", "criancas",
                    "acordo_casa", "alergias", "motivo",
                    "tratamento", "atividade", "responsavel", "horas_fora",
                    "moradia", "estrutura", "quintal_compartilhado", "moradores",
                    "areas", "periodos", "dormir", "varanda_noite",
                )
                if not isinstance(entrevista, dict) or any(
                    not str(entrevista.get(campo, "")).strip()
                    for campo in campos_obrigatorios
                ):
                    return self.send_json(
                        400,
                        {
                            "ok": False,
                            "message": "Preencha todas as respostas obrigatórias da entrevista de adoção.",
                        },
                    )
                if not isinstance(entrevista.get("documentos"), list) or not entrevista["documentos"]:
                    return self.send_json(400, {"ok": False, "message": "Envie o documento com foto e o comprovante de endereço."})
                if not isinstance(entrevista.get("fotos_lar"), list) or not entrevista["fotos_lar"] or len(entrevista["fotos_lar"]) > 10:
                    return self.send_json(400, {"ok": False, "message": "Envie de 1 a 10 fotos ou vídeos do lar."})
                arquivos = entrevista["documentos"] + entrevista["fotos_lar"]
                if sum(int(arquivo.get("tamanho", 0)) for arquivo in arquivos if isinstance(arquivo, dict)) > 12 * 1024 * 1024:
                    return self.send_json(400, {"ok": False, "message": "O tamanho total dos arquivos deve ser de até 12 MB."})


            session = get_session(self)

            if (
                session
                and session.get("user_type") == "adopter"
            ):
                data["adopter_id"] = session[
                    "user_id"
                ]

            if str(data.get("contact_type", "")).lower() == "adocao":
                animal_id = str(data.get("animal_id", "")).strip()
                if animal_id:
                    animal = db.animals.find_one({"_id": object_id(animal_id)})
                    if animal:
                        data["animal_name"] = animal.get("name", "")
                        data["animal_snapshot"] = {
                            "name": animal.get("name", ""),
                            "species": animal.get("species", ""),
                            "breed": animal.get("breed", ""),
                            "sex": animal.get("sex", ""),
                            "age": animal.get("age", ""),
                            "size": animal.get("size", ""),
                            "image": animal.get("image", ""),
                        }

            data.update(
                {
                    "status": "em análise",
                    "created_at": now(),
                }
            )


            result = db.applications.insert_one(
                data
            )
            email_status = send_adoption_confirmation(data) if str(data.get("contact_type", "")).lower() == "adocao" else "not_applicable"
            db.applications.update_one({"_id": result.inserted_id}, {"$set": {"email_status": email_status}})


            return self.send_json(
                201,
                {
                    "ok": True,
                    "id": str(
                        result.inserted_id
                    ),
                    "message": (
                        "Solicitação registrada."
                    ),
                    "email_status": email_status,
                },
            )


        # ----------------------------------------------------
        # ANIMAIS
        # ----------------------------------------------------

        if path == "/api/animals":

            if (
                not data.get("name")
                or not data.get("species")
            ):
                return self.send_json(
                    400,
                    {
                        "ok": False,
                        "message": (
                            "Nome e espécie são obrigatórios."
                        ),
                    },
                )


            data.update(
                {
                    "status": "disponível",
                    "created_at": now(),
                }
            )


            result = db.animals.insert_one(
                data
            )


            return self.send_json(
                201,
                {
                    "ok": True,
                    "id": str(
                        result.inserted_id
                    ),
                },
            )


        return self.send_json(
            404,
            {
                "ok": False,
                "message": "Rota não encontrada.",
            },
        )



    # ========================================================
    # PUT - APROVAÇÃO/RECUSA DE SOLICITAÇÃO
    # ========================================================

    def do_PUT(self):
        path = urlparse(self.path).path
        data = self.body()

        if path.startswith("/api/applications/"):
            session = get_session(self)
            if not session or session.get("user_type") not in {"master", "volunteer"}:
                return self.send_json(403, {"ok": False, "message": "Apenas a Master e as contas de apoio podem atualizar pedidos."})
            request_object_id = object_id(path.rsplit("/", 1)[-1])
            if not request_object_id:
                return self.send_json(400, {"ok": False, "message": "ID de pedido inválido."})
            updates = {}
            if "adoption_interview" in data:
                if not isinstance(data["adoption_interview"], dict):
                    return self.send_json(400, {"ok": False, "message": "O formulário de adoção precisa ser um objeto válido."})
                updates["adoption_interview"] = data["adoption_interview"]
            status = str(data.get("status", "")).strip().lower()
            if status:
                if status not in {"resolvido", "resolved"}:
                    return self.send_json(400, {"ok": False, "message": "Status inválido."})
                updates.update({"status": "resolvido", "resolved_at": now(), "resolved_by": session["user_id"]})
            if not updates:
                return self.send_json(400, {"ok": False, "message": "Nenhuma alteração informada."})
            result = db.applications.update_one(
                {"_id": request_object_id},
                {"$set": updates},
            )
            if not result.matched_count:
                return self.send_json(404, {"ok": False, "message": "Pedido não encontrado."})
            return self.send_json(200, {"ok": True, "message": "Pedido marcado como resolvido."})

        # ====================================================
        # APROVAR / RECUSAR CADASTRO DE VOLUNTÁRIO - MASTER
        # ====================================================

        if path.startswith("/api/volunteer-requests/"):
            if not is_master(self):
                return self.send_json(403, {
                    "ok": False,
                    "message": "Somente a conta Master pode analisar solicitações de voluntários.",
                })

            request_id = path.rsplit("/", 1)[-1]
            request_object_id = object_id(request_id)
            if not request_object_id:
                return self.send_json(400, {"ok": False, "message": "ID de solicitação inválido."})

            status = str(data.get("status", "")).strip().lower()
            allowed = {"first_phase", "approved", "rejected", "revert"}
            if status not in allowed:
                return self.send_json(400, {"ok": False, "message": "Status inválido."})

            request = db.volunteer_requests.find_one({"_id": request_object_id})
            if not request:
                return self.send_json(404, {"ok": False, "message": "Solicitação de voluntariado não encontrada."})

            current = str(request.get("status", "pending")).lower()
            master_id = str(get_session(self)["user_id"])

            # Reverter uma recusa: volta para a fila pendente e remove o TTL.
            if status == "revert":
                if current != "rejected":
                    return self.send_json(409, {"ok": False, "message": "Somente solicitações recusadas podem ser revertidas."})
                result = db.volunteer_requests.update_one(
                    {"_id": request_object_id},
                    {"$set": {"status": "pending"}, "$unset": {"history_expires_at": "", "reviewed_at": "", "reviewed_by": ""}},
                )
                return self.send_json(200, {"ok": True, "modified": result.modified_count, "message": "Solicitação revertida para pendente."})

            # Recusar em qualquer fase anterior à aprovação final.
            if status == "rejected":
                result = db.volunteer_requests.update_one(
                    {"_id": request_object_id},
                    {"$set": {
                        "status": "rejected",
                        "reviewed_by": master_id,
                        "reviewed_at": now(),
                        "rejected_at": now(),
                        "history_expires_at": datetime.now(timezone.utc) + timedelta(days=30),
                    }},
                )
                return self.send_json(200, {"ok": True, "modified": result.modified_count, "message": "Solicitação recusada."})

            # Primeira aprovação: somente entrevista. NÃO cria conta.
            if status == "first_phase":
                if current != "pending":
                    return self.send_json(409, {"ok": False, "message": "Esta solicitação não está mais pendente."})

                nome = str(request.get("name", request.get("nome", ""))).strip() or "voluntário(a)"
                whatsapp = enviar_whatsapp_primeira_fase(request.get("phone", request.get("telefone", "")), nome)

                result = db.volunteer_requests.update_one(
                    {"_id": request_object_id},
                    {"$set": {
                        "status": "first_phase",
                        "first_phase_at": now(),
                        "reviewed_by": master_id,
                        "reviewed_at": now(),
                        "whatsapp_first_phase_sent": bool(whatsapp.get("sent")),
                    }, "$unset": {"history_expires_at": ""}},
                )

                return self.send_json(200, {
                    "ok": True,
                    "modified": result.modified_count,
                    "message": "Pessoa aprovada para a primeira fase. A conta de voluntário ainda não foi criada.",
                    "whatsapp_sent": whatsapp.get("sent", False),
                    "whatsapp_url": whatsapp.get("whatsapp_url"),
                    "whatsapp_message": whatsapp.get("message"),
                })

            # Só a primeira fase pode virar aprovação final.
            if current != "first_phase":
                return self.send_json(409, {
                    "ok": False,
                    "message": "A pessoa precisa passar pela primeira fase e entrevista antes da aprovação final.",
                })

            email = str(request.get("email", "")).strip().lower()
            if not email or "@" not in email:
                return self.send_json(400, {"ok": False, "message": "A solicitação não possui um e-mail válido."})

            if db.accounts.find_one({"email": email}) or db.adopters.find_one({"email": email}):
                return self.send_json(409, {"ok": False, "message": "Este e-mail já pertence a outro tipo de conta."})

            activation_token = secrets.token_urlsafe(32)
            volunteer = {
                "name": str(request.get("name", "")).strip(),
                "email": email,
                "phone": str(request.get("phone", "")).strip(),
                "modalidades": request.get("modalidades", []),
                "disponibilidade": str(request.get("disponibilidade", "")).strip(),
                "status": "active",
                "first_access_completed": False,
                "activation_token": activation_token,
                "approved_at": now(),
                "approved_by": master_id,
                "created_at": request.get("created_at") or now(),
            }

            existente = db.volunteers.find_one({"email": email})
            if existente:
                db.volunteers.update_one({"_id": existente["_id"]}, {"$set": volunteer})
                volunteer_id = existente["_id"]
            else:
                result_volunteer = db.volunteers.insert_one(volunteer)
                volunteer_id = result_volunteer.inserted_id

            result_request = db.volunteer_requests.update_one(
                {"_id": request_object_id},
                {"$set": {
                    "status": "approved",
                    "interview_completed_at": now(),
                    "reviewed_by": master_id,
                    "reviewed_at": now(),
                    "volunteer_id": str(volunteer_id),
                }, "$unset": {"history_expires_at": ""}},
            )

            whatsapp = enviar_whatsapp_conta_criada(
                request.get("phone", request.get("telefone", "")),
                str(request.get("name", "")).strip() or "voluntário(a)",
                email,
                activation_token,
            )

            db.volunteer_requests.update_one(
                {"_id": request_object_id},
                {"$set": {
                    "whatsapp_account_created_sent": bool(whatsapp.get("sent")),
                    "whatsapp_account_created_message": whatsapp.get("message"),
                }},
            )

            return self.send_json(200, {
                "ok": True,
                "modified": result_request.modified_count,
                "message": "Entrevista concluída e conta de voluntário criada com sucesso.",
                "volunteer_id": str(volunteer_id),
                "activation_token": activation_token,
                "whatsapp_sent": whatsapp.get("sent", False),
                "whatsapp_url": whatsapp.get("whatsapp_url"),
                "whatsapp_message": whatsapp.get("message"),
                "first_access_url": whatsapp.get("first_access_url"),
            })


        if path.startswith("/api/event-requests/"):

            if not is_master(self):
                return self.send_json(
                    403,
                    {
                        "ok": False,
                        "message": "Somente a conta Master pode aprovar solicitações.",
                    },
                )

            request_id = path.rsplit("/", 1)[-1]
            request_object_id = object_id(request_id)

            if not request_object_id:
                return self.send_json(
                    400,
                    {
                        "ok": False,
                        "message": "ID de solicitação inválido.",
                    },
                )

            status = str(
                data.get("status", "")
            ).strip().lower()

            if status not in {"approved", "rejected"}:
                return self.send_json(
                    400,
                    {
                        "ok": False,
                        "message": "O status deve ser approved ou rejected.",
                    },
                )

            request = db.event_requests.find_one(
                {"_id": request_object_id}
            )

            if not request:
                return self.send_json(
                    404,
                    {
                        "ok": False,
                        "message": "Solicitação não encontrada.",
                    },
                )

            if status == "approved":
                event = db.events.find_one(
                    {
                        "_id": object_id(
                            request["event_id"]
                        )
                    }
                )

                if not event:
                    return self.send_json(
                        404,
                        {
                            "ok": False,
                            "message": "Evento não encontrado.",
                        },
                    )

                counts = get_event_request_counts(
                    request["event_id"]
                )

                if request.get("status") != "approved":
                    if (
                        counts["approvedAnimals"]
                        >= int(event.get("animalLimit", 0))
                    ):
                        return self.send_json(
                            409,
                            {
                                "ok": False,
                                "message": "O limite de animais deste evento já foi atingido.",
                            },
                        )

                    if (
                        counts["approvedRequests"]
                        >= int(event.get("volunteerLimit", 0))
                    ):
                        return self.send_json(
                            409,
                            {
                                "ok": False,
                                "message": "O limite de voluntários deste evento já foi atingido.",
                            },
                        )

            result = db.event_requests.update_one(
                {"_id": request_object_id},
                {
                    "$set": {
                        "status": status,
                        "reviewed_by": get_session(self)["user_id"],
                        "reviewed_at": now(),
                    }
                },
            )

            return self.send_json(
                200,
                {
                    "ok": True,
                    "modified": result.modified_count,
                    "message": (
                        "Solicitação aprovada."
                        if status == "approved"
                        else "Solicitação recusada."
                    ),
                },
            )

        return self.send_json(
            404,
            {
                "ok": False,
                "message": "Rota não encontrada.",
            },
        )


    # ========================================================
    # DELETE - EXCLUSÃO DE EVENTO
    # ========================================================

    def do_DELETE(self):
        path = urlparse(self.path).path
        if path == "/api/account/me":
            session = get_session(self)
            if not session:
                return self.send_json(401, {"ok": False, "message": "Você precisa estar conectado."})
            if session.get("user_type") == "master":
                return self.send_json(403, {"ok": False, "message": "A conta Master não pode ser excluída."})
            user_id = object_id(session.get("user_id"))
            if session.get("user_type") == "adopter":
                adopter = db.adopters.find_one({"_id": user_id}) if user_id else None
                if adopter:
                    db.applications.delete_many({"$or": [{"adopter_id": session.get("user_id")}, {"email": adopter.get("email")}]})
                    db.adopters.delete_one({"_id": adopter["_id"]})
            elif session.get("user_type") == "volunteer":
                volunteer = db.volunteers.find_one({"_id": user_id}) if user_id else None
                if volunteer:
                    volunteer_id = str(volunteer["_id"])
                    db.volunteer_requests.delete_many({"email": volunteer.get("email")})
                    db.event_requests.delete_many({"volunteer_id": volunteer_id})
                    db.volunteers.delete_one({"_id": volunteer["_id"]})
            else:
                return self.send_json(403, {"ok": False, "message": "Este tipo de conta não pode ser excluído por esta rota."})
            delete_session(self)
            return self.send_json(200, {"ok": True, "message": "Todos os dados da conta foram removidos."})

        # ====================================================
        # EXCLUSÃO DA CONTA MASTER
        # ====================================================
        if path == "/api/auth/master-account":
            master = get_master_from_session(self)
            if not master or str(master.get("role", "")).upper() != "MASTER":
                return self.send_json(401, {
                    "ok": False,
                    "message": "Você precisa estar conectado como conta Master.",
                })

            data = self.body()
            senha_atual = str(data.get("senhaAtual", ""))
            confirmacao = str(data.get("confirmacao", ""))

            if confirmacao != "EXCLUIR":
                return self.send_json(400, {"ok": False, "message": "Confirmação inválida."})
            if not senha_atual or not verify_password(senha_atual, master.get("password_hash")):
                return self.send_json(401, {"ok": False, "message": "Senha atual incorreta."})

            master_id = str(master["_id"])
            # Eventos criados pela conta são removidos junto com suas solicitações.
            eventos = list(db.events.find({"createdBy": master_id}, {"_id": 1}))
            event_ids = [str(item["_id"]) for item in eventos]
            if event_ids:
                db.event_requests.delete_many({"event_id": {"$in": event_ids}})
                db.events.delete_many({"createdBy": master_id})

            db.accounts.delete_one({"_id": master["_id"]})
            delete_session(self)

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.clear_session_cookie()
            self.end_headers()
            self.wfile.write(json.dumps({
                "ok": True,
                "message": "Conta Master excluída com sucesso."
            }, ensure_ascii=False).encode("utf-8"))
            return

        if path.startswith("/api/animals/"):
            session = get_session(self)
            if not session or session.get("user_type") not in {"volunteer", "master"}:
                return self.send_json(401, {
                    "ok": False,
                    "message": "Faça login para remover animais.",
                })

            animal_oid = object_id(path.rsplit("/", 1)[-1])
            if not animal_oid:
                return self.send_json(400, {"ok": False, "message": "ID de animal inválido."})

            animal = db.animals.find_one({"_id": animal_oid})
            if not animal:
                return self.send_json(404, {"ok": False, "message": "Animal não encontrado."})
            if session.get("user_type") == "volunteer" and str(animal.get("created_by")) != str(session.get("user_id")):
                return self.send_json(403, {
                    "ok": False,
                    "message": "Você só pode remover os animais cadastrados pela sua conta.",
                })

            db.animals.delete_one({"_id": animal_oid})
            return self.send_json(200, {
                "ok": True,
                "message": "Animal removido com sucesso.",
            })

        if path.startswith("/api/events/"):

            if not is_master(self):
                return self.send_json(
                    403,
                    {
                        "ok": False,
                        "message": "Somente a conta Master pode excluir eventos.",
                    },
                )

            event_id = path.rsplit("/", 1)[-1]
            event_object_id = object_id(event_id)

            if not event_object_id:
                return self.send_json(
                    400,
                    {
                        "ok": False,
                        "message": "ID de evento inválido.",
                    },
                )

            result = db.events.delete_one(
                {"_id": event_object_id}
            )

            if not result.deleted_count:
                return self.send_json(
                    404,
                    {
                        "ok": False,
                        "message": "Evento não encontrado.",
                    },
                )

            db.event_requests.delete_many(
                {"event_id": event_id}
            )

            return self.send_json(
                200,
                {
                    "ok": True,
                    "message": "Evento excluído com sucesso.",
                },
            )

        return self.send_json(
            404,
            {
                "ok": False,
                "message": "Rota não encontrada.",
            },
        )


    # ========================================================
    # ARQUIVOS HTML/CSS/JS
    # ========================================================

    def translate_path(self, path):
        requested = urlparse(path).path.lstrip("/")

        if not requested:
            requested = "index.html"

        return str(
            ROOT / requested
        )


# ============================================================
# INICIALIZAÇÃO
# ============================================================

if __name__ == "__main__":
    init_db()

    print(
        "Servidor ativo em "
        "http://127.0.0.1:8000 "
        "(MongoDB Atlas conectado)"
    )
    print("API de eventos: /api/events")
    print("API de solicitações: /api/event-requests")

    ThreadingHTTPServer(
        ("127.0.0.1", 8000),
        App,
    ).serve_forever()