"""Servidor local do Pacotinho de Amor conectado ao MongoDB Atlas."""

import hashlib
import json
import os
import secrets
from datetime import datetime, timezone
from http.cookies import SimpleCookie
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

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

    init_event_indexes()


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
        # EVENTOS
        # ----------------------------------------------------

        if path == "/api/events":
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

            if session.get("user_type") != "volunteer":
                return self.send_json(
                    403,
                    {
                        "ok": False,
                        "message": "Apenas voluntários podem acessar solicitações de eventos.",
                    },
                )

            current_volunteer_id = str(
                session["user_id"]
            )

            # O voluntário só pode consultar as próprias solicitações.
            if volunteer_id and volunteer_id != current_volunteer_id:
                return self.send_json(
                    403,
                    {
                        "ok": False,
                        "message": "Você só pode consultar suas próprias solicitações.",
                    },
                )

            request_filter = {
                "volunteer_id": current_volunteer_id
            }

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


        return super().do_GET()


    # ========================================================
    # POST
    # ========================================================

    def do_POST(self):
        path = urlparse(self.path).path
        data = self.body()


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
                            "user_type": "master",
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
                        "user_type": "volunteer",
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
            ):
                return self.send_json(
                    400,
                    {
                        "ok": False,
                        "message": (
                            "Nome e e-mail são obrigatórios."
                        ),
                    },
                )


            session = get_session(self)

            if (
                session
                and session.get("user_type") == "adopter"
            ):
                data["adopter_id"] = session[
                    "user_id"
                ]


            data.update(
                {
                    "status": "em análise",
                    "created_at": now(),
                }
            )


            result = db.applications.insert_one(
                data
            )


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

        # ====================================================
        # PERFIL DA CONTA MASTER
        # ====================================================
        if path == "/api/auth/master-profile":
            master = get_master_from_session(self)
            if not master or str(master.get("role", "")).upper() != "MASTER":
                return self.send_json(401, {
                    "ok": False,
                    "message": "Você precisa estar conectado como conta Master.",
                })

            updates = {}

            if "nome" in data:
                nome = str(data.get("nome", "")).strip()
                if not nome:
                    return self.send_json(400, {"ok": False, "message": "Informe seu nome."})
                updates["name"] = nome
                # Mantém compatibilidade caso algum dado antigo use nome.
                updates["nome"] = nome

            if "email" in data:
                email = str(data.get("email", "")).strip().lower()
                if not email or "@" not in email:
                    return self.send_json(400, {"ok": False, "message": "Informe um e-mail válido."})
                existente = db.accounts.find_one({
                    "email": email,
                    "_id": {"$ne": master["_id"]},
                })
                if existente:
                    return self.send_json(409, {"ok": False, "message": "Este e-mail já está em uso."})
                updates["email"] = email

            if "profile_photo" in data:
                foto = data.get("profile_photo")
                if foto is not None:
                    foto = str(foto)
                    if not foto.startswith("data:image/"):
                        return self.send_json(400, {"ok": False, "message": "A foto enviada não é válida."})
                    if len(foto) > 2_000_000:
                        return self.send_json(400, {"ok": False, "message": "A foto é muito grande. Escolha uma imagem menor."})
                updates["profile_photo"] = foto

            if "senhaAtual" in data or "novaSenha" in data:
                senha_atual = str(data.get("senhaAtual", ""))
                nova_senha = str(data.get("novaSenha", ""))
                if not senha_atual or not nova_senha:
                    return self.send_json(400, {"ok": False, "message": "Informe a senha atual e a nova senha."})
                if len(nova_senha) < 8:
                    return self.send_json(400, {"ok": False, "message": "A nova senha deve ter pelo menos 8 caracteres."})
                if not verify_password(senha_atual, master.get("password_hash")):
                    return self.send_json(401, {"ok": False, "message": "A senha atual está incorreta."})
                updates["password_hash"] = hash_password(nova_senha)

            if not updates:
                return self.send_json(400, {"ok": False, "message": "Nenhum dado para atualizar."})

            db.accounts.update_one({"_id": master["_id"]}, {"$set": updates})
            atualizado = db.accounts.find_one({"_id": master["_id"]})
            return self.send_json(200, {
                "ok": True,
                "user": serialize(atualizado),
                "message": "Perfil atualizado com sucesso.",
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