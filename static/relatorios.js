"use strict";

async function iniciarRelatorios() {
  const dados = await requisicao("/api/relatorios");
  const fonte = porId("relatorio-fonte");
  const campo = porId("relatorio-campo");
  tabela(porId("resumo-maquinas"), ["Equipamento", "Estado", "Ciclos", "Alertas", "Falhas",
    "Temperatura média · K", "Torque médio · Nm", "Rotação média · rpm", "Desgaste médio · min"],
    dados.maquinas.map((m) => [
      escapar(m.codigo), selo(m.estado), numero(m.estatisticas.quantidade),
      numero(m.estatisticas.alertas), numero(m.estatisticas.falhas),
      ...["temperatura_processo", "torque", "rpm", "desgaste"].map((k) => numero(m.estatisticas.medicoes[k]?.media))
    ]));

  function distribuicao() {
    const resumo = dados[fonte.value];
    const medicao = resumo.medicoes[campo.value];
    porId("contagem-fonte").textContent = `${numero(resumo.quantidade)} registros ·
      ${numero(resumo.alertas)} alertas · ${numero(resumo.falhas)} falhas`;
    porId("histograma-vazio").hidden = Boolean(medicao);
    const classes = medicao?.histograma || [];
    desenhar("histograma", "bar", [{nome: "Registros", valores: classes.map((c) => c.quantidade)}], {
      etiquetas: classes.map((c) => c.inicio === c.fim ? numero(c.inicio) : `${numero(c.inicio)}–${numero(c.fim)}`),
      eixoX: rotulosMedicao[campo.value].join(" · "), eixoY: "Frequência", legenda: false, zero: true
    });
    estatisticasTabela(porId("descricao-fonte"), resumo);
  }

  const titulos = {ordenacao: "Ordenação", busca: "Busca", hash: "Tabela hash", sistema: "Carga de trabalho"};
  const painel = porId("relatorio-experimentos");
  for (const [aba, titulo] of Object.entries(titulos)) {
    const resumo = dados.resultados[aba];
    const cartao = document.createElement("section");
    cartao.className = "cartao painel-grafico";
    cartao.innerHTML = `<div class="titulo-bloco"><div><h2>${titulo}</h2><p class="interpretacao"></p></div></div>`;
    painel.append(cartao);
    const paragrafo = cartao.querySelector(".interpretacao");
    if (!resumo?.length) {
      paragrafo.textContent = "Aguardando medições do laboratório.";
      continue;
    }
    const maior = Math.max(...resumo.map((r) => r.tamanho));
    const perfil = {ordenacao: "Aleatória", busca: "Lacunas e concentração", sistema: "Dinâmica"}[aba];
    const linhas = resumo.filter((r) => r.tamanho === maior && (!perfil || r.distribuicao === perfil));
    const porTempo = linhas.slice().sort((a, b) => a.tempo_ns_mediana - b.tempo_ns_mediana);
    const melhor = porTempo[0];
    paragrafo.textContent = aba === "hash"
      ? `Com ${numero(maior)} registros, a menor mediana de preparo + consultas ocorreu na carga-alvo de ${numero(melhor.carga_alvo * 100)}% (${numero(melhor.tempo_ns_mediana / 1e6, 4)} ms).`
      : `Em ${melhor.distribuicao.toLowerCase()}, com ${numero(maior)} registros, ${nomesAlgoritmos[melhor.algoritmo]} teve a menor mediana total (${numero(melhor.tempo_ns_mediana / 1e6, 4)} ms).`;
    const grafico = document.createElement("div");
    grafico.className = "grafico";
    const tela = document.createElement("canvas");
    tela.id = "relatorio-" + aba;
    tela.setAttribute("role", "img");
    tela.setAttribute("aria-label", "Tempos comparados para " + titulo);
    grafico.append(tela);
    const quadro = document.createElement("div");
    quadro.className = "tabela-rolavel";
    cartao.append(grafico, quadro);
    const rotulo = (r) => aba === "hash" ? numero(r.carga_alvo * 100) + "%" : nomesAlgoritmos[r.algoritmo];
    desenhar(tela.id, "bar", [{
      nome: "Mediana", valores: linhas.map((r) => r.tempo_ns_mediana / 1e6)
    }], {etiquetas: linhas.map(rotulo), eixoY: "Tempo total · ms", legenda: false, zero: true});
    tabela(quadro, [aba === "hash" ? "Carga-alvo" : "Algoritmo", "Mediana · ms", "IIQ · ms", "Pico · KiB"],
      linhas.map((r) => [rotulo(r), numero(r.tempo_ns_mediana / 1e6, 4),
        numero(r.tempo_ns_iiq / 1e6, 4), numero(r.pico_bytes_mediana / 1024)]));
  }

  fonte.addEventListener("change", distribuicao);
  campo.addEventListener("change", distribuicao);
  distribuicao();
}

async function iniciarDados() {
  const formulario = porId("configuracoes");
  formulario.addEventListener("submit", (evento) => {
    evento.preventDefault();
    ocupado(evento.submitter, async () => {
      const {semente, repeticoes, ...limites} = Object.fromEntries(new FormData(formulario));
      await enviar("/api/configuracoes", "PATCH", {semente, repeticoes, limites});
      avisar("Configurações salvas.");
    });
  });
  const dados = await requisicao("/api/dados");
  function preencher(id, itens) {
    porId(id).innerHTML = itens.map(([nome, valor]) =>
      `<div><dt>${escapar(nome)}</dt><dd>${escapar(valor)}</dd></div>`).join("");
  }
  preencher("info-dados", [
    ["Arquivo original", dados.original], ["Registros sintéticos", numero(dados.quantidade)],
    ["Tipos de produto", Object.entries(dados.tipos).map(([k, v]) => k + " " + numero(v)).join(" · ")],
    ["Unidade das temperaturas", "Kelvin (K)"], ["SHA-256", dados.sha256]
  ]);
  preencher("info-ambiente", [
    ["Python", dados.python], ["Sistema", dados.ambiente],
    ["Cópia de trabalho", `${numero(dados.trabalho)} registros · registros.csv`],
    ["Histórico simulado", `${numero(dados.simulacoes)} ciclos · simulacoes.csv`],
    ["Resultados experimentais", `${numero(dados.resultados)} de 4 abas com medições`]
  ]);
}

(document.body.dataset.pagina === "relatorios" ? iniciarRelatorios() : iniciarDados())
  .catch((erro) => avisar(erro.message, true));

