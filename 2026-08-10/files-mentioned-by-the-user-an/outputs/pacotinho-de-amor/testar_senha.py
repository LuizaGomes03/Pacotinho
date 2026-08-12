import server

email = "barbara@pacotinho.com"
senha = "Master123!"

conta = server.db.accounts.find_one({"email": email})

if not conta:
    print("ERRO: conta não encontrada.")
else:
    print("Conta encontrada:", conta.get("name"))
    print("Role:", conta.get("role"))

    resultado = server.verify_password(
        senha,
        conta.get("password_hash")
    )

    print("Senha correta:", resultado)