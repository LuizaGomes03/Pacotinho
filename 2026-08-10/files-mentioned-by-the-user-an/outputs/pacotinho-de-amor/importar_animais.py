"""
Importa os animais do portfólio para o MongoDB.

Como usar (na pasta pacotinho-de-amor, com o servidor parado ou não):
    python importar_animais.py

- Animais que ainda não existem no banco são cadastrados.
- Animais que já existem (mesmo nome) são ATUALIZADOS com os dados do portfólio.
- Nenhum animal é apagado.
"""

import json
import os
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pymongo import MongoClient
from pymongo.server_api import ServerApi

PASTA = Path(__file__).resolve().parent


def ler_env():
    env = PASTA / ".env"
    if not env.exists():
        raise SystemExit("Arquivo .env não encontrado nesta pasta.")
    for linha in env.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if linha and not linha.startswith("#") and "=" in linha:
            chave, valor = linha.split("=", 1)
            os.environ.setdefault(chave.strip(), valor.strip().strip('"').strip("'"))


def slug(texto):
    texto = unicodedata.normalize("NFD", texto).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", texto).strip("-")


def main():
    ler_env()
    cliente = MongoClient(os.environ["MONGODB_URI"], server_api=ServerApi("1"))
    colecao = cliente.get_database("pacotinho_de_amor").animals

    animais = json.loads((PASTA / "animais_portfolio.json").read_text(encoding="utf-8"))
    agora = datetime.now(timezone.utc)
    novos = atualizados = 0

    for posicao, dados in enumerate(animais):
        foto = f"assets/{slug(dados['name'])}.jpg"
        if not (PASTA / foto).exists():
            print(f"  ! Foto não encontrada: {foto}")

        campos = {
            "name": dados["name"],
            "species": dados["species"],
            "breed": "Sem raça definida",
            "age": dados["age"],
            "size": dados["size"],
            "sex": dados["sex"],
            "description": dados["description"],
            "health": dados["health"],
            "image": foto,
            "status": "disponível",
        }

        # Procura pelo nome, sem diferenciar maiúsculas/minúsculas
        filtro = {"name": {"$regex": f"^{re.escape(dados['name'])}$", "$options": "i"}}
        existente = colecao.find_one(filtro)

        if existente:
            colecao.update_one({"_id": existente["_id"]}, {"$set": campos})
            atualizados += 1
            print(f"  atualizado: {dados['name']}")
        else:
            # Mantém a ordem do portfólio (o primeiro aparece primeiro no site)
            campos["created_at"] = (agora - timedelta(seconds=posicao)).isoformat()
            colecao.insert_one(campos)
            novos += 1
            print(f"  cadastrado: {dados['name']}")

    print(f"\nPronto! {novos} cadastrado(s) e {atualizados} atualizado(s).")


if __name__ == "__main__":
    main()
