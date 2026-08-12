import importlib.util

CAMINHO = "server.master.py"

spec = importlib.util.spec_from_file_location(
    "server_master",
    CAMINHO
)

server = importlib.util.module_from_spec(spec)

spec.loader.exec_module(server)


# Nova senha da conta MASTER
nova_senha = "2003"

# Gera o hash usando a mesma função do servidor
novo_hash = server.hash_password(nova_senha)


# Atualiza a conta da Bárbara
resultado = server.db.accounts.update_one(
    {
        "email": "barbara@pacotinho.com",
        "role": "MASTER"
    },
    {
        "$set": {
            "password_hash": novo_hash
        },
        "$unset": {
            "password": ""
        }
    }
)


print("Encontrados:", resultado.matched_count)
print("Alterados:", resultado.modified_count)


if resultado.matched_count == 1:
    print("Senha MASTER redefinida com sucesso.")
    print("Nova senha: 2003")
else:
    print("ERRO: conta MASTER não encontrada.")