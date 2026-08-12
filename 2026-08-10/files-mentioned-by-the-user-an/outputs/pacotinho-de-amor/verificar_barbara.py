import server

email = "barbara@pacotinho.com"

print("\n=== ACCOUNTS ===")
contas = list(server.db.accounts.find(
    {"email": email},
    {"email": 1, "name": 1, "nome": 1, "role": 1}
))

for conta in contas:
    print(conta)

print("\n=== VOLUNTEERS ===")
voluntarios = list(server.db.volunteers.find(
    {"email": email},
    {"email": 1, "name": 1, "nome": 1, "role": 1}
))

for voluntario in voluntarios:
    print(voluntario)

print("\n=== MASTER ACCOUNTS ===")
masters = list(server.db.accounts.find(
    {"role": "MASTER"},
    {"email": 1, "name": 1, "nome": 1, "role": 1}
))

for master in masters:
    print(master)