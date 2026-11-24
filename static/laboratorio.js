"use strict";

(() => {
  const descricoes = {
    ordenacao: ["Crescimento das ordenações", "Qual estratégia organiza melhor os registros? Insertion Sort, Merge Sort, Heap Sort e a referência Python sorted recebem as mesmas entradas."],
    busca: ["Custo das buscas", "Quando o preparo compensa? Sequencial, binária, interpolação e hash consultam os mesmos UDIs regulares ou concentrados, metade presentes."],
    hash: ["Efeito do fator de carga", "Como colisões afetam consultas repetidas? A tabela própria recebe as mesmas chaves com cargas-alvo de 25%, 50% e 75%."],
    sistema: ["Custo total do sistema", "Qual estratégia tem menor custo total quando os registros são consultados, inseridos, corrigidos e removidos?"]
  };
  const botoes = Array.from(document.querySelectorAll("[data-aba]"));
  const formulario = porId("experimento");
  const recorte = porId("recorte-lab");
  const fonte = porId("fonte-laboratorio");
  const painelOperacional = new PainelAnaliseOperacional(porId("analise-operacional"));
  const argumentos = Object.fromEntries(new URLSearchParams(location.search));
  const contextoRetorno = Object.fromEntries(Object.entries(argumentos)
    .filter(([nome]) => nome.startsWith("retorno_"))
    .map(([nome, valor]) => [nome.slice("retorno_".length), valor]));
  const querVoltar = argumentos.ocorrencia || argumentos.voltar === "ocorrencias";
  const destinoRetorno = contextoRetorno.origem ? contextoRetorno : argumentos;
  const retorno = querVoltar && ["M-01", "M-02", "M-03"].includes(destinoRetorno.origem)
    ? parametrosRecorte(destinoRetorno) : null;
  let modo = argumentos.modo === "operacional" ? "operacional" : "academico";
  let selecao = Object.fromEntries(parametrosRecorte(argumentos));
  let origemDisponivel;
  let pedidoOrigem = 0;
  let executando = false;
  let aba = Object.hasOwn(descricoes, argumentos.aba) ? argumentos.aba : "ordenacao";
  let resultado;
  let carregamento = 0;
  let trabalhoAcompanhado;
  let temporizador;

  const consultarMetadados = () => requisicao("/api/investigacao/origem?" + parametrosRecorte(selecao));

  function atualizarUrl() {
    const params = parametrosRecorte(selecao);
    params.set("modo", modo);
    params.set("aba", aba);
    if (retorno) {
      params.set("voltar", "ocorrencias");
      for (const [nome, valor] of retorno) params.set("retorno_" + nome, valor);
    }
    if (argumentos.udi && selecao.origem === argumentos.origem) params.set("udi", argumentos.udi);
    history.replaceState(null, "", "/laboratorio?" + params);
  }

  async function mudarOrigem(nova) {
    const versao = ++pedidoOrigem;
    ++carregamento;
    resultado = null;
    origemDisponivel = null;
    selecao = nova;
    fonte.elements.origem.value = nova.origem;
    const temCiclos = !["ai4i", "controlado"].includes(nova.origem);
    fonte.querySelectorAll("[data-ciclo-lab]").forEach((elemento) => { elemento.hidden = !temCiclos; });
    fonte.elements.inicio.value = nova.inicio ?? "";
    fonte.elements.fim.value = nova.fim ?? "";
    painelOperacional.contexto(null);
    formulario.querySelector("button").disabled = true;
    for (const id of ["lab-visual", "exportacoes-lab", "bloco-compensacao"]) porId(id).hidden = true;
    porId("contexto-lab").textContent = "Carregando origem…";
    try {
      const origem = await consultarMetadados();
      if (versao !== pedidoOrigem) return;
      origemDisponivel = origem;
      selecao = origem.selecao;
      const intervalo = temCiclos ? ` · Ciclos ${selecao.inicio ?? origem.ciclo_minimo ?? "—"}
        a ${selecao.fim ?? origem.ciclo_maximo ?? "—"}` : "";
      porId("contexto-lab").textContent = `${origem.origem_nome} · ${origem.natureza} ·
        ${numero(origem.quantidade, 0)} registros · UDIs: ${origem.distribuicao_udi.toLowerCase()}${intervalo}
        ${selecao.ocorrencia ? " · " + selecao.ocorrencia : ""}
        ${[selecao.equipamento, selecao.fonte, selecao.status].filter(Boolean).join(" · ") || ""}`;
      fonte.elements.inicio.value = selecao.inicio ?? "";
      fonte.elements.fim.value = selecao.fim ?? "";
      painelOperacional.contexto(selecao, selecao.origem === argumentos.origem && argumentos.udi
        ? argumentos.udi : origem.udi_minimo ?? "0");
      formulario.querySelector("button").disabled = executando;
      atualizarUrl();
      if (modo === "academico") await carregar();
    } catch (erro) {
      if (versao === pedidoOrigem) porId("contexto-lab").textContent = erro.message;
    }
  }

  function mudarModo(novo) {
    modo = novo;
    document.querySelectorAll("[data-modo]").forEach((botao) => {
      botao.setAttribute("aria-pressed", String(botao.dataset.modo === modo));
    });
    const operacional = modo === "operacional";
    porId("area-academica").hidden = operacional;
    porId("area-operacional").hidden = !operacional;
    fonte.elements.origem.querySelector('option[value="controlado"]').disabled = operacional;
    porId("modo-lab-nota").textContent = operacional
      ? "Usa os valores e UDIs do recorte. Tempos pontuais variam entre execuções."
      : "Deriva amostras e distribuições controladas da origem indicada. Para o protocolo completo, use o conjunto controlado com 500, 2.000 e 8.000 registros.";
    if (!selecao.origem || (operacional && selecao.origem === "controlado")) {
      selecao = {origem: operacional ? "trabalho" : "controlado"};
    }
    mudarAba(aba, false);
    mudarOrigem(selecao);
  }

  function configurarRecorte() {
    const anterior = recorte.value;
    const valores = [...new Set(resultado.resumo.map((r) =>
      aba === "hash" ? String(r.tamanho) : r.distribuicao))];
    recorte.replaceChildren(...valores.map((v) => new Option(aba === "hash" ? numero(v) : v, v)));
    if (valores.includes(anterior)) recorte.value = anterior;
    porId("rotulo-recorte").firstChild.textContent = aba === "hash" ? "Tamanho" : "Distribuição";
  }

  function resultadosDaAba() {
    if (!resultado) return;
    const nas = (r, campo = "tempo_ns_mediana") => numero(r[campo] == null ? null : r[campo] / 1e6, 4);
    const linhas = resultado.resumo.filter((r) =>
      aba === "hash" ? String(r.tamanho) === recorte.value : r.distribuicao === recorte.value);
    const porMetodo = [...new Set(linhas.map((r) => r.algoritmo))];
    const series = porMetodo.map((metodo) => ({
      nome: nomesAlgoritmos[metodo],
      valores: linhas.filter((r) => r.algoritmo === metodo).map((r) => ({
        x: r.tamanho, y: (aba === "busca" ? r.consulta_ns_mediana : r.tempo_ns_mediana) / 1e6
      })).sort((a, b) => a.x - b.x)
    }));
    if (aba === "hash") {
      const indicadores = [["Presentes", "passos_presente_mediana"], ["Ausentes", "passos_ausente_mediana"]];
      desenhar("grafico-lab", "line", indicadores.map(([nome, campo]) => ({
        nome, valores: linhas.map((r) => ({x: r.fator_carga_mediana, y: r[campo]}))
      })), {linear: true, proporcao: true, eixoX: "Fator de carga real", eixoY: "Passos médios", zero: true});
    } else {
      desenhar("grafico-lab", "line", series, {
        linear: true, eixoX: "Registros", eixoY: aba === "busca" ? "Lote de consultas · ms" : "Tempo · ms",
        log: aba === "ordenacao" || aba === "busca", zero: aba === "sistema"
      });
    }
    const cabecalho = ["Estratégia", "n", "Tempo total · ms", "IIQ · ms", "Memória · KiB"];
    const campos = {
      ordenacao: ["Comparações", "Movimentações", "Posições auxiliares"],
      busca: ["Preparo · ms", "Consultas · ms", "Passos presente", "Passos ausente"],
      hash: ["Alvo", "Carga real", "Capacidade", "Colisões", "Maior balde", "Média baldes ocupados", "Passos presente", "Passos ausente"],
      sistema: ["Preparo · ms", "Consultas · ms", "Atualizações · ms", "Reconstrução isolada · ms", "Mutações"]
    };
    tabela(porId("tabela-lab"), [...cabecalho, ...campos[aba]], linhas.map((r) => {
      let extras;
      if (aba === "ordenacao") {
        extras = [r.comparacoes_mediana, r.movimentacoes_mediana, r.espaco_auxiliar_posicoes_mediana]
          .map((valor) => numero(valor));
      } else if (aba === "hash") {
        extras = [numero(r.carga_alvo * 100) + "%", numero(r.fator_carga_mediana * 100, 3) + "%",
          ...["capacidade", "colisoes", "balde_maximo", "media_balde_ocupado", "passos_presente", "passos_ausente"]
            .map((campo) => numero(r[campo + "_mediana"], 3))];
      } else {
        extras = [nas(r, "preparo_ns_mediana"), nas(r, "consulta_ns_mediana"), ...(aba === "sistema"
          ? [nas(r, "atualizacao_ns_mediana"), nas(r, "reconstrucao_ns_mediana"), numero(r.mutacoes_executadas_mediana)]
          : [numero(r.passos_presente_mediana, 3), numero(r.passos_ausente_mediana, 3)])];
      }
      return [nomesAlgoritmos[r.algoritmo], numero(r.tamanho), nas(r), nas(r, "tempo_ns_iiq"),
        numero(r.pico_bytes_mediana / 1024), ...extras];
    }));
    const tamanho = Math.max(...linhas.map((r) => r.tamanho));
    const comparaveis = linhas.filter((r) => r.tamanho === tamanho);
    if (comparaveis.length) {
      const menor = comparaveis.reduce((a, b) => a.tempo_ns_mediana <= b.tempo_ns_mediana ? a : b);
      const nome = aba === "hash" ? `carga-alvo ${numero(menor.carga_alvo * 100)}%` : nomesAlgoritmos[menor.algoritmo];
      const detalhe = aba === "busca" ? "O tempo total inclui preparo e consultas. Consulte a compensação para os lotes testados."
        : aba === "sistema" ? "O total inclui manutenção incremental. " +
          (resultado.resumo.some((r) => r.reconstrucao_ns_mediana != null)
            ? "A reconstrução é medida à parte no cenário dinâmico."
            : "A reconstrução é incluída em novas execuções, em uma coluna separada.")
        : aba === "hash" ? "Os passos variam com o tamanho dos baldes, o perfil de UDIs e a capacidade escolhida."
        : "A comparação vale para a distribuição selecionada e inclui as cópias internas.";
      porId("interpretacao-lab").textContent = `Com ${numero(tamanho, 0)} registros, o menor tempo total
        mediano no recorte foi de ${nas(menor)} ms (${nome}). ${detalhe} Medições excluem leitura de arquivos e renderização.`;
    }
  }

  async function carregar() {
    const versao = ++carregamento;
    const argumentosMedicao = parametrosRecorte(selecao);
    const medicao = await requisicao("/api/experimentos/" + aba + "?" + argumentosMedicao);
    if (versao !== carregamento) return;
    resultado = medicao;
    porId("lab-visual").hidden = !medicao;
    porId("exportacoes-lab").hidden = !medicao;
    porId("bloco-compensacao").hidden = !medicao?.compensacao.length;
    porId("resultado-lab-info").textContent = medicao
      ? `${medicao.configuracao.repeticoes} repetições · Semente ${medicao.configuracao.semente} ·
         Mediana e intervalo interquartil · ${medicao.origem?.origem_entrada || "Referência controlada derivada da AI4I"}
         ${medicao.origem ? " · entrada congelada: " + numero(medicao.origem.registros_disponiveis, 0) +
           " registros · SHA-256 " + medicao.origem.conteudo_sha256.slice(0, 12) : ""}
         ${medicao.recorte_alterado ? " · A seleção atual mudou desde a medição. Estes resultados são do recorte congelado." : ""}`
      : "Execute um experimento para visualizar as medições.";
    if (!medicao) return;
    const exportacao = (tipo) => {
      argumentosMedicao.set("tipo", tipo);
      return "/api/experimentos/" + aba + "/csv?" + argumentosMedicao;
    };
    porId("exportar-brutos").href = exportacao("brutos");
    porId("exportar-resumo").href = exportacao("resumo");
    porId("exportar-compensacao").href = exportacao("compensacao");
    configurarRecorte();
    resultadosDaAba();
    if (medicao.compensacao.length) {
      tabela(porId("tabela-compensacao"), ["n", "Distribuição", "Estratégia", "Estimativa pelo modelo", "Primeiro lote observado"],
        medicao.compensacao.map((r) => [numero(r.tamanho), escapar(r.distribuicao), nomesAlgoritmos[r.algoritmo],
          r.estimativa_modelo == null ? "Sem ganho unitário" : numero(r.estimativa_modelo),
          r.consultas_compensacao == null ? `Sem compensação até ${numero(r.consultas_limite)}` : numero(r.consultas_compensacao)]));
    }
  }

  function mudarAba(nova, buscar = true) {
    aba = nova;
    ++carregamento;
    resultado = null;
    painelOperacional.abrir(nova);
    botoes.forEach((botao) => botao.setAttribute("aria-pressed", String(botao.dataset.aba === aba)));
    porId("lab-descricao").textContent = descricoes[aba][1];
    porId("titulo-grafico-lab").textContent = descricoes[aba][0];
    document.querySelectorAll("[data-campo]").forEach((rotulo) => {
      const campo = rotulo.dataset.campo;
      const visivel = campo === "atributo" ? aba === "ordenacao" :
        campo === "operacoes" ? aba === "sistema" : aba !== "ordenacao";
      rotulo.hidden = !visivel;
      rotulo.querySelector("input,select").disabled = !visivel;
    });
    porId("lab-visual").hidden = true;
    porId("exportacoes-lab").hidden = true;
    porId("bloco-compensacao").hidden = true;
    porId("resultado-lab-info").textContent = "Carregando medições…";
    if (buscar && origemDisponivel) {
      atualizarUrl();
      if (modo === "academico") carregar().catch((erro) => avisar(erro.message, true));
    }
  }

  async function acompanhar() {
    const trabalho = await requisicao("/api/experimentos/estado");
    executando = trabalho?.estado === "Executando";
    const botao = formulario.querySelector("button");
    botao.disabled = executando || !origemDisponivel;
    porId("progresso-lab").hidden = !executando;
    if (executando) {
      trabalhoAcompanhado = trabalho.id;
      const barra = porId("progresso-barra");
      if (trabalho.total) {
        barra.max = trabalho.total;
        barra.value = trabalho.concluidos;
      } else barra.removeAttribute("value");
      porId("progresso-texto").textContent = `Executando ${descricoes[trabalho.aba][0].toLowerCase()}
        · ${trabalho.concluidos} de ${trabalho.total || "…"} configurações.`;
      temporizador = setTimeout(verificar, 700);
    } else if (trabalho && trabalho.id === trabalhoAcompanhado) {
      trabalhoAcompanhado = null;
      if (trabalho.estado === "Concluído") {
        avisar("Experimento concluído. As métricas estão disponíveis.");
        if (modo === "academico" && aba === trabalho.aba && origemDisponivel) await carregar();
      } else avisar(trabalho.mensagem, true);
    }
  }

  function verificar() {
    acompanhar().catch((erro) => {
      avisar(erro.message, true);
      if (trabalhoAcompanhado) temporizador = setTimeout(verificar, 1500);
    });
  }

  formulario.addEventListener("submit", async (evento) => {
    evento.preventDefault();
    const botao = evento.submitter;
    if (botao.disabled) return;
    botao.disabled = true;
    try {
      const valores = Object.fromEntries(new FormData(formulario));
      valores.tamanhos = valores.tamanhos.split(",").map((n) => n.trim());
      const trabalho = await enviar("/api/experimentos", "POST", {aba, selecao, ...valores});
      trabalhoAcompanhado = trabalho.id;
      clearTimeout(temporizador);
      await acompanhar();
    } catch (erro) {
      botao.disabled = false;
      avisar(erro.message, true);
    }
  });
  botoes.forEach((botao) => botao.addEventListener("click", () => mudarAba(botao.dataset.aba)));
  document.querySelectorAll("[data-modo]").forEach((botao) => {
    botao.addEventListener("click", () => mudarModo(botao.dataset.modo));
  });
  fonte.elements.origem.addEventListener("change", () => mudarOrigem({origem: fonte.elements.origem.value}));
  fonte.addEventListener("submit", (evento) => {
    evento.preventDefault();
    mudarOrigem({...selecao, inicio: fonte.elements.inicio.value, fim: fonte.elements.fim.value});
  });
  porId("exportar-grafico").addEventListener("click", () => {
    const grafico = Chart.getChart(porId("grafico-lab"));
    if (!grafico) return;
    const imagem = document.createElement("canvas");
    imagem.width = grafico.canvas.width;
    imagem.height = grafico.canvas.height;
    const desenho = imagem.getContext("2d");
    desenho.fillStyle = "#121b24";
    desenho.fillRect(0, 0, imagem.width, imagem.height);
    desenho.drawImage(grafico.canvas, 0, 0);
    const link = document.createElement("a");
    link.href = imagem.toDataURL("image/png");
    link.download = aba + ".png";
    link.click();
  });
  if (retorno) {
    const link = porId("voltar-investigacao");
    link.href = "/ocorrencias?" + retorno;
    link.hidden = false;
  }
  recorte.addEventListener("change", resultadosDaAba);
  mudarModo(modo);
  verificar();
})();

