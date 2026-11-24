"use strict";

(() => {
  const abas = Array.from(document.querySelectorAll("[data-maquina]"));
  const consulta = new URLSearchParams(location.search);
  const inicial = consulta.get("maquina");
  const filtros = porId("filtros-historico");
  const botaoEstatisticas = porId("gerar-estatisticas");
  let codigo = abas.some((aba) => aba.dataset.maquina === inicial) ? inicial : "M-01";
  let estatisticasAbertas = consulta.get("painel") === "estatisticas";
  let filtrosAplicados = new URLSearchParams({limite: filtros.elements.periodo.value});
  let historicoExibido = {historico: [], total_intervalo: 0, eventos: []};
  let assinaturaAnterior = "";
  let cicloEstatistica = null;
  let pedidoHistorico;
  let pedidoEstatisticas;

  function selecionar() {
    abas.forEach((aba) => {
      aba.setAttribute("aria-pressed", String(aba.dataset.maquina === codigo));
    });
    document.querySelectorAll("[data-unidade]").forEach((cartao) => {
      cartao.hidden = cartao.dataset.unidade !== codigo;
    });
    porId("exportar-maquina").href = urlMaquina(codigo) + "/csv";
  }

  function apresentarHistorico() {
    const {historico, eventos, total_intervalo: total} = historicoExibido;
    porId("contexto-historico").textContent = historico.length
      ? `${codigo} · Ciclos ${historico[0].ciclo} a ${historico.at(-1).ciclo} · ${numero(historico.length)} exibidos de ${numero(total)}`
      : `${codigo} · Nenhum ciclo no período selecionado.`;
    tendenciaOperacional("grafico-maquina", "maquina-grafico-vazio", [{
      codigo, historico
    }], porId("historico-campo").value);
    tabela(porId("historico-maquina"), [
      "Ciclo", "UDI", "Temperatura · °C", "Torque · Nm", "Rotação · rpm", "Desgaste · min", "Estado"
    ], historico.slice().reverse().map((r) => [
      numero(r.ciclo, 0), escapar(r.identificador), numero(r.temperatura_c),
      numero(r.torque), numero(r.rpm, 0), numero(r.desgaste, 0),
      selo(r.falha ? "Falha" : r.alerta ? "Alerta" : "Operando")
    ]), "O intervalo selecionado ainda não contém leituras.");
    apresentarEventos(porId("eventos-maquina"), eventos);
  }

  async function buscarHistorico() {
    pedidoHistorico?.abort();
    const pedido = new AbortController();
    pedidoHistorico = pedido;
    try {
      const dados = await requisicao(
        urlMaquina(codigo) + "/historico?" + filtrosAplicados, {signal: pedido.signal, cache: "no-store"}
      );
      if (pedido.signal.aborted) return;
      historicoExibido = dados;
      apresentarHistorico();
    } catch (erro) {
      if (!pedido.signal.aborted) {
        assinaturaAnterior = "";
        porId("contexto-historico").textContent = erro.message;
      }
    } finally {
      if (pedidoHistorico === pedido) pedidoHistorico = null;
    }
  }

  function apresentarEstatisticas(resumo) {
    const temp = resumo.medicoes.temperatura_processo;
    const leitura = (valor, unidade) => valor == null ? "—" : `${numero(valor)} ${unidade}`;
    const convertida = (chave) => temp ? temp[chave] - 273.15 : null;
    const indicadores = [
      ["Ciclos executados", numero(resumo.quantidade, 0)],
      ["Alertas", numero(resumo.alertas, 0)],
      ["Falhas", numero(resumo.falhas, 0)],
      ["Temperatura mínima", leitura(convertida("minimo"), "°C")],
      ["Temperatura média", leitura(convertida("media"), "°C")],
      ["Temperatura máxima", leitura(convertida("maximo"), "°C")],
      ["Rotação média", leitura(resumo.medicoes.rpm?.media, "rpm")],
      ["Torque médio", leitura(resumo.medicoes.torque?.media, "Nm")],
      ["Desgaste no último ciclo", leitura(resumo.desgaste_acumulado, "min")]
    ];
    porId("estatisticas-maquina").innerHTML = `<div class="mini-estatisticas">${indicadores.map(([nome, valor]) =>
      `<div><small>${nome}</small><strong>${valor}</strong></div>`
    ).join("")}</div>`;
  }

  async function buscarEstatisticas() {
    pedidoEstatisticas?.abort();
    const pedido = new AbortController();
    pedidoEstatisticas = pedido;
    botaoEstatisticas.setAttribute("aria-busy", "true");
    try {
      const resumo = await requisicao(urlMaquina(codigo) + "/estatisticas", {
        signal: pedido.signal, cache: "no-store"
      });
      if (!pedido.signal.aborted) apresentarEstatisticas(resumo);
    } catch (erro) {
      if (!pedido.signal.aborted) {
        cicloEstatistica = null;
        porId("estatisticas-maquina").textContent = erro.message;
      }
    } finally {
      if (pedidoEstatisticas === pedido) {
        pedidoEstatisticas = null;
        botaoEstatisticas.removeAttribute("aria-busy");
      }
    }
  }

  function atualizar(painel) {
    const maquina = painel.maquinas.find((m) => m.codigo === codigo);
    if (!maquina) return;
    botaoEstatisticas.disabled = false;
    const {id, versao} = maquina.execucao;
    const assinatura = [codigo, maquina.ciclo, id, versao, maquina.estado_atual].join("/");
    if (assinatura !== assinaturaAnterior) {
      assinaturaAnterior = assinatura;
      buscarHistorico();
    }
    if (estatisticasAbertas && cicloEstatistica !== maquina.ciclo) {
      cicloEstatistica = maquina.ciclo;
      buscarEstatisticas();
    }
  }

  abas.forEach((aba) => aba.addEventListener("click", () => {
    if (aba.dataset.maquina === codigo) return;
    codigo = aba.dataset.maquina;
    assinaturaAnterior = "";
    cicloEstatistica = null;
    historicoExibido = {historico: [], total_intervalo: 0, eventos: []};
    porId("estatisticas-maquina").textContent = estatisticasAbertas
      ? "Carregando estatísticas…" : "Gere as estatísticas para consolidar os ciclos registrados.";
    history.replaceState(null, "", "/maquinas?maquina=" + codigo);
    selecionar();
    apresentarHistorico();
    if (controleOperacional.painel) atualizar(controleOperacional.painel);
  }));
  botaoEstatisticas.addEventListener("click", () => {
    estatisticasAbertas = true;
    buscarEstatisticas();
  });
  porId("historico-campo").addEventListener("change", apresentarHistorico);

  function aplicarPeriodo() {
    const personalizado = filtros.elements.periodo.value === "intervalo";
    document.querySelectorAll("[data-intervalo]").forEach((elemento) => { elemento.hidden = !personalizado; });
    if (personalizado && !filtros.reportValidity()) return;
    const {inicio, fim} = filtros.elements;
    if (personalizado && inicio.value && fim.value && inicio.valueAsNumber > fim.valueAsNumber) {
      avisar("O ciclo final deve ser maior ou igual ao inicial.", true);
      return;
    }
    filtrosAplicados = new URLSearchParams({limite: personalizado ? "1000" : filtros.elements.periodo.value});
    if (personalizado) {
      if (inicio.value) filtrosAplicados.set("inicio", inicio.value);
      if (fim.value) filtrosAplicados.set("fim", fim.value);
    }
    buscarHistorico();
  }

  filtros.elements.periodo.addEventListener("change", aplicarPeriodo);
  filtros.addEventListener("submit", (evento) => {
    evento.preventDefault();
    aplicarPeriodo();
  });
  selecionar();
  controleOperacional.observar(atualizar);
  controleOperacional.iniciar();
})();
