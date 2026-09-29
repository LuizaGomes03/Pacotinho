(() => {
  const page = location.pathname.split('/').pop() || 'home.html';

  const API =
    location.port === '8000'
      ? '/api'
      : 'http://127.0.0.1:8000/api';

  /*
   * ============================================================
   * HEADER
   * ============================================================
   */

 const header = `
  <header class="pa-header">

    <a
      class="pa-brand"
      href="home.html"
      aria-label="Pacotinho de Amor, início"
    >
      <img
        class="pa-brand-logo"
        src="assets/logo-footer.png"
        alt="Logo Pacotinho de Amor"
      >

      <span>
        Pacotinho<br>
        de amor
      </span>
    </a>

    <nav class="pa-nav" aria-label="Navegação principal">

      <a
        href="home.html#projeto"
        ${page === 'home.html' ? 'aria-current="page"' : ''}
      >
        O Projeto
      </a>

      <a
        href="animais-para-adocao.html"
        ${page === 'animais-para-adocao.html' ? 'aria-current="page"' : ''}
      >
        Animais
      </a>

      <a
        href="sobre-o-projeto.html"
        ${page === 'sobre-o-projeto.html' ? 'aria-current="page"' : ''}
      >
        Quem Somos
      </a>

      <a
        href="quero-ajudar.html"
        ${page === 'quero-ajudar.html' ? 'aria-current="page"' : ''}
      >
        Como ajudar
      </a>

    </nav>

    <div class="pa-header-actions">

      <a
        class="pa-account"
        href="login.html"
        aria-label="Minha conta"
        ${page === 'login.html' ? 'aria-current="page"' : ''}
      >
        <span class="pa-account-label">
          Conta
        </span>
      </a>

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

          <img
            class="pa-footer-logo"
            src="assets/logo-footer.png"
            alt="Logo Pacotinho de Amor"
          >

          <div>

            <strong>
              Pacotinho de Amor
            </strong>

            <p>
              Projeto independente dedicado a conectar animais
              que precisam de um lar a pessoas dispostas a amar
              para sempre.
            </p>

          </div>

        </div>


        <nav aria-label="Links do rodapé">

          <a href="home.html">
            Início
          </a>


          <a href="animais-para-adocao.html">
            Animais
          </a>


          <a href="home.html#projeto">
    Projeto
</a>


          <a href="quero-ajudar.html">
            Como ajudar
          </a>



          <a href="politica-privacidade.html">
            Política de Privacidade
          </a>


          <a href="termos-uso.html">
            Termos de Uso
          </a>

        </nav>

      </div>


      <small>
        Mais de 1.950 animais adotados com amor.
        © Pacotinho de Amor
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
   * O painel do voluntário possui layout próprio.
   * As outras páginas recebem o header.
   */

  if (page !== 'painel-voluntario.html') {

    document.body.insertAdjacentHTML(
      'afterbegin',
      header
    );

  }


  /*
   * Adiciona o footer nas páginas normais.
   */

  if (
    page !== 'login.html' &&
    page !== 'painel-voluntario.html' &&
    !document.querySelector('footer.pa-footer')
  ) {

    document.body.insertAdjacentHTML(
      'beforeend',
      footer
    );

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


  /*
   * ============================================================
   * DESTINOS DOS BOTÕES
   * ============================================================
   */

  const target = (text) => {

    text = text
      .toLowerCase()
      .replace(/\s+/g, ' ')
      .trim();


    if (
      /conheça os animais|view all pets|browse pets|conhecer outros animais|voltar para os animais/.test(text)
    ) {

      return 'animais-para-adocao.html';

    }


    if (/conhecer animal/.test(text)) {

      return 'detalhes-animal-luna.html';

    }


    if (/quero ajudar|fazer uma doação/.test(text)) {

      return 'quero-ajudar.html';

    }


    /*
     * Conta agora abre o LOGIN DO ADOTANTE.
     */

    if (/^conta$/.test(text)) {

      return 'login.html';

    }


    if (
      /ver próximas feirinhas|próximas feirinhas de adoção/.test(text)
    ) {

      return 'gerenciamento-feirinhas.html';

    }


    if (
      /configurar disponibilidade|gerenciar disponibilidade/.test(text)
    ) {

      return 'configurar-disponibilidade.html';

    }


    if (/adicionar compromisso/.test(text)) {

      return 'escolher-forma-contato.html';

    }


    if (/visitar/.test(text)) {

      return 'agenda-visita.html';

    }


    if (/facetime|videochamada/.test(text)) {

      return 'agenda-facetime.html';

    }


    if (/solicitar videochamada/.test(text)) {

      return 'status-adocao-entrevista.html';

    }


    if (/continuar para a entrevista/.test(text)) {

      return 'entrevista-adocao-luna.html';

    }


    if (/quero adotar/.test(text)) {

      return 'quero-adotar-luna.html';

    }


    if (/adicionar animal|cadastrar animal/.test(text)) {

      return 'adicionar-animal.html';

    }


    if (/aprovar para entrevista/.test(text)) {

      return 'status-adocao-entrevista.html';

    }


    if (/voltar para o início|\bhome\b/.test(text)) {

      return 'home.html';

    }


    if (/voltar/.test(text)) {

      return 'home.html';

    }


    if (/entrar/.test(text)) {

      return 'painel-voluntario.html';

    }


    if (/solicitar mais informações/.test(text)) {

      return 'solicitacoes-adocao.html';

    }


    if (/agendar visita/.test(text)) {

      return 'status-adocao-entrevista.html';

    }


    if (/publicar animal/.test(text)) {

      return 'gerenciamento-animais.html';

    }


    return null;

  };


  /*
   * ============================================================
   * TOAST
   * ============================================================
   */

  const toast = (message) => {

    const el = document.querySelector('.pa-toast');

    if (!el) return;


    el.textContent = message;

    el.classList.add('show');


    clearTimeout(window.paToast);


    window.paToast = setTimeout(() => {

      el.classList.remove('show');

    }, 2600);

  };


  /*
   * ============================================================
   * API
   * ============================================================
   */

  const request = async (route, payload) => {

    const response = await fetch(`${API}${route}`, {

      method: 'POST',

      headers: {
        'Content-Type': 'application/json'
      },

      body: JSON.stringify(payload)

    });


    const data = await response.json();


    if (!response.ok) {

      throw new Error(
        data.message ||
        'Não foi possível concluir a ação.'
      );

    }


    return data;

  };


  /*
   * ============================================================
   * FORMULÁRIO DE ADOÇÃO
   * ============================================================
   */

  const sendApplication = async (form) => {

    const value = (id) =>
      form.querySelector(`#${id}`)?.value.trim() || '';


    try {

      const result = await request('/applications', {

        animal_id: 1,

        applicant_name: value('nome'),

        cpf: value('cpf'),

        email: value('email'),

        phone: value('telefone'),

        birth_date: value('data-nascimento')

      });


      toast(result.message);


      setTimeout(() => {

        location.href = 'status-adocao-enviado.html';

      }, 500);


    } catch (error) {

      toast(error.message);

    }

  };


  /*
   * ============================================================
   * CLIQUES
   * ============================================================
   */

  document.addEventListener('click', (event) => {

    const element =
      event.target.closest('button, a[href="#"]');


    /*
     * Não interferir no header e footer.
     */

    if (
      !element ||
      element.closest('.pa-header, .pa-footer')
    ) {

      return;

    }


    if (element.closest('[data-filter-control]')) {

      return;

    }


    if (element.closest('[data-panel-menu-toggle]')) {

      return;

    }


    // Não interferir em botões que possuem comportamento real próprio.
    if (element.closest('[data-no-demo]')) {

      return;

    }


    if (
      element instanceof HTMLButtonElement &&
      element.type === 'submit' &&
      element.closest('form')
    ) {

      return;

    }


    if (
      /próximo/.test(element.textContent || '') &&
      element.closest('form')?.querySelector('#nome')
    ) {

      event.preventDefault();


      sendApplication(
        element.closest('form')
      );


      return;

    }


    const dest =
      target(element.textContent || '');


    if (dest) {

      event.preventDefault();

      location.href = dest;

      return;

    }


    if (element.matches('a[href="#"]')) {

      event.preventDefault();

    }


    if (element.tagName === 'BUTTON') {

      event.preventDefault();


      toast(
        'Ação registrada. Esta demonstração não envia dados reais.'
      );

    }

  });


  /*
   * ============================================================
   * FORMULÁRIOS / LOGIN
   * ============================================================
   */

  document.addEventListener('submit', async (event) => {

    const form = event.target;


    if (!(form instanceof HTMLFormElement)) {

      return;

    }


    event.preventDefault();


    const isLogin =
      form.querySelector('input[type="password"]');


    if (!isLogin) {

      return sendApplication(form);

    }


    const email =
      form.querySelector('#email')?.value.trim() || '';


    const password =
      form.querySelector('#password')?.value || '';


    /*
      * ========================================================
      * LOGIN ÚNICO
      * ========================================================
      * O backend informa o tipo da conta:
      * MASTER      -> painel-master.html
      * VOLUNTÁRIO  -> painel-voluntario.html
      * ADOTANTE    -> pagina-adotante.html
      * ========================================================
     */

    if (page === 'login.html') {

      if (!email || !password) {
        toast('Preencha seus dados para continuar.');
        return;
      }

      try {

        const result =
          await request('/auth/login', {

            email: email,

            password: password

          });


        toast(
          result.message ||
          'Acesso autorizado'
        );


        const userType =
          String(
            result.user_type ||
            result.userType ||
            result.user?.user_type ||
            result.user?.userType ||
            result.user?.role ||
            result.role ||
            ''
          ).toLowerCase().trim();


        setTimeout(() => {

          if (
            userType === 'master' ||
            userType === 'admin'
          ) {

            location.href = 'painel-master.html';
            return;

          }


          if (
            userType === 'voluntario' ||
            userType === 'volunteer'
          ) {

            location.href = 'painel-voluntario.html';
            return;

          }


          if (
            userType === 'adotante' ||
            userType === 'adopter'
          ) {

            location.href = 'pagina-adotante.html';
            return;

          }


          toast(
            'A conta foi autenticada, mas o tipo de acesso não foi identificado.'
          );

        }, 500);


        return;

      } catch (error) {

        toast(
          error.message ||
          'E-mail ou senha incorretos.'
        );


        return;

      }

    }


    /*
     * ========================================================
     * FALLBACK DE LOGIN
     * ========================================================
     */

    try {

      const result =
        await request('/auth/login', {

          email: email,

          password: password

        });


      toast(result.message);


      setTimeout(() => {

        location.href = 'painel-voluntario.html';

      }, 500);


    } catch (error) {

      toast(error.message);

    }

  });

})();