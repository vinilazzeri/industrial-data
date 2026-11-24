"use strict";

(() => {
  const filtros = porId("filtros-registros");
  const destino = porId("tabela-registros");
  const modal = porId("registro-modal");
  const formulario = porId("form-registro");
  const consulta = porId("consulta-registro");
  const resultadoConsulta = porId("resultado-consulta");
  const colunas = ["UDI", "Produto", "Tipo", "Equipamento", "Fonte", "Processo · K", "Torque · Nm",
    "Rotação · rpm", "Desgaste · min", "Status", "Ações"];
  let pagina = 1;
  let registros = [];
  let udiAtivo = null;
  let pedido = 0;
  const argumentos = new URLSearchParams(location.search);
  const contexto = new URLSearchParams();
  if (argumentos.get("origem")) {
    for (const nome of ["origem", "ocorrencia", "inicio", "fim"]) {
      if (argumentos.has(nome)) contexto.set(nome, argumentos.get(nome));
    }
    porId("registros-contexto").textContent = "Registros consultáveis da investigação · "
      + contexto.get("origem") + (contexto.get("ocorrencia") ? " · " + contexto.get("ocorrencia") : "");
    const voltar = porId("voltar-ocorrencia-registros");
    voltar.href = "/ocorrencias?" + contexto;
    voltar.hidden = false;
  }
  if (argumentos.has("udi")) consulta.elements.udi.value = argumentos.get("udi");
  const camposFiltro = ["equipamento", "fonte", "status"];
  for (const campo of camposFiltro) {
    const valor = argumentos.get(campo);
    if (valor && Array.from(filtros.elements[campo].options).some((o) => o.value === valor)) {
      filtros.elements[campo].value = valor;
    }
  }

  const caminhoRegistro = (udi) => "/api/registros/" + encodeURIComponent(udi);
  const atributos = (form) => Object.fromEntries(new FormData(form));
  const erroFormulario = (form) => (erro) => { form.querySelector(".erro-form").textContent = erro.message; };
  const limparErro = (form) => { form.querySelector(".erro-form").textContent = ""; };

  function atualizarComparacoes() {
    const recorte = new URLSearchParams(contexto);
    if (!recorte.has("origem")) {
      recorte.set("origem", "trabalho");
    } else recorte.set("voltar", "ocorrencias");
    for (const campo of camposFiltro) {
      const valor = filtros.elements[campo].value;
      if (valor) recorte.set(campo, valor);
    }
    if (consulta.elements.udi.value) recorte.set("udi", consulta.elements.udi.value);
    for (const [id, aba] of [["comparar-buscas", "busca"], ["comparar-ordenacoes", "ordenacao"]]) {
      porId(id).href = "/laboratorio?modo=operacional&aba=" + aba + "&" + recorte;
    }
  }

  function atualizarManutencao() {
    requisicao("/api/registros/manutencao").then((dados) => {
      if (!dados) return;
      const painel = porId("manutencao-registros");
      const invalidos = dados.invalidos.map((chave) => nomesAlgoritmos[chave]).join(", ");
      painel.textContent = `${dados.operacao} · persistência ${numero(dados.persistencia_ns, 0)} ns ·
        sincronização ${numero(dados.sincronizacao_ns, 0)} ns. ${invalidos
          ? "Índices invalidados: " + invalidos + ". A próxima consulta mede o preparo."
          : dados.alterado ? "Nenhum índice global estava carregado." : "Sem alteração no conteúdo."}`;
      painel.hidden = false;
    }).catch(() => {});
  }

  async function carregar() {
    const versao = ++pedido;
    const parametros = new URLSearchParams(contexto);
    new FormData(filtros).forEach((valor, nome) => parametros.set(nome, valor));
    atualizarComparacoes();
    porId("exportar-registros").href = "/api/registros/csv?" + parametros;
    parametros.set("pagina", pagina);
    destino.setAttribute("aria-busy", "true");
    try {
      const resposta = await requisicao("/api/registros?" + parametros);
      if (versao !== pedido) return;
      const totalPaginas = Math.max(1, Math.ceil(resposta.total / resposta.limite));
      if (pagina > totalPaginas) {
        pagina = totalPaginas;
        return carregar();
      }
      registros = resposta.registros;
      tabela(destino, colunas, registros.map((r, i) => [
        `<span class="monoespaco">${escapar(r.identificador)}</span>`, escapar(r.produto || "—"),
        escapar(r.tipo), escapar(r.equipamento || "—"), escapar(r.fonte), numero(r.temperatura_processo),
        numero(r.torque), numero(r.rpm), numero(r.desgaste), selo(r.status),
        `<button class="botao" data-editar="${i}">Editar</button><button class="botao perigo" data-remover="${i}">Remover</button>`
      ]));
      porId("total-registros").textContent = `${numero(resposta.total)} registros nos filtros atuais`;
      porId("pagina-registros").textContent = `Página ${numero(pagina)} de ${numero(totalPaginas)}`;
      porId("anterior").disabled = pagina === 1;
      porId("proxima").disabled = pagina >= totalPaginas;
    } finally {
      if (versao === pedido) destino.removeAttribute("aria-busy");
    }
  }

  function atualizar() {
    carregar().catch((erro) => avisar(erro.message, true));
  }

  function abrirRegistro(registro) {
    udiAtivo = registro?.identificador ?? null;
    formulario.reset();
    limparErro(formulario);
    porId("titulo-registro").textContent = registro ? "Editar registro" : "Novo registro";
    formulario.elements.identificador.readOnly = Boolean(registro);
    formulario.elements.equipamento.disabled = registro?.fonte === "Simulação";
    if (registro) {
      for (const campo of formulario.elements) {
        if (!Object.hasOwn(registro, campo.name)) continue;
        if (campo.type === "checkbox") campo.checked = Boolean(registro[campo.name]);
        else campo.value = registro[campo.name];
      }
    }
    modal.showModal();
  }

  formulario.addEventListener("submit", (evento) => {
    evento.preventDefault();
    limparErro(formulario);
    ocupado(evento.submitter, async () => {
      const valores = atributos(formulario);
      for (const campo of formulario.querySelectorAll('[type="checkbox"]')) valores[campo.name] = Number(campo.checked);
      if (udiAtivo !== null) delete valores.identificador;
      await enviar(udiAtivo === null ? "/api/registros" : caminhoRegistro(udiAtivo),
        udiAtivo === null ? "POST" : "PATCH", valores);
      modal.close();
      resultadoConsulta.hidden = true;
      await carregar();
      atualizarManutencao();
      avisar("Registro salvo.");
    }, erroFormulario(formulario));
  });

  const formRemover = porId("form-remover");
  destino.addEventListener("click", (evento) => {
    const botao = evento.target.closest("button");
    if (!botao) return;
    if (botao.dataset.editar !== undefined) abrirRegistro(registros[botao.dataset.editar]);
    if (botao.dataset.remover !== undefined) {
      udiAtivo = registros[botao.dataset.remover].identificador;
      limparErro(formRemover);
      porId("remover-descricao").textContent = `Remover o UDI ${udiAtivo} da coleção de trabalho?`;
      porId("remover-modal").showModal();
    }
  });
  formRemover.addEventListener("submit", (evento) => {
    evento.preventDefault();
    limparErro(formRemover);
    ocupado(evento.submitter, async () => {
      await requisicao(caminhoRegistro(udiAtivo), {method: "DELETE"});
      porId("remover-modal").close();
      resultadoConsulta.hidden = true;
      await carregar();
      atualizarManutencao();
      avisar("Registro removido.");
    }, erroFormulario(formRemover));
  });

  consulta.addEventListener("submit", (evento) => {
    evento.preventDefault();
    ocupado(evento.submitter, async () => {
      const parametros = new URLSearchParams(contexto);
      if (contexto.has("origem")) {
        for (const campo of camposFiltro) {
          const valor = filtros.elements[campo].value;
          if (valor) parametros.set(campo, valor);
        }
      }
      new FormData(consulta).forEach((valor, nome) => parametros.set(nome, valor));
      const busca = await requisicao("/api/registros/consulta?" + parametros);
      const r = busca.registro;
      resultadoConsulta.innerHTML = r
        ? `<strong>UDI ${escapar(r.identificador)} encontrado</strong> · ${escapar(r.produto || r.fonte)}
           · ${selo(r.status)} <p>${escapar(r.fonte)} · ${escapar(r.equipamento || "Sem equipamento")}
           · ${numero(r.temperatura_processo)} K · ${numero(r.torque)} Nm · ${numero(r.rpm)} rpm ·
           ${numero(r.desgaste)} min</p>`
        : "<strong>Identificador ausente na coleção.</strong>";
      resultadoConsulta.insertAdjacentHTML("beforeend",
        `<p>${nomesAlgoritmos[busca.estrategia]} · ${numero(busca.passos)} passos ·
         preparo ${numero(busca.preparo_ns)} ns${busca.indice_reutilizado ? " (índice reutilizado)" : ""}
         · consulta ${numero(busca.consulta_ns)} ns</p>`);
      resultadoConsulta.hidden = false;
    });
  });

  const formImportar = porId("form-importar");
  porId("botao-importar").addEventListener("click", () => {
    formImportar.reset();
    limparErro(formImportar);
    porId("importar-modal").showModal();
  });
  formImportar.addEventListener("submit", (evento) => {
    evento.preventDefault();
    limparErro(formImportar);
    ocupado(evento.submitter, async () => {
      const resposta = await requisicao("/api/registros/importar", {method: "POST", body: new FormData(formImportar)});
      porId("importar-modal").close();
      resultadoConsulta.hidden = true;
      await carregar();
      atualizarManutencao();
      avisar(`${numero(resposta.importados)} registros importados.`);
    }, erroFormulario(formImportar));
  });
  porId("novo-registro").addEventListener("click", () => abrirRegistro(null));
  filtros.addEventListener("change", () => { pagina = 1; atualizar(); });
  consulta.elements.udi.addEventListener("input", atualizarComparacoes);
  filtros.addEventListener("submit", (evento) => evento.preventDefault());
  porId("anterior").addEventListener("click", () => { pagina--; atualizar(); });
  porId("proxima").addEventListener("click", () => { pagina++; atualizar(); });
  atualizar();
})();

