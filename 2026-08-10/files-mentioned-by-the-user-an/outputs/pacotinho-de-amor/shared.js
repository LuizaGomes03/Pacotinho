(() => {
  const page = location.pathname.split('/').pop() || 'home.html';

  const API =
    location.port === '8000'
      ? '/api'
      : 'http://127.0.0.1:8000/api';

  const atual = (arquivo) =>
    page === arquivo ? 'aria-current="page"' : '';

  /*
   * ============================================================
   * HEADER
   * Todos os estilos ficam no shared.css (nada é injetado aqui),
   * para o header aparecer igual em todas as páginas.
   * ============================================================
   */

  const header = `
  <header class="pa-header">

    <a class="pa-brand" href="home.html" aria-label="Pacotinho de Amor, início">
      <img class="pa-brand-logo" src="assets/logo-footer.png" alt="" width="50" height="50">
      <span>Pacotinho<br>de amor</span>
    </a>

    <nav class="pa-nav" aria-label="Navegação principal">
      <a href="home.html#projeto" ${atual('home.html')}>O Projeto</a>
      <a href="animais-para-adocao.html" ${atual('animais-para-adocao.html')}>Animais</a>
      <a href="eventos.html" ${atual('eventos.html')}>Eventos</a>
      <a href="sobre-o-projeto.html" ${atual('sobre-o-projeto.html')}>Quem Somos</a>
      <a href="quero-ajudar.html" ${atual('quero-ajudar.html')}>Como ajudar</a>
    </nav>

    <div class="pa-header-actions">

      <a class="pa-account" href="minha-conta.html" aria-label="Conta" ${atual('minha-conta.html')}>
        <span class="pa-account-icon" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="8" r="4"/>
            <path d="M4.5 20.5c1.2-3.6 4-5.5 7.5-5.5s6.3 1.9 7.5 5.5"/>
          </svg>
        </span>
        <span class="pa-account-label">Conta</span>
      </a>

      <button type="button" class="pa-menu-toggle" aria-label="Abrir menu" aria-expanded="false" data-no-demo>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true">
          <line x1="4" y1="7" x2="20" y2="7"></line>
          <line x1="4" y1="12" x2="20" y2="12"></line>
          <line x1="4" y1="17" x2="20" y2="17"></line>
        </svg>
      </button>

    </div>

  </header>
  `;

  /*
   * ============================================================
   * FOOTER
   * ============================================================
   */

  const footer = `
    <footer class="pa-footer">

      <div class="pa-footer-inner">

        <div class="pa-footer-brand">
          <img class="pa-footer-logo" src="assets/logo-footer.png" alt="Logo Pacotinho de Amor">
          <div>
            <strong>Pacotinho de Amor</strong>
            <p>
              Projeto independente dedicado a conectar animais
              que precisam de um lar a pessoas dispostas a amar
              para sempre.
            </p>
          </div>
        </div>

        <nav aria-label="Links do rodapé">
          <a href="home.html">Início</a>
          <a href="animais-para-adocao.html">Animais</a>
          <a href="eventos.html">Eventos</a>
          <a href="sobre-o-projeto.html">Quem Somos</a>
          <a href="quero-ajudar.html">Como ajudar</a>
          <a href="politica-privacidade.html">Política de Privacidade</a>
          <a href="termos-uso.html">Termos de Uso</a>
        </nav>

      </div>

      <small>
        Mais de 1.950 animais adotados com amor. © Pacotinho de Amor
      </small>

    </footer>
  `;

  /*
   * ============================================================
   * PADRONIZAÇÃO
   * ============================================================
   */

  document.body.classList.add(
    'pa-standardized',
    `pa-page-${page.replace(/\.html$/, '')}`
  );

  /*
   * ============================================================
   * HEADER NAS PÁGINAS
   * ============================================================
   */

  if (page !== 'painel-voluntario.html') {

    document.body.insertAdjacentHTML('afterbegin', header);

    const cabecalho = document.querySelector('.pa-header');
    const botaoMenu = cabecalho.querySelector('.pa-menu-toggle');

    const fecharMenu = () => {
      cabecalho.classList.remove('pa-menu-aberto');
      botaoMenu.setAttribute('aria-expanded', 'false');
      botaoMenu.setAttribute('aria-label', 'Abrir menu');
    };

    botaoMenu.addEventListener('click', () => {
      const abrir = !cabecalho.classList.contains('pa-menu-aberto');
      cabecalho.classList.toggle('pa-menu-aberto', abrir);
      botaoMenu.setAttribute('aria-expanded', String(abrir));
      botaoMenu.setAttribute('aria-label', abrir ? 'Fechar menu' : 'Abrir menu');
    });

    // Fecha o menu ao clicar fora, ao escolher um link ou com Esc
    document.addEventListener('click', (e) => {
      if (!cabecalho.contains(e.target) || e.target.closest('.pa-nav a')) {
        fecharMenu();
      }
    });

    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') fecharMenu();
    });

    /*
     * "MINHA CONTA"
     * Antes de sair da página, pergunta ao servidor quem está logado
     * e vai direto para o lugar certo. Assim a minha-conta.html
     * não abre (e some) quando a pessoa ainda não entrou.
     */
    const PAGINA_DA_CONTA = {
      adopter: 'minha-conta.html',
      volunteer: 'painel-voluntario.html',
      master: 'painel-master.html'
    };

    const botaoConta = cabecalho.querySelector('.pa-account');
    const rotuloConta = cabecalho.querySelector('.pa-account-label');
    localStorage.removeItem('pa_account_name');
    /*
     * Atualiza o cabeçalho sem depender do localStorage.
     * A sessão do servidor é a fonte de verdade para evitar exibir
     * o nome de uma pessoa que já saiu ou de outra conta.
     */
    async function consultarSessao() {
      try {
        const controle = new AbortController();
        const limite = setTimeout(() => controle.abort(), 4000);

        const resposta = await fetch(`${API}/auth/me`, {
          credentials: 'include',
          signal: controle.signal
        });

        clearTimeout(limite);

        const sessao = await resposta.json().catch(() => ({}));
        return resposta.ok && sessao.ok ? sessao : null;
      } catch {
        return null;
      }
    }

    const sessaoPronta = consultarSessao();
    let sessaoAtual;
    sessaoPronta.then((sessao) => {
      sessaoAtual = sessao || null;
    });

    async function atualizarContaLogada() {
      try {
        const sessao = await sessaoPronta;
        if (!sessao) {
          localStorage.removeItem('pa_account_name');
          rotuloConta.textContent = 'Conta';
          rotuloConta.removeAttribute('title');
          botaoConta.setAttribute('aria-label', 'Conta');
          delete botaoConta.dataset.logged;
          return;
        }

        const usuario = sessao.user || {};
        const nome = String(usuario.name || usuario.nome || '').trim();

        if (!nome) {
          localStorage.removeItem('pa_account_name');
          return;
        }

        const primeiroNome = nome.split(/\s+/)[0];
        rotuloConta.textContent = `Olá, ${primeiroNome}`;
        rotuloConta.title = nome;
        botaoConta.setAttribute('aria-label', `Abrir conta de ${nome}`);
        botaoConta.dataset.logged = 'true';
        localStorage.setItem('pa_account_name', nome);
      } catch {
        localStorage.removeItem('pa_account_name');
        rotuloConta.textContent = 'Conta';
        rotuloConta.removeAttribute('title');
        botaoConta.setAttribute('aria-label', 'Conta');
        delete botaoConta.dataset.logged;
      }
    }

    atualizarContaLogada();

    botaoConta.addEventListener('click', (e) => {

      // Ctrl/Cmd + clique ou botão do meio: deixa abrir em nova aba normalmente
      if (e.ctrlKey || e.metaKey || e.shiftKey || e.button !== 0) return;

      /*
       * Só intercepta quando a consulta em segundo plano já terminou.
       * Se ainda estiver pendente, o navegador navega imediatamente para
       * minha-conta.html, sem deixar o header travado esperando a API.
       */
      if (typeof sessaoAtual === 'undefined') return;

      e.preventDefault();
      const tipo = String(sessaoAtual?.user_type || '').toLowerCase();
      location.href = PAGINA_DA_CONTA[tipo] || 'login.html?next=minha-conta.html';

    });

  }

  /*
   * ============================================================
   * FOOTER NAS PÁGINAS NORMAIS
   * ============================================================
   */

  if (
    page !== 'login.html' &&
    page !== 'painel-voluntario.html' &&
    !document.querySelector('footer.pa-footer')
  ) {
    document.body.insertAdjacentHTML('beforeend', footer);
  }

  /*
   * ============================================================
   * TOAST
   * ============================================================
   */

  document.body.insertAdjacentHTML(
    'beforeend',
    '<div class="pa-toast" role="status" aria-live="polite"></div>'
  );

  const toast = (message) => {
    const el = document.querySelector('.pa-toast');
    if (!el || !message) return;

    el.textContent = message;
    el.classList.add('show');

    clearTimeout(window.paToast);
    window.paToast = setTimeout(() => el.classList.remove('show'), 2600);
  };

  /*
   * ============================================================
   * NAVEGAÇÃO DAS PÁGINAS ANTIGAS
   * ============================================================
   */

  const target = (text) => {

    text = text.toLowerCase().replace(/\s+/g, ' ').trim();

    if (/conheça os animais|conhecer outros animais|voltar para os animais/.test(text)) {
      return 'animais-para-adocao.html';
    }

    if (/quero ajudar|fazer uma doação/.test(text)) {
      return 'quero-ajudar.html';
    }

    // Minha conta / Cadastro
    if (/^conta$|^minha conta$|^cadastro$|^criar conta$|^crie sua conta$/.test(text)) {
      if (/cadastro|criar conta|crie sua conta/.test(text)) {
        return 'cadastro.html';
      }
      return 'minha-conta.html';
    }

    if (/configurar disponibilidade|gerenciar disponibilidade/.test(text)) {
      return 'configurar-disponibilidade.html';
    }

    if (/adicionar compromisso/.test(text)) {
      return 'escolher-forma-contato.html';
    }

    if (/solicitar videochamada/.test(text)) {
      return 'status-adocao-entrevista.html';
    }

    if (/facetime|videochamada/.test(text)) {
      return 'agenda-facetime.html';
    }

    if (/visitar/.test(text)) {
      return 'agenda-visita.html';
    }

    if (/continuar para a entrevista/.test(text)) {
      return 'entrevista_adocao.html';
    }

    if (/quero adotar/.test(text)) {
      return 'processo_adocao.html';
    }

    if (/adicionar animal|cadastrar animal/.test(text)) {
      return 'adicionar-animal.html';
    }

    if (/voltar para o início/.test(text)) {
      return 'home.html';
    }

    if (/solicitar mais informações/.test(text)) {
      return 'solicitacoes-adocao.html';
    }

    if (/agendar visita/.test(text)) {
      return 'status-adocao-entrevista.html';
    }

    return null;
  };

  /*
   * ============================================================
   * BOTÕES COM FUNÇÃO PRÓPRIA
   * ============================================================
   */

  const temFuncaoPropria = (el) =>
    el.id ||
    el.hasAttribute('onclick') ||
    el.getAttribute('type') === 'submit' ||
    Object.keys(el.dataset).length > 0 ||
    el.closest(
      '[data-no-demo], [data-filter-control], [data-panel-menu-toggle], form, dialog, [role="dialog"]'
    );

  document.addEventListener('click', (event) => {

    const element = event.target.closest('button, a[href="#"]');

    if (!element || element.closest('.pa-header, .pa-footer')) {
      return;
    }

    if (temFuncaoPropria(element)) {
      return;
    }

    const dest = target(element.textContent || '');

    if (dest) {
      event.preventDefault();
      location.href = dest;
      return;
    }

    if (element.matches('a[href="#"]')) {
      event.preventDefault();
    }

  });

  /*
   * ============================================================
   * FORMULÁRIO DE ADOÇÃO
   * ============================================================
   */

  const sendApplication = async (form) => {

    const value = (id) =>
      form.querySelector(`#${id}`)?.value.trim() || '';

    const animalId = new URLSearchParams(location.search).get('id') || '';

    try {

      const response = await fetch(`${API}/applications`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          animal_id: animalId,
          applicant_name: value('nome'),
          cpf: value('cpf'),
          email: value('email'),
          phone: value('telefone'),
          birth_date: value('data-nascimento')
        })
      });

      const data = await response.json().catch(() => ({}));

      if (!response.ok) {
        throw new Error(data.message || 'Não foi possível enviar a solicitação.');
      }

      toast(data.message || 'Solicitação enviada.');

      setTimeout(() => {
        location.href = 'status-adocao-enviado.html';
      }, 500);

    } catch (error) {
      toast(error.message);
    }

  };

  /*
   * ============================================================
   * ENVIO DO FORMULÁRIO DE ADOÇÃO
   * ============================================================
   *
   * IMPORTANTE:
   * O cadastro possui #nome e #cpf também.
   * Por isso NÃO basta verificar esses dois campos.
   *
   * O formulário de adoção possui #data-nascimento.
   * O cadastro possui #dataNascimento.
   *
   * Assim, o cadastro não será tratado como adoção.
   */

  const ehFormularioDeAdocao = (form) =>
    form.querySelector('#nome') &&
    form.querySelector('#cpf') &&
    form.querySelector('#data-nascimento');

  document.addEventListener('submit', (event) => {

    const form = event.target;

    if (!(form instanceof HTMLFormElement) || !ehFormularioDeAdocao(form)) {
      return;
    }

    event.preventDefault();
    sendApplication(form);

  });

  /*
   * ============================================================
   * PRÓXIMO — FORMULÁRIO DE ADOÇÃO
   * ============================================================
   */

  document.addEventListener('click', (event) => {

    const botao = event.target.closest('button');
    const form = botao?.closest('form');

    if (!botao || !form || botao.getAttribute('type') !== 'button') {
      return;
    }

    if (!/próximo/i.test(botao.textContent || '')) {
      return;
    }

    if (!ehFormularioDeAdocao(form)) {
      return;
    }

    event.preventDefault();
    sendApplication(form);

  });

})();