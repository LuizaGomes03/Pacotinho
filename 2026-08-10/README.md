# 🐾 Pacotinho de Amor

Site do **Pacotinho de Amor**, projeto independente de proteção animal em São Paulo.
O projeto resgata animais, cuida deles e ajuda cada um a encontrar uma família.
Mais de 1.950 animais já foram adotados.

O site permite:

- conhecer os animais disponíveis para adoção e pedir uma adoção ou uma videochamada;
- ver os próximos eventos (feirinhas de adoção);
- se cadastrar como voluntário(a), doar por PIX e seguir o projeto;
- acompanhar os próprios pedidos na área **Minha conta**;
- administrar animais, pedidos, voluntários, eventos e relatórios no **painel master**.

---

## Sumário

- [Tecnologias](#tecnologias)
- [Como rodar no computador](#como-rodar-no-computador)
- [Estrutura de pastas](#estrutura-de-pastas)
- [Páginas](#páginas)
- [Tipos de conta](#tipos-de-conta)
- [API](#api)
- [Privacidade e LGPD](#privacidade-e-lgpd)
- [Como contribuir](#como-contribuir)
- [Pendências](#pendências)

---

## Tecnologias

| Parte | Tecnologia |
|---|---|
| Páginas | HTML, CSS e JavaScript puro |
| Visual | CSS próprio (`shared.css`), fontes Bricolage Grotesque e Figtree |
| Painéis internos | Tailwind CSS (via CDN) e Material Symbols |
| Servidor | Python (`server.py`) |
| Banco de dados | MongoDB Atlas, acessado com `pymongo` |

---

## Como rodar no computador

### Antes de começar

Você precisa ter instalado:

- [Python 3](https://www.python.org/downloads/)
- [Git](https://git-scm.com/downloads)
- Acesso ao banco no MongoDB Atlas (peça a connection string para a responsável pelo projeto)

> ⚠️ **Não coloque o projeto dentro do OneDrive, Google Drive ou Dropbox.**
> A sincronização trava arquivos do Git e pode corromper o repositório.
> Use uma pasta comum, como `C:\Projetos`.

### 1. Baixar o projeto

```powershell
cd C:\Projetos
git clone https://github.com/LuizaGomes03/Pacotinho.git
cd Pacotinho
```

### 2. Criar o ambiente Python e instalar as dependências

```powershell
python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
.\.venv\Scripts\Activate.ps1
cd ".\2026-08-10\files-mentioned-by-the-user-an\outputs\pacotinho-de-amor"
pip install -r requirements.txt
```

No macOS ou Linux, ative o ambiente com `source .venv/bin/activate`.

### 3. Criar o arquivo `.env`

Na mesma pasta do `server.py`, crie um arquivo chamado `.env` com o endereço do banco:

```env
MONGODB_URI=mongodb+srv://USUARIO:SENHA@cluster0.xxxxx.mongodb.net/
```

> 🔒 O `.env` guarda a senha do banco. Ele já está no `.gitignore` e **nunca deve ir para o GitHub**.
> Para conferir, rode `git check-ignore .env`: a resposta precisa ser `.env`.

### 4. Iniciar o servidor

```powershell
python server.py
```

Se tudo deu certo, aparece:

```
Servidor ativo em http://127.0.0.1:8000 (MongoDB Atlas conectado)
```

Abra **http://localhost:8000/home.html** no navegador.
Deixe o terminal aberto enquanto usa o site. Para parar o servidor, aperte **Ctrl + C**.

### Problemas comuns

| Mensagem | O que fazer |
|---|---|
| `Crie o arquivo .env com MONGODB_URI antes de iniciar o servidor` | Falta o `.env` (passo 3). |
| `ModuleNotFoundError: No module named ...` | O ambiente não está ativo ou faltou o `pip install -r requirements.txt`. |
| O PowerShell não deixa ativar o `.venv` | Rode `Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned` antes. |
| O site abre mas não carrega animais nem eventos | O servidor não está rodando, ou o site foi aberto pelo arquivo direto em vez de `localhost:8000`. |
| As mudanças não aparecem no navegador | Recarregue sem cache com **Ctrl + Shift + R**. |

---

## Estrutura de pastas

Todo o site fica em:

```
2026-08-10/files-mentioned-by-the-user-an/outputs/pacotinho-de-amor/
```

Os arquivos principais são:

```
pacotinho-de-amor/
├── server.py            # servidor e API
├── requirements.txt     # dependências do Python
├── .env                 # endereço do banco (não vai para o GitHub)
├── shared.css           # visual do header, footer e base de todas as páginas
├── shared.js            # header, footer, menu do celular e funções comuns
├── eventos.js           # lista de eventos (home e página de eventos)
├── assets/              # imagens e logo
└── *.html               # páginas do site
```

O header e o footer **não ficam em cada página**: o `shared.js` insere os dois automaticamente.
Para mudar o menu ou o rodapé, edite só o `shared.js` (estrutura) e o `shared.css` (visual).

---

## Páginas

### Site público

| Página | O que faz |
|---|---|
| `home.html` | Página inicial, com animais em destaque, próximos eventos, como adotar e doação por PIX |
| `animais-para-adocao.html` | Lista de animais com busca e filtros (espécie, sexo, idade e porte) |
| `detalhes-animal.html` | Perfil de um animal |
| `processo_adocao.html` / `entrevista_adocao.html` | Pedido de adoção |
| `agenda-facetime.html` | Pedido de videochamada para conhecer um animal |
| `eventos.html` | Próximas feirinhas de adoção |
| `sobre-o-projeto.html` | Quem somos, como adotar e como ajudar (voluntariado, PIX e Instagram) |
| `quero-ajudar.html` | Formas de ajudar e cadastro de voluntário(a) |
| `politica-privacidade.html` / `termos-uso.html` | Documentos legais |

### Contas

| Página | O que faz |
|---|---|
| `login.html` | Login único para todos os tipos de conta. Cada conta é levada para a sua área |
| `cadastro.html` | Cadastro de adotante |
| `minha-conta.html` | Área do adotante: solicitações, dados pessoais, privacidade e central de ajuda |
| `painel-voluntario.html` | Área do(a) voluntário(a) |
| `painel-master.html` | Administração completa do projeto |
| `adicionar-animal.html` | Cadastro de animal |

---

## Tipos de conta

| Tipo (`user_type`) | Quem é | Para onde vai depois do login |
|---|---|---|
| `adopter` | Pessoa que quer adotar | `minha-conta.html` |
| `volunteer` | Voluntário(a) ou conta de apoio | `painel-voluntario.html` |
| `master` | Administração do projeto | `painel-master.html` |

O login tenta primeiro `/api/auth/login` (master e voluntário) e depois `/api/auth/adopter-login` (adotante).
Em seguida, confirma o tipo de conta em `/api/auth/me`.

### O que o painel master faz

- **Animais:** cadastrar, editar, deletar e marcar como adotado.
- **Solicitações:** ver pedidos de adoção e de videochamada, chamar a pessoa no WhatsApp e marcar como resolvido.
- **Adotados:** histórico com data, local e adotante, além de um relatório para imprimir ou salvar em PDF.
- **Voluntários:** aprovar, recusar e conversar pelo WhatsApp.
- **Contas de apoio:** criar acessos limitados para a equipe.
- **Eventos:** criar eventos e, ao final, registrar quantos **filhotes e adultos, cães e gatos** foram adotados.
- **Relatórios:** adoções por período, zona, espécie e mês, e ranking dos eventos.

---

## API

Todas as rotas começam com `/api` e usam JSON. As rotas protegidas usam a sessão por cookie, criada no login.

### Autenticação

| Método | Rota | Uso |
|---|---|---|
| `POST` | `/auth/login` | Login de master e voluntário(a) |
| `POST` | `/auth/adopter-login` | Login de adotante |
| `GET` | `/auth/me` | Retorna a conta logada e o `user_type` |
| `POST` | `/auth/logout` | Sai da conta |
| `PUT` | `/auth/master-profile` | Atualiza nome, e-mail, senha e foto do master |

### Dados

| Método | Rota | Uso |
|---|---|---|
| `GET` | `/animals` | Lista os animais |
| `PUT` / `DELETE` | `/animals/:id` | Edita ou remove um animal |
| `GET` / `POST` | `/applications` | Pedidos de adoção e de videochamada |
| `PUT` | `/applications/:id` | Atualiza um pedido |
| `GET` / `POST` | `/volunteer-requests` | Cadastros de voluntários |
| `PUT` | `/volunteer-requests/:id` | Aprova, recusa ou marca como resolvido |
| `GET` / `POST` | `/events` | Eventos |
| `PUT` / `DELETE` | `/events/:id` | Edita, fecha (com resultados) ou remove um evento |
| `GET` | `/event-requests` | Inscrições em eventos |
| `GET` | `/event-reports` | Resultados de eventos já encerrados |

### Formato de um evento

```json
{
  "title": "Feirinha de adoção — Petland Ipiranga",
  "description": "Feirinha de adoção na Zona Sul.",
  "date": "2026-10-03",
  "startTime": "10:00",
  "endTime": "15:00",
  "location": "Petland Ipiranga, Rua Bom Pastor, 2177 - Ipiranga, São Paulo",
  "status": "published",
  "expiresAt": { "$date": "2026-10-04T03:00:00Z" }
}
```

- O site só mostra eventos com `status: "published"` (ou sem status) e com data de hoje em diante.
- Eventos com `status: "closed"` (eventos fechados ao público) ficam no banco, mas não aparecem no site.
- O campo `expiresAt` permite que o MongoDB apague o evento sozinho depois que ele passa, com um **índice TTL** no campo: `{ "expiresAt": 1 }` com `{ "expireAfterSeconds": 0 }`.

---

## Privacidade e LGPD

O site trata dados pessoais (nome, contato, endereço, CPF), então segue alguns cuidados:

- **Voluntariado:** o formulário pede ciência sobre o uso dos dados e trata o uso de imagem como opcional.
- **Minha conta:** o titular pode **ver, corrigir, baixar e pedir a exclusão** dos próprios dados. O CPF aparece mascarado por padrão.
- **Relatórios:** adotantes e voluntários aparecem só em contagens agrupadas.
- **Senhas e chaves** ficam fora do código, no `.env`.

Antes de colocar o site no ar, confira:

- [ ] As senhas são guardadas com hash (por exemplo, bcrypt), nunca em texto puro.
- [ ] O site usa **HTTPS** em produção.
- [ ] O acesso de rede do MongoDB Atlas não está liberado para qualquer IP (`0.0.0.0/0`).
- [ ] Os pedidos de exclusão são de fato atendidos pela equipe.
- [ ] Existe um prazo definido para guardar pedidos antigos e termos assinados.
- [ ] A Política de Privacidade descreve o que o site realmente faz.

---

## Como contribuir

1. Atualize o projeto antes de começar:
   ```powershell
   git pull
   ```
2. Faça as alterações e teste com o servidor rodando.
3. Confira o que mudou. O `.env` e o `.venv` **não podem** aparecer na lista:
   ```powershell
   git status
   ```
4. Salve e envie:
   ```powershell
   git add -A
   git commit -m "Descreva o que mudou"
   git push
   ```

Se o `git push` for recusado, rode `git pull` antes. Evite `git push --force`, porque ele pode apagar o trabalho de outras pessoas.

---

## Pendências

- [ ] Criar a rota `/api/volunteer-accounts` no servidor (contas de apoio do painel master).
- [ ] Criar a rota `PATCH /api/auth/me` (edição de dados na Minha conta).
- [ ] Garantir que o servidor salve os campos `puppies_dogs`, `puppies_cats`, `adult_dogs` e `adult_cats` ao fechar um evento.
- [ ] Adicionar a foto `assets/animais/luna.jpg` usada no topo da página de animais.
- [ ] Recuperação de senha para adotantes.
- [ ] Mover o site para a raiz do repositório (ou para uma pasta `site/`) e encurtar o caminho atual.

---

## Contato

- Instagram: [@projeto.pacotinhodeamor](https://www.instagram.com/projeto.pacotinhodeamor/)
- WhatsApp: [whats.link/projetopacotinhodeamor](https://whats.link/projetopacotinhodeamor)
