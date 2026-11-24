"use strict";

(() => {
  const formulario = porId("filtros-ocorrencias");
  const campos = formulario.elements;
  const analise = new PainelAnaliseOperacional(porId("analise-operacional"));
  const mensagem = porId("estado-ocorrencias");
  const variavel = porId("variavel-ocorrencia");
  const lista = porId("lista-ocorrencias");
  let dados;
  let versao = 0;

  function contextoAtual() {
    return Object.fromEntries(parametrosRecorte(Object.fromEntries(new FormData(formulario))));
  }

  function grafico() {
    if (!dados) return;
    const medicao = variavel.value;
    const campo = medicao === "temperatura_processo" ? "temperatura_c" : medicao;
    const unidade = medicao === "temperatura_processo" ? "°C" : rotulosMedicao[medicao][1];
    const pontos = dados.serie.map((r) => ({x: r.ciclo, y: r[campo]}));
    porId("grafico-ocorrencia-vazio").hidden = Boolean(pontos.length);
    const series = [{nome: dados.selecao.origem, valores: pontos}];
    if (dados.detecao) {
      series.push({nome: dados.ocorrencia.revisado ? "Detecção · leitura corrigida" : "Detecção", cor: "#f07577", raio: 6, ordem: -1, valores: [
        {x: dados.detecao.ciclo, y: dados.detecao[campo]}
      ]});
    }
    desenhar("grafico-ocorrencia", "line", series, {
      linear: true, inteirosX: true, eixoX: "Ciclo · até 300 leituras recentes", eixoY: unidade,
      legenda: Boolean(dados.detecao)
    });
  }

  function apresentar() {
    const {selecao, ocorrencia, ocorrencias, detecao, resumo, registros, maquina, quantidade} = dados;
    campos.origem.value = selecao.origem;
    campos.ocorrencia.replaceChildren(
      new Option("Intervalo sem ocorrência", ""),
      ...ocorrencias.map((o) => new Option(`${o.tipo} · ciclo ${o.ciclo} · ${o.id}`, o.id))
    );
    campos.ocorrencia.value = ocorrencia?.id || "";
    campos.inicio.value = selecao.inicio ?? "";
    campos.fim.value = selecao.fim ?? "";
    mensagem.textContent = ocorrencias.length
      ? `${numero(ocorrencias.length, 0)} ocorrências registradas · ${numero(quantidade, 0)} medições no recorte.`
      : "Esta máquina ainda não tem alertas ou falhas registrados. Se houver ciclos normais, eles podem ser analisados.";
    tabela(lista, ["Ocorrência", "Equipamento", "Tipo", "Ciclo", "Estado", "Descrição", "Registro associado", "Ação"],
      ocorrencias.map((o) => [
        escapar(o.id), escapar(o.equipamento), escapar(o.tipo), numero(o.ciclo, 0), selo(o.estado),
        escapar(o.descricao), escapar(o.udi) + (o.disponivel ? "" : " · removido"),
        `<button class="botao" data-investigar="${escapar(o.id)}">Investigar ocorrência</button>`
      ]), "A lista é preenchida quando a simulação registra uma condição anormal.");
    if (ocorrencia) lista.querySelector(`[data-investigar="${CSS.escape(ocorrencia.id)}"]`)
      ?.closest("tr").setAttribute("aria-selected", "true");
    const med = resumo.medicoes;
    const temperatura = (valor) => valor == null ? "—" : numero(valor - 273.15) + " °C";
    const unidade = (valor, nome) => valor == null ? "—" : numero(valor) + " " + nome;
    const itens = [
      ["Registros", numero(quantidade, 0)], ["Alertas / falhas", `${resumo.alertas} / ${resumo.falhas}`],
      ["Temperatura mínima", temperatura(med.temperatura_processo?.minimo)],
      ["Temperatura média", temperatura(med.temperatura_processo?.media)],
      ["Temperatura máxima", temperatura(med.temperatura_processo?.maximo)],
      ["Torque médio", unidade(med.torque?.media, "Nm")], ["Torque máximo", unidade(med.torque?.maximo, "Nm")],
      ["RPM médio", unidade(med.rpm?.media, "rpm")], ["Maior desgaste observado", unidade(med.desgaste?.maximo, "min")]
    ];
    porId("resumo-ocorrencia").innerHTML = itens.map(([nome, valor]) =>
      `<div class="ficha-evidencia"><small>${nome}</small><strong>${valor}</strong></div>`).join("");
    const condicao = ocorrencia ? `${ocorrencia.descricao} · ciclo ${ocorrencia.ciclo} · ${ocorrencia.id}`
      : "Intervalo de operação selecionado";
    porId("observacao-ocorrencia").textContent = `${selecao.origem} · ${maquina} · ${condicao}`;
    const det = porId("detecao-ocorrencia");
    det.hidden = !ocorrencia;
    if (ocorrencia) {
      const motivos = ocorrencia.motivos.map((m) => m.valor == null ? m.nome :
        `${m.nome} ${numero(m.valor)} ${m.unidade} · referência ${numero(m.nivel === "falha" ? m.limite : m.alerta)} ${m.unidade}`);
      const titulo = !detecao ? "UDI associado à detecção"
        : ocorrencia.revisado ? "Medição associada · versão corrigida" : "Medição exata da detecção";
      det.innerHTML = `<h3>${titulo}</h3>${detecao ? resumoRegistro(detecao)
        : `<p>UDI ${escapar(ocorrencia.udi)} · ${ocorrencia.disponivel ? "fora do recorte selecionado"
          : "indisponível na coleção de trabalho"}</p>`}
        ${motivos.length ? `<p>Condição no evento arquivado · ${escapar(motivos.join(" / "))}</p>` : ""}`;
    }
    tabela(porId("registros-ocorrencia"), colunasEvidencia, registros.slice().reverse().map(celulasEvidencia));
    porId("registros-ocorrencia-info").textContent =
      `${numero(registros.length, 0)} de ${numero(quantidade, 0)} registros. O CSV exporta o recorte completo.`;
    const parametros = parametrosRecorte(selecao);
    if (ocorrencia) parametros.set("udi", ocorrencia.udi);
    const caminho = parametros.toString();
    for (const [id, rota] of [
      ["exportar-evidencias", "/api/ocorrencias/csv?"], ["abrir-registros", "/registros?"],
      ["abrir-laboratorio", "/laboratorio?modo=operacional&voltar=ocorrencias&"]
    ]) {
      const link = porId(id);
      link.href = rota + caminho;
      link.hidden = false;
    }
    analise.contexto(selecao, ocorrencia?.udi ?? dados.udi_minimo);
    history.replaceState(null, "", "/ocorrencias?" + caminho + location.hash);
    grafico();
  }

  async function carregar(selecao) {
    const pedido = ++versao;
    mensagem.textContent = "Carregando evidências…";
    formulario.setAttribute("aria-busy", "true");
    analise.contexto(null);
    try {
      const resposta = await requisicao("/api/ocorrencias?" + parametrosRecorte(selecao));
      if (pedido !== versao) return;
      dados = resposta;
      apresentar();
    } catch (erro) {
      if (pedido === versao) {
        mensagem.textContent = erro.message;
        for (const id of ["exportar-evidencias", "abrir-registros", "abrir-laboratorio"]) porId(id).hidden = true;
        avisar(erro.message, true);
      }
    } finally {
      if (pedido === versao) formulario.removeAttribute("aria-busy");
    }
  }

  formulario.addEventListener("submit", (evento) => {
    evento.preventDefault();
    carregar(contextoAtual());
  });
  campos.origem.addEventListener("change", () => carregar({origem: campos.origem.value}));
  campos.ocorrencia.addEventListener("change", () => carregar({
    origem: campos.origem.value, ocorrencia: campos.ocorrencia.value
  }));
  lista.addEventListener("click", (evento) => {
    const botao = evento.target.closest("[data-investigar]");
    if (botao) carregar({origem: campos.origem.value, ocorrencia: botao.dataset.investigar});
  });
  variavel.addEventListener("change", grafico);
  porId("cenario-demo").addEventListener("click", (evento) => ocupado(evento.currentTarget, async () => {
    const demo = await enviar("/api/ocorrencias/demonstracao", "POST");
    await carregar({origem: demo.equipamento, ocorrencia: demo.ocorrencia});
    avisar("Cenário controlado gravado no histórico da M-01.");
  }));
  carregar(Object.fromEntries(new URLSearchParams(location.search)));
})();
