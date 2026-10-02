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
- `POST /api/volunteer-accounts` — a conta Master cria contas de apoio.
- Contas de apoio podem cadastrar, editar e remover apenas os próprios animais, consultar pedidos de adoção e atualizar suas configurações.
- A conta Master é a única que cria eventos e gerencia voluntários e contas de apoio.
- Contas normais (adotantes) não têm acesso a painel administrativo; usam a conta para adotar animais e se voluntariar.

Usuário de demonstração: `voluntario@pacotinhodeamor.org` / `123456`.
# Confirmação por e-mail

Após uma solicitação de adoção, o servidor envia uma confirmação para o e-mail informado quando o SMTP estiver configurado. Defina as variáveis no `.env` (sem versionar senhas):

```env
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=conta-do-projeto@gmail.com
SMTP_PASSWORD=senha-de-app-do-gmail
SMTP_FROM=conta-do-projeto@gmail.com
SMTP_TLS=true
```

Para Gmail, use uma senha de aplicativo, nunca a senha normal da conta. O campo `email_status` da solicitação registra `sent`, `failed` ou `not_configured`.
