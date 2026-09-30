/*
 * PRÓXIMOS EVENTOS — usado na home e na página eventos.html
 *
 * Uso:
 *   mostrarEventos({ lista: "id-da-lista", secao: "id-da-secao", limite: 3 });
 *
 * - lista:  onde os cards são colocados
 * - secao:  (opcional) bloco inteiro que fica escondido quando não há eventos
 * - vazio:  (opcional) elemento que aparece quando não há eventos
 * - limite: (opcional) quantos eventos mostrar
 */

(() => {
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"
  }[c]));

  // Data de hoje no formato AAAA-MM-DD (horário do Brasil)
  function hoje() {
    return new Date().toLocaleDateString("en-CA", { timeZone: "America/Sao_Paulo" });
  }

  // "2026-10-12" -> Date ao meio-dia (evita erro de fuso)
  const paraData = (iso) => new Date(`${iso}T12:00:00`);

  function linkMapa(local) {
    return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(local)}`;
  }

  // Link que abre o Google Agenda já com o evento preenchido
  function linkAgenda(e) {
    const junta = (data, hora) => `${data.replaceAll("-", "")}T${(hora || "00:00").replace(":", "")}00`;
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

  function card(e) {
    const data = paraData(e.date);
    const dia = data.getDate();
    const mes = data.toLocaleDateString("pt-BR", { month: "short" }).replace(".", "");
    const diaSemana = data.toLocaleDateString("pt-BR", { weekday: "long" });
    const horario = e.startTime ? `${e.startTime}${e.endTime ? " às " + e.endTime : ""}` : "";

    return `
      <article class="flex flex-col rounded-2xl bg-white p-5 shadow-[0_4px_20px_rgba(0,0,0,0.05)]">
        <div class="flex gap-4">
          <div class="flex h-16 w-16 shrink-0 flex-col items-center justify-center rounded-xl bg-[#472056] text-white">
            <span class="text-2xl font-bold leading-none">${dia}</span>
            <span class="text-xs font-semibold uppercase">${esc(mes)}</span>
          </div>
          <div class="min-w-0">
            <h3 class="font-bold text-[#472056] leading-snug">${esc(e.title)}</h3>
            <p class="mt-1 text-sm capitalize text-[#4c444d]">${esc(diaSemana)}${horario ? " • " + esc(horario) : ""}</p>
          </div>
        </div>

        ${e.location ? `
          <p class="mt-4 flex items-start gap-1.5 text-sm text-[#4c444d]">
            <span class="material-symbols-outlined text-[18px] text-[#78517a]">location_on</span>
            <span>${esc(e.location)}</span>
          </p>` : ""}

        ${e.description ? `<p class="mt-2 line-clamp-3 text-sm text-[#4c444d]">${esc(e.description)}</p>` : ""}

        <div class="mt-auto flex flex-col gap-2 pt-5 sm:flex-row">
          ${e.location ? `
            <a href="${linkMapa(e.location)}" target="_blank" rel="noopener"
               class="flex flex-1 items-center justify-center gap-1.5 rounded-full bg-[#472056] px-4 py-2.5 text-sm font-semibold text-white hover:bg-[#5f376e]">
              <span class="material-symbols-outlined text-[18px]">directions</span>Como chegar
            </a>` : ""}
          <a href="${linkAgenda(e)}" target="_blank" rel="noopener"
             class="flex flex-1 items-center justify-center gap-1.5 rounded-full border-2 border-[#472056] px-4 py-2 text-sm font-semibold text-[#472056] hover:bg-[#f8f1f9]">
            <span class="material-symbols-outlined text-[18px]">event</span>Salvar na agenda
          </a>
        </div>
      </article>`;
  }

  window.mostrarEventos = async function ({ lista, secao, vazio, limite } = {}) {
    const elLista = document.getElementById(lista);
    const elSecao = secao && document.getElementById(secao);
    const elVazio = vazio && document.getElementById(vazio);
    if (!elLista) return;

    try {
      const resposta = await fetch("/api/events");
      if (!resposta.ok) throw new Error("Erro " + resposta.status);
      const todos = await resposta.json();

      // Só eventos publicados, de hoje em diante, do mais próximo ao mais distante
      let proximos = (Array.isArray(todos) ? todos : [])
        .filter((e) => e.date && e.date >= hoje() && (e.status || "published") === "published")
        .sort((a, b) => `${a.date}${a.startTime}`.localeCompare(`${b.date}${b.startTime}`));

      if (limite) proximos = proximos.slice(0, limite);

      if (!proximos.length) {
        if (elSecao) elSecao.classList.add("hidden");
        if (elVazio) elVazio.classList.remove("hidden");
        elLista.innerHTML = "";
        return;
      }

      elLista.innerHTML = proximos.map(card).join("");
      if (elSecao) elSecao.classList.remove("hidden");
      if (elVazio) elVazio.classList.add("hidden");
    } catch (erro) {
      console.error("Erro ao carregar eventos:", erro);
      if (elSecao) elSecao.classList.add("hidden");
      if (elVazio) elVazio.classList.remove("hidden");
    }
  };
})();