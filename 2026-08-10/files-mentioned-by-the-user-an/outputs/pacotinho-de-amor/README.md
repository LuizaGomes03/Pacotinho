# Pacotinho de Amor

## Como executar

No terminal do VS Code, dentro desta pasta, execute:

```powershell
python server.py
```

Depois abra `http://127.0.0.1:8000`. O arquivo `pacotinho.db` é criado automaticamente na primeira execução.

## Banco e APIs

- `GET /api/health` — confirma o servidor e o banco.
- `GET` e `POST /api/animals` — lista e cadastra animais.
- `GET` e `POST /api/applications` — lista e registra solicitações de adoção.
- `POST /api/auth/login` — autenticação de voluntário.

Usuário de demonstração: `voluntario@pacotinhodeamor.org` / `123456`.
