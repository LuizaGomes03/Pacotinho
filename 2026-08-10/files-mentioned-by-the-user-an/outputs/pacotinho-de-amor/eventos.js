/*
 * PRÓXIMOS EVENTOS — usado na home e na página eventos.html
 *
 * Aceita variações comuns do banco:
 *  - campos em inglês ou português (date/data, title/titulo, startTime/horaInicio...)
 *  - datas "2026-10-05", "2026-10-05T00:00:00.000Z", "05/10/2026" ou { $date: ... }
 *  - status "published", "publicado", "ativo", "active", true ou sem status
 *
 * Os estilos dos cards são injetados por este arquivo, então funcionam
 * em qualquer página sem depender do Tailwind.
 */

(() => {

  /* ---------- utilidades ---------- */

  const esc = (v) =>
    String(v ?? "").replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"
    }[c]));

  const limpar = (v) =>
    String(v ?? "").toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "").trim();

  // Primeiro campo preenchido entre vários nomes possíveis
  const pegar = (obj, ...nomes) => {
    for (const n of nomes) {
      if (obj[n] !== undefined && obj[n] !== null && obj[n] !== "") return obj[n];
    }
    return "";
  };

  // Mesmo esquema das outras páginas: funciona no servidor (porta 8000)
  // e também no Live Server / arquivo aberto direto
    const API = "/api";

  function hoje() {
    return new Date().toLocaleDateString("en-CA", { timeZone: "America/Sao_Paulo" });
  }

  // Converte qualquer formato de data para "AAAA-MM-DD" (ou "" se inválida)
  function normalizarData(valor) {
    if (!valor) return "";

    if (typeof valor === "object") {
      valor = valor.$date ?? valor.date ?? "";
      if (typeof valor === "object") valor = valor.$numberLong ?? "";
    }

    if (typeof valor === "number" || /^\d{10,}$/.test(String(valor))) {
      return new Date(Number(valor)).toISOString().slice(0, 10);
    }

    const texto = String(valor).trim();

    // 2026-10-05 ou 2026-10-05T...
    let m = texto.match(/^(\d{4})-(\d{2})-(\d{2})/);
    if (m) return `${m[1]}-${m[2]}-${m[3]}`;

    // 05/10/2026 ou 5/10/2026
    m = texto.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})/);
    if (m) return `${m[3]}-${m[2].padStart(2, "0")}-${m[1].padStart(2, "0")}`;

    return "";
  }

  // "14h", "14:00", "14h30" -> "14:00" / "14:30"
  function normalizarHora(valor) {
    const m = String(valor ?? "").match(/(\d{1,2})\s*[:h]\s*(\d{2})?/i);
    if (!m) return "";
    return `${m[1].padStart(2, "0")}:${m[2] || "00"}`;
  }

  function estaPublicado(status) {
    if (status === undefined || status === null || status === "" || status === true) return true;
    if (status === false) return false;
    return ["published", "publicado", "publicada", "ativo", "ativa", "active"].includes(limpar(status));
  }

  function normalizar(bruto) {
    return {
      title: pegar(bruto, "title", "titulo", "nome", "name") || "Evento",
      date: normalizarData(pegar(bruto, "date", "data", "dataEvento", "data_evento", "eventDate")),
      startTime: normalizarHora(pegar(bruto, "startTime", "start_time", "horaInicio", "hora_inicio", "horario", "hora")),
      endTime: normalizarHora(pegar(bruto, "endTime", "end_time", "horaFim", "hora_fim")),
      location: pegar(bruto, "location", "local", "endereco", "address"),
      description: pegar(bruto, "description", "descricao"),
      status: pegar(bruto, "status", "situacao", "published", "publicado")
    };
  }

  const paraData = (iso) => new Date(`${iso}T12:00:00`);

  function linkMapa(local) {
    return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(local)}`;
  }

  function linkAgenda(e) {
    const junta = (data, hora) =>
      `${data.replaceAll("-", "")}T${(hora || "00:00").replace(":", "")}00`;

    const params = new URLSearchParams({
      action: "TEMPLATE",
      text: `${e.title} — Pacotinho de Amor`,
      dates: `${junta(e.date, e.startTime)}/${junta(e.date, e.endTime || e.startTime)}`,
      ctz: "America/Sao_Paulo",
      location: e.location || "",
      details: e.description || ""
    });

    return `https://calendar.google.com/calendar/render?${params}`;
  }

  /* ---------- estilos dos cards ---------- */

  function injetarEstilos() {
    if (document.getElementById("pv-eventos-estilos")) return;

    const css = `
      .pv-evento {
        --ev-ameixa: #472056;
        --ev-ameixa-escura: #2e1438;
        --ev-ameixa-media: #6d3a80;
        --ev-lilas: #f6f0f7;
        --ev-rosa: #f6cfdf;
        --ev-mel: #f2b84b;
        --ev-suave: #6b5f6e;

        display: flex;
        flex-direction: column;
        padding: 26px;
        border-radius: 28px;
        background: #fff;
        box-shadow: 0 20px 40px -28px rgba(46, 20, 56, .45);
        font-family: "Figtree", "Segoe UI", system-ui, sans-serif;
        color: #2a2230;
        line-height: 1.5;
        box-sizing: border-box;
      }

      .pv-evento * { box-sizing: border-box; }

      .pv-evento__topo {
        display: flex;
        gap: 18px;
        align-items: flex-start;
      }

      .pv-evento__folhinha {
        flex-shrink: 0;
        width: 74px;
        overflow: hidden;
        border-radius: 18px;
        background: var(--ev-lilas);
        text-align: center;
        transform: rotate(-4deg);
      }

      .pv-evento__mes {
        display: block;
        padding: 5px 0 4px;
        background: var(--ev-mel);
        color: var(--ev-ameixa-escura);
        font-weight: 700;
        font-size: 14px;
        text-transform: capitalize;
      }

      .pv-evento__dia {
        display: block;
        padding: 6px 0 10px;
        font-family: "Bricolage Grotesque", "Trebuchet MS", system-ui, sans-serif;
        font-weight: 800;
        font-size: 34px;
        line-height: 1;
        color: var(--ev-ameixa);
      }

      .pv-evento h3 {
        margin: 2px 0 8px;
        font-family: "Bricolage Grotesque", "Trebuchet MS", system-ui, sans-serif;
        font-weight: 700;
        font-size: 22px;
        line-height: 1.15;
        letter-spacing: -.01em;
        color: var(--ev-ameixa-escura);
      }

      .pv-evento__info {
        display: flex;
        align-items: flex-start;
        gap: 7px;
        margin: 4px 0 0;
        font-size: 15px;
        color: var(--ev-suave);
      }

      .pv-evento__info svg {
        flex-shrink: 0;
        width: 17px;
        height: 17px;
        margin-top: 2px;
        color: var(--ev-ameixa);
      }

      .pv-evento__dia-semana {
        text-transform: capitalize;
      }

      .pv-evento__local {
        margin-top: 18px;
        padding: 12px 14px;
        border-radius: 14px;
        background: var(--ev-lilas);
      }

      .pv-evento__local .pv-evento__info {
        margin: 0;
        color: #2a2230;
        font-weight: 600;
      }

      .pv-evento__desc {
        margin: 14px 0 0;
        font-size: 15px;
        color: var(--ev-suave);
        display: -webkit-box;
        -webkit-line-clamp: 3;
        -webkit-box-orient: vertical;
        overflow: hidden;
      }

      .pv-evento__acoes {
        display: flex;
        flex-wrap: wrap;
        gap: 10px;
        margin-top: auto;
        padding-top: 22px;
      }

      .pv-evento__botao {
        flex: 1 1 140px;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        gap: 7px;
        padding: 12px 16px;
        border-radius: 999px;
        border: 2px solid var(--ev-ameixa);
        font-weight: 700;
        font-size: 15px;
        text-decoration: none;
        transition: background .2s, color .2s;
      }

      .pv-evento__botao svg {
        width: 18px;
        height: 18px;
      }

      .pv-evento__botao--cheio {
        background: var(--ev-ameixa);
        color: #fff;
      }

      .pv-evento__botao--cheio:hover {
        background: var(--ev-ameixa-media);
        border-color: var(--ev-ameixa-media);
      }

      .pv-evento__botao--contorno {
        background: #fff;
        color: var(--ev-ameixa);
      }

      .pv-evento__botao--contorno:hover {
        background: var(--ev-ameixa);
        color: #fff;
      }

      .pv-evento__botao:focus-visible {
        outline: 3px solid var(--ev-mel);
        outline-offset: 3px;
      }

      @media (prefers-reduced-motion: reduce) {
        .pv-evento__botao { transition: none; }
      }
    `;

    const tag = document.createElement("style");
    tag.id = "pv-eventos-estilos";
    tag.textContent = css;
    document.head.appendChild(tag);
  }

  /* ---------- card ---------- */

  const icones = {
    calendario: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3.5" y="5" width="17" height="15" rx="3"/><path d="M3.5 10h17M8 3v4M16 3v4"/></svg>`,
    relogio: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/></svg>`,
    pino: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 21s-6.5-5.6-6.5-11a6.5 6.5 0 0 1 13 0c0 5.4-6.5 11-6.5 11z"/><circle cx="12" cy="10" r="2.3"/></svg>`,
    rota: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 11l18-8-8 18-2-8z"/></svg>`,
    agenda: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3.5" y="5" width="17" height="15" rx="3"/><path d="M3.5 10h17M8 3v4M16 3v4M12 13v4M10 15h4"/></svg>`
  };

  function card(e) {
    const data = paraData(e.date);
    const dia = data.getDate();
    const mes = data.toLocaleDateString("pt-BR", { month: "short" }).replace(".", "");
    const diaSemana = data.toLocaleDateString("pt-BR", { weekday: "long" });
    const horario = e.startTime
      ? `${e.startTime}${e.endTime ? " às " + e.endTime : ""}`
      : "";

    return `
      <article class="pv-evento">

        <div class="pv-evento__topo">
          <div class="pv-evento__folhinha" aria-hidden="true">
            <span class="pv-evento__mes">${esc(mes)}</span>
            <span class="pv-evento__dia">${dia}</span>
          </div>

          <div>
            <h3>${esc(e.title)}</h3>
            <p class="pv-evento__info">
              ${icones.calendario}
              <span class="pv-evento__dia-semana">${esc(diaSemana)}, ${dia} de ${esc(mes)}</span>
            </p>
            ${horario ? `<p class="pv-evento__info">${icones.relogio}<span>${esc(horario)}</span></p>` : ""}
          </div>
        </div>

        ${e.location ? `
          <div class="pv-evento__local">
            <p class="pv-evento__info">${icones.pino}<span>${esc(e.location)}</span></p>
          </div>` : ""}

        ${e.description ? `<p class="pv-evento__desc">${esc(e.description)}</p>` : ""}

        <div class="pv-evento__acoes">
          ${e.location ? `
            <a class="pv-evento__botao pv-evento__botao--cheio"
               href="${linkMapa(e.location)}" target="_blank" rel="noopener">
              ${icones.rota} Como chegar
            </a>` : ""}
          <a class="pv-evento__botao pv-evento__botao--contorno"
             href="${linkAgenda(e)}" target="_blank" rel="noopener">
            ${icones.agenda} Salvar na agenda
          </a>
        </div>

      </article>`;
  }

  /* ---------- principal ---------- */

  window.mostrarEventos = async function ({ lista, secao, vazio, limite } = {}) {
    const elLista = document.getElementById(lista);
    const elSecao = secao && document.getElementById(secao);
    const elVazio = vazio && document.getElementById(vazio);

    if (!elLista) {
      console.error("mostrarEventos: elemento da lista não encontrado:", lista);
      return;
    }

    injetarEstilos();

    function mostrarVazio() {
      elLista.innerHTML = "";
      elSecao?.classList.add("hidden");
      elVazio?.classList.remove("hidden");
    }

    try {
      const resposta = await fetch(`${API}/events`, {
        credentials: "include",
        headers: { Accept: "application/json" }
      });

      if (!resposta.ok) throw new Error(`Erro ${resposta.status} ao carregar eventos`);

      const dados = await resposta.json();

      const todos = Array.isArray(dados) ? dados
        : Array.isArray(dados?.events) ? dados.events
        : Array.isArray(dados?.eventos) ? dados.eventos
        : Array.isArray(dados?.data) ? dados.data
        : dados?.event ? [dados.event]
        : [];

      const dataHoje = hoje();
      const descartados = [];

      let proximos = todos
        .map((bruto) => ({ bruto, e: normalizar(bruto || {}) }))
        .filter(({ bruto, e }) => {
          let motivo = "";
          if (!e.date) motivo = "sem data ou data em formato desconhecido";
          else if (!estaPublicado(e.status)) motivo = `status "${e.status}" não é publicado`;
          else if (e.date < dataHoje) motivo = `data ${e.date} já passou`;

          if (motivo) descartados.push({ motivo, evento: bruto });
          return !motivo;
        })
        .map(({ e }) => e)
        .sort((a, b) => `${a.date}${a.startTime}`.localeCompare(`${b.date}${b.startTime}`));

      console.log(`Eventos: ${todos.length} no banco, ${proximos.length} exibidos.`);
      if (descartados.length) console.table(descartados.map((d) => ({ motivo: d.motivo, evento: JSON.stringify(d.evento) })));

      if (limite) proximos = proximos.slice(0, limite);

      if (!proximos.length) {
        mostrarVazio();
        return;
      }

      elLista.innerHTML = proximos.map(card).join("");
      elSecao?.classList.remove("hidden");
      elVazio?.classList.add("hidden");

    } catch (erro) {
      console.error("Erro ao carregar eventos:", erro);
      mostrarVazio();
    }
  };
})();