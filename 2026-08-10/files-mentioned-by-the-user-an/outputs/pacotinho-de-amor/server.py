"""Servidor local do Pacotinho de Amor conectado ao MongoDB Atlas."""

import hashlib
import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from http.cookies import SimpleCookie
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

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

# Arquivos que o servidor NUNCA deve entregar ao navegador.
# Arquivos que começam com "." (como .env e .gitignore) também são bloqueados.
EXTENSOES_BLOQUEADAS = {".py", ".db", ".md", ".example"}

# Campos aceitos ao cadastrar um animal.
CAMPOS_ANIMAL = [
    "name",
    "species",
    "breed",
    "age",
    "size",
    "sex",
    "location",
    "description",
    "image",
]

# Tamanho máximo da foto (em caracteres base64, ~1 MB de imagem).
TAMANHO_MAX_FOTO = 1_500_000

# Pedidos de voluntariado são apagados automaticamente depois deste prazo.
DIAS_GUARDAR_VOLUNTARIOS = 14


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

    # Datas do MongoDB viram texto para poderem ir ao navegador.
    for chave, valor in result.items():
        if isinstance(valor, datetime):
            if valor.tzinfo is None:
                valor = valor.replace(tzinfo=timezone.utc)
            result[chave] = valor.isoformat()

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
    """Retorna se a sessão pertence à conta MASTER."""
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

    db.volunteer_requests.create_index(
        "status",
        name="volunteer_request_status",
    )

    db.volunteer_requests.create_index(
        "created_at",
        name="volunteer_request_created_at",
    )

    # Apaga cada pedido automaticamente quando chega a data em "expires_at".
    db.volunteer_requests.create_index(
        "expires_at",
        expireAfterSeconds=0,
        name="volunteer_request_ttl",
    )

    # Pedidos antigos (de antes dessa regra) ganham a data de expiração
    # contada a partir do dia em que foram enviados.
    for pedido in db.volunteer_requests.find(
        {"expires_at": {"$exists": False}},
        {"created_at": 1},
    ):
        try:
            enviado = datetime.fromisoformat(str(pedido.get("created_at")))
            if enviado.tzinfo is None:
                enviado = enviado.replace(tzinfo=timezone.utc)
        except ValueError:
            enviado = datetime.now(timezone.utc)

        db.volunteer_requests.update_one(
            {"_id": pedido["_id"]},
            {"$set": {"expires_at": enviado + timedelta(days=DIAS_GUARDAR_VOLUNTARIOS)}},
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

        # ----------------------------------------------------
        # SOLICITAÇÕES DE ADOÇÃO (PROTEGIDO)
        # Adotante vê só os próprios pedidos;
        # voluntário e Master veem todos.
        # ----------------------------------------------------

        if path == "/api/applications":
            session = get_session(self)

            if not session:
                return self.send_json(
                    401,
                    {
                        "ok": False,
                        "message": "Você precisa estar conectado.",
                    },
                )

            filtro = {}

            if session.get("user_type") == "adopter":
                filtro = {"adopter_id": session["user_id"]}

            elif session.get("user_type") not in {"volunteer", "master"}:
                return self.send_json(
                    403,
                    {
                        "ok": False,
                        "message": "Acesso não permitido.",
                    },
                )

            applications = db.applications.find(filtro).sort(
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
        # CONTAS DE APOIO - MASTER
        # ----------------------------------------------------
        if path == "/api/volunteer-accounts":
            if not is_master(self):
                return self.send_json(
                    403,
                    {
                        "ok": False,
                        "message": "Somente a conta Master pode consultar as contas de apoio.",
                    },
                )

            accounts = db.volunteers.find(
                {"account_type": "support"}
            ).sort("created_at", -1)

            return self.send_json(
                200,
                [serialize(account) for account in accounts],
            )

        # ----------------------------------------------------
        # SOLICITAÇÕES DE CADASTRO DE VOLUNTÁRIOS - MASTER
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
        # CRIAÇÃO DE CONTA DE APOIO - MASTER
        # ----------------------------------------------------
        if path == "/api/volunteer-accounts":
            master = get_master_from_session(self)

            if not master or str(master.get("role", "")).upper() != "MASTER":
                return self.send_json(
                    403,
                    {
                        "ok": False,
                        "message": "Somente a conta Master pode criar contas de apoio.",
                    },
                )

            nome = str(data.get("nome", "")).strip()
            email = str(data.get("email", "")).strip().lower()
            senha = str(data.get("senha", ""))

            if not nome or not email or not senha:
                return self.send_json(
                    400,
                    {
                        "ok": False,
                        "message": "Preencha nome, e-mail e senha.",
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

            if len(senha) < 8:
                return self.send_json(
                    400,
                    {
                        "ok": False,
                        "message": "A senha deve ter pelo menos 8 caracteres.",
                    },
                )

            # O mesmo e-mail não pode ser usado por outra conta Master,
            # adotante ou voluntário.
            if db.accounts.find_one({"email": email}):
                return self.send_json(
                    409,
                    {
                        "ok": False,
                        "message": "Este e-mail já está em uso.",
                    },
                )

            if db.adopters.find_one({"email": email}):
                return self.send_json(
                    409,
                    {
                        "ok": False,
                        "message": "Este e-mail já está em uso.",
                    },
                )

            if db.volunteers.find_one({"email": email}):
                return self.send_json(
                    409,
                    {
                        "ok": False,
                        "message": "Este e-mail já está em uso.",
                    },
                )

            volunteer = {
                "name": nome,
                "email": email,
                "password_hash": hash_password(senha),
                "account_type": "support",
                "created_by": str(master["_id"]),
                "created_at": now(),
            }

            try:
                result = db.volunteers.insert_one(volunteer)
            except Exception as error:
                if "duplicate key" in str(error).lower():
                    return self.send_json(
                        409,
                        {
                            "ok": False,
                            "message": "Já existe uma conta com este e-mail.",
                        },
                    )
                raise

            volunteer["_id"] = result.inserted_id

            return self.send_json(
                201,
                {
                    "ok": True,
                    "account": serialize(volunteer),
                    "message": "Conta de apoio criada com sucesso.",
                },
            )

        # ----------------------------------------------------
        # CADASTRO DE VOLUNTÁRIO - PÚBLICO
        # ----------------------------------------------------

        if path == "/api/volunteer-requests":
            nome = str(data.get("nome", "")).strip()
            email = str(data.get("email", "")).strip().lower()
            telefone = str(data.get("telefone", "")).strip()
            disponibilidade = str(data.get("disponibilidade", "")).strip()
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

            if any(item not in modalidades_permitidas for item in modalidades):
                return self.send_json(400, {
                    "ok": False,
                    "message": "Uma ou mais formas de voluntariado são inválidas.",
                })

            if not nome or not email or not telefone or not disponibilidade:
                return self.send_json(400, {
                    "ok": False,
                    "message": "Preencha nome, e-mail, telefone e disponibilidade.",
                })

            if not modalidades:
                return self.send_json(400, {
                    "ok": False,
                    "message": "Selecione pelo menos uma forma de voluntariado.",
                })

            if "@" not in email:
                return self.send_json(400, {
                    "ok": False,
                    "message": "Informe um e-mail válido.",
                })

            if not bool(data.get("aceiteTermo")) or not bool(data.get("aceiteLGPD")):
                return self.send_json(400, {
                    "ok": False,
                    "message": "É necessário aceitar o Termo e confirmar a ciência sobre o tratamento dos dados.",
                })

            pendente = db.volunteer_requests.find_one({
                "email": email,
                "status": {"$in": ["pending", "contacted"]},
            })

            if pendente:
                return self.send_json(409, {
                    "ok": False,
                    "message": "Já existe um cadastro de voluntariado pendente para este e-mail.",
                })

            request = {
                "name": nome,
                "email": email,
                "phone": telefone,
                "modalidades": modalidades,
                "disponibilidade": disponibilidade,
                "aceiteTermo": True,
                "aceiteLGPD": True,
                "aceiteImagem": bool(data.get("aceiteImagem")),
                "termoEnviado": bool(data.get("termoEnviado")),
                "status": "pending",
                "created_at": now(),
                "expires_at": datetime.now(timezone.utc) + timedelta(days=DIAS_GUARDAR_VOLUNTARIOS),
            }

            result = db.volunteer_requests.insert_one(request)

            return self.send_json(201, {
                "ok": True,
                "id": str(result.inserted_id),
                "message": "Cadastro de voluntário enviado com sucesso.",
            })

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
                        "message": "Preencha todos os campos obrigatórios.",
                    },
                )

            nome = str(data["nome"]).strip()
            email = str(data["email"]).strip().lower()
            telefone = str(data["telefone"]).strip()
            cpf = str(data["cpf"]).strip()
            data_nascimento = str(data["data_nascimento"]).strip()
            senha = str(data["senha"])

            if len(senha) < 8:
                return self.send_json(
                    400,
                    {
                        "ok": False,
                        "message": "A senha deve ter pelo menos 8 caracteres.",
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

            if db.adopters.find_one({"email": email}):
                return self.send_json(
                    409,
                    {
                        "ok": False,
                        "message": "Este e-mail já possui uma conta.",
                    },
                )

            if db.adopters.find_one({"cpf": cpf}):
                return self.send_json(
                    409,
                    {
                        "ok": False,
                        "message": "Este CPF já possui uma conta.",
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
                result = db.adopters.insert_one(adopter)

            except Exception as error:
                # Protege contra corrida/índice único.
                if "duplicate key" in str(error).lower():
                    return self.send_json(
                        409,
                        {
                            "ok": False,
                            "message": "Já existe uma conta com esses dados.",
                        },
                    )

                raise

            return self.send_json(
                201,
                {
                    "ok": True,
                    "id": str(result.inserted_id),
                    "message": "Conta criada com sucesso.",
                },
            )

        # ----------------------------------------------------
        # LOGIN DO ADOTANTE
        # ----------------------------------------------------

        if path == "/api/auth/adopter-login":

            email = str(data.get("email", "")).strip().lower()
            password = str(data.get("password", ""))

            if not email or not password:
                return self.send_json(
                    400,
                    {
                        "ok": False,
                        "message": "E-mail e senha são obrigatórios.",
                    },
                )

            adopter = db.adopters.find_one({"email": email})

            if not adopter:
                return self.send_json(
                    401,
                    {
                        "ok": False,
                        "message": "E-mail ou senha inválidos.",
                    },
                )

            valid = verify_password(
                password,
                adopter.get("password_hash"),
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

            email = str(data.get("email", "")).strip().lower()
            password = str(data.get("password", ""))

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

            session = get_session(self)

            if not session or session.get("user_type") not in {"master", "volunteer"}:
                return self.send_json(
                    403,
                    {
                        "ok": False,
                        "message": "Somente a conta Master ou uma conta de voluntário pode criar eventos.",
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

            event_id = str(data.get("eventId", "")).strip()
            animal_id = str(data.get("animalId", "")).strip()
            observation = str(data.get("observation", "")).strip()

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

            counts = get_event_request_counts(event_id)

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
                result = db.event_requests.insert_one(request)
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
                        "message": "Nome e e-mail são obrigatórios.",
                    },
                )

            session = get_session(self)

            if (
                session
                and session.get("user_type") == "adopter"
            ):
                data["adopter_id"] = session["user_id"]

            data.update(
                {
                    "status": "em análise",
                    "created_at": now(),
                }
            )

            result = db.applications.insert_one(data)

            return self.send_json(
                201,
                {
                    "ok": True,
                    "id": str(result.inserted_id),
                    "message": "Solicitação registrada.",
                },
            )

        # ----------------------------------------------------
        # ANIMAIS (PROTEGIDO)
        # Só voluntários e a conta Master podem cadastrar.
        # ----------------------------------------------------

        if path == "/api/animals":
            session = get_session(self)

            if not session or session.get("user_type") not in {"volunteer", "master"}:
                return self.send_json(
                    401,
                    {
                        "ok": False,
                        "message": "Faça login como voluntário para cadastrar animais.",
                    },
                )

            # Salva apenas os campos esperados.
            animal = {
                campo: str(data.get(campo, "")).strip()
                for campo in CAMPOS_ANIMAL
            }

            if not animal["name"] or not animal["species"]:
                return self.send_json(
                    400,
                    {
                        "ok": False,
                        "message": "Nome e espécie são obrigatórios.",
                    },
                )

            imagem = animal["image"]

            if imagem and not imagem.startswith(("data:image/", "assets/", "https://")):
                return self.send_json(
                    400,
                    {
                        "ok": False,
                        "message": "A foto enviada não é válida.",
                    },
                )

            if len(imagem) > TAMANHO_MAX_FOTO:
                return self.send_json(
                    400,
                    {
                        "ok": False,
                        "message": "A foto é muito grande. Escolha uma imagem menor.",
                    },
                )

            animal.update(
                {
                    "status": "disponível",
                    "created_at": now(),
                    "created_by": str(session["user_id"]),
                }
            )

            result = db.animals.insert_one(animal)

            return self.send_json(
                201,
                {
                    "ok": True,
                    "id": str(result.inserted_id),
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

        # ====================================================
        # APROVAÇÃO/RECUSA DE CADASTRO DE VOLUNTÁRIO
        # ====================================================
        if path.startswith("/api/volunteer-requests/"):
            if not is_master(self):
                return self.send_json(
                    403,
                    {
                        "ok": False,
                        "message": "Somente a conta Master pode analisar solicitações de voluntários.",
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

            status = str(data.get("status", "")).strip().lower()

            if status not in {"contacted", "approved", "rejected"}:
                return self.send_json(
                    400,
                    {
                        "ok": False,
                        "message": "Status inválido.",
                    },
                )

            request = db.volunteer_requests.find_one(
                {"_id": request_object_id}
            )

            if not request:
                return self.send_json(
                    404,
                    {
                        "ok": False,
                        "message": "Solicitação de voluntariado não encontrada.",
                    },
                )

            result = db.volunteer_requests.update_one(
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
                    "message": {
                        "contacted": "Marcado como chamado no WhatsApp.",
                        "approved": "Voluntário aprovado.",
                        "rejected": "Voluntário recusado.",
                    }[status],
                },
            )

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

            status = str(data.get("status", "")).strip().lower()

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
                        "_id": object_id(request["event_id"])
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

                counts = get_event_request_counts(request["event_id"])

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

        # ====================================================
        # EDITAR ANIMAL (status, responsável, descrição, PCD)
        # Só voluntários e a conta Master.
        # ====================================================
        if path.startswith("/api/animals/"):
            session = get_session(self)

            if not session or session.get("user_type") not in {"volunteer", "master"}:
                return self.send_json(401, {
                    "ok": False,
                    "message": "Faça login para editar animais.",
                })

            animal_oid = object_id(path.rsplit("/", 1)[-1])

            if not animal_oid:
                return self.send_json(400, {"ok": False, "message": "ID de animal inválido."})

            updates = {}
            remover = {}

            if "status" in data:
                status = str(data.get("status", "")).strip().lower()
                if status not in {"disponível", "em adoção", "adotado"}:
                    return self.send_json(400, {"ok": False, "message": "Status inválido."})
                updates["status"] = status

                if status == "adotado":
                    # Data da adoção (AAAA-MM-DD). Sem data, usa hoje (horário de Brasília).
                    data_adocao = str(data.get("adopted_at", "")).strip()
                    if data_adocao:
                        try:
                            datetime.strptime(data_adocao, "%Y-%m-%d")
                        except ValueError:
                            return self.send_json(400, {"ok": False, "message": "Data de adoção inválida."})
                    else:
                        data_adocao = (datetime.now(timezone.utc) - timedelta(hours=3)).strftime("%Y-%m-%d")
                    updates["adopted_at"] = data_adocao
                    updates["adoption_place"] = str(data.get("adoption_place", "")).strip()[:120]
                else:
                    # Voltou para adoção: apaga os dados da adoção
                    remover = {"adopted_at": "", "adoption_place": ""}

            for campo in ("description", "responsible_person"):
                if campo in data:
                    updates[campo] = str(data.get(campo, "")).strip()[:1000]

            if "pcd" in data:
                updates["pcd"] = bool(data.get("pcd"))

            if not updates:
                return self.send_json(400, {"ok": False, "message": "Nenhum dado para atualizar."})

            updates["updated_at"] = now()

            operacao = {"$set": updates}
            if remover:
                operacao["$unset"] = remover

            result = db.animals.update_one({"_id": animal_oid}, operacao)

            if not result.matched_count:
                return self.send_json(404, {"ok": False, "message": "Animal não encontrado."})

            animal = db.animals.find_one({"_id": animal_oid})

            return self.send_json(200, {
                "ok": True,
                "animal": serialize(animal),
                "message": "Animal atualizado.",
            })

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
        # EXCLUSÃO DE CONTA DE APOIO PELA MASTER
        # ====================================================
        if path.startswith("/api/volunteer-accounts/"):
            if not is_master(self):
                return self.send_json(
                    403,
                    {
                        "ok": False,
                        "message": "Somente a conta Master pode excluir contas de apoio.",
                    },
                )

            volunteer_id = path.rsplit("/", 1)[-1]
            volunteer_object_id = object_id(volunteer_id)

            if not volunteer_object_id:
                return self.send_json(
                    400,
                    {
                        "ok": False,
                        "message": "ID de conta inválido.",
                    },
                )

            volunteer = db.volunteers.find_one(
                {
                    "_id": volunteer_object_id,
                    "account_type": "support",
                }
            )

            if not volunteer:
                return self.send_json(
                    404,
                    {
                        "ok": False,
                        "message": "Conta de apoio não encontrada.",
                    },
                )

            # Remove apenas a conta de acesso. Os animais/eventos já publicados
            # continuam registrados no sistema.
            db.volunteers.delete_one({"_id": volunteer_object_id})

            # Invalida qualquer sessão ativa dessa conta.
            tokens = [
                token
                for token, sessao in SESSIONS.items()
                if sessao.get("user_type") == "volunteer"
                and str(sessao.get("user_id")) == str(volunteer_object_id)
            ]
            for token in tokens:
                SESSIONS.pop(token, None)

            return self.send_json(
                200,
                {
                    "ok": True,
                    "message": "Conta de apoio excluída com sucesso.",
                },
            )

        # ====================================================
        # EXCLUSÃO DA CONTA DO PRÓPRIO VOLUNTÁRIO
        # ====================================================
        if path == "/api/auth/volunteer-account":
            volunteer = get_volunteer_from_session(self)

            if not volunteer:
                return self.send_json(
                    401,
                    {
                        "ok": False,
                        "message": "Você precisa estar conectado como voluntário.",
                    },
                )

            data = self.body()
            senha_atual = str(data.get("senhaAtual", ""))
            confirmacao = str(data.get("confirmacao", ""))

            if confirmacao != "EXCLUIR":
                return self.send_json(
                    400,
                    {
                        "ok": False,
                        "message": "Confirmação inválida.",
                    },
                )

            if not senha_atual or not verify_password(
                senha_atual,
                volunteer.get("password_hash"),
            ):
                return self.send_json(
                    401,
                    {
                        "ok": False,
                        "message": "Senha atual incorreta.",
                    },
                )

            # A própria pessoa só pode excluir a própria conta.
            db.volunteers.delete_one({"_id": volunteer["_id"]})
            delete_session(self)

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.clear_session_cookie()
            self.end_headers()
            self.wfile.write(
                json.dumps(
                    {
                        "ok": True,
                        "message": "Sua conta foi excluída com sucesso.",
                    },
                    ensure_ascii=False,
                ).encode("utf-8")
            )
            return

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
    # ARQUIVOS HTML/CSS/JS (PROTEGIDO)
    # Bloqueia .env, código Python, banco local e arquivos
    # fora da pasta do site.
    # ========================================================

    def translate_path(self, path):
        requested = unquote(urlparse(path).path).lstrip("/") or "index.html"
        destino = (ROOT / requested).resolve()

        # Bloqueia arquivos fora da pasta do site
        try:
            partes = destino.relative_to(ROOT).parts
        except ValueError:
            return str(ROOT / "__nao_existe__")

        # Bloqueia arquivos ocultos (.env, .gitignore) e extensões privadas
        if any(p.startswith(".") for p in partes) or destino.suffix.lower() in EXTENSOES_BLOQUEADAS:
            return str(ROOT / "__nao_existe__")

        return str(destino)


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