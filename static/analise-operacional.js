"use strict";

function parametrosRecorte(selecao) {
  const nomes = ["origem", "ocorrencia", "inicio", "fim", "equipamento", "fonte", "status"];
  return new URLSearchParams(nomes.flatMap((nome) => {
    const valor = selecao[nome];
    return valor == null || valor === "" ? [] : [[nome, valor]];
  }));
}

function celulasEvidencia(r) {
  const temperatura = r.temperatura_c ?? r.temperatura_processo - 273.15;
  return [escapar(r.identificador), escapar(r.equipamento || "—"),
    r.ciclo ? numero(r.ciclo, 0) : "—", numero(temperatura),
    numero(r.torque), numero(r.rpm, 0), numero(r.desgaste, 0), selo(r.status)];
}
const colunasEvidencia = ["UDI", "Máquina", "Ciclo", "Temperatura · °C", "Torque · Nm",
  "Rotação · rpm", "Desgaste · min", "Estado"];

function resumoRegistro(r) {
  if (!r) return "Identificador ausente no recorte consultado.";
  const [udi, equipamento, ciclo, temperatura, torque, rpm, desgaste, estado] = celulasEvidencia(r);
  return `<strong>UDI ${udi}</strong> · ${equipamento} · Ciclo ${ciclo} · ${estado}
    <p>${temperatura} °C · ${torque} Nm · ${rpm} rpm · ${desgaste} min</p>`;
}

class PainelAnaliseOperacional {
  constructor(raiz) {
    this.raiz = raiz;
    this.formulario = raiz.querySelector("[data-form-analise]");
    this.botoes = Array.from(raiz.querySelectorAll("[data-acao-analise]"));
    this.botao = raiz.querySelector("[data-executar-analise]");
    this.versao = 0;
    this.botoes.forEach((botao) => botao.addEventListener("click", () => this.abrir(botao.dataset.acaoAnalise)));
    this.formulario.addEventListener("submit", (evento) => {
      evento.preventDefault();
      this.executar();
    });
    this.raiz.querySelector("[data-exportar-metricas]").addEventListener("click", () => this.exportar());
    this.abrir("ordenacao");
  }

  contexto(selecao, udi) {
    this.selecao = selecao;
    this.versao++;
    this.formulario.elements.udi.value = udi ?? "";
    this.botao.disabled = !selecao;
    this.limpar();
  }

  abrir(acao) {
    if (this.acao === acao) return;
    this.acao = acao;
    this.versao++;
    this.limpar();
    this.botao.disabled = !this.selecao;
    this.botoes.forEach((botao) => {
      botao.setAttribute("aria-pressed", String(botao.dataset.acaoAnalise === acao));
    });
    const definicoes = {
      ordenacao: ["Organize a mesma entrada pela medição e pelo UDI como desempate.", "Identificar extremos", ["atributo", "estrategia"]],
      busca: ["Recupere um registro pelo UDI. A busca binária e a interpolação preparam uma ordem própria por identificador.", "Consultar UDI", ["udi", "estrategia"]],
      "consulta-hash": ["Consulte o UDI por encadeamento. Consultas repetidas podem reaproveitar o índice do recorte.", "Consultar por hash", ["udi"]],
      hash: ["Meça consultas e mutações em uma cópia isolada da seleção. O histórico permanece disponível para consulta.", "Demonstrar tabela hash", ["udi", "capacidade"]],
      sistema: ["Compare consultas estáticas com inserção, correção e remoção em uma cópia do recorte.", "Comparar cargas", ["udi", "consultas"]]
    };
    const [descricao, rotulo, entradas] = definicoes[acao];
    this.raiz.querySelector("[data-acao-descricao]").textContent = descricao;
    this.botao.textContent = rotulo;
    this.raiz.querySelectorAll("[data-entrada]").forEach((campo) => {
      campo.hidden = !entradas.includes(campo.dataset.entrada);
      campo.querySelector("input,select").disabled = campo.hidden;
    });
    if (acao === "ordenacao" || acao === "busca") {
      const metodos = acao === "ordenacao"
        ? ["insercao", "intercalacao", "heap"] : ["sequencial", "binaria", "interpolacao", "hash"];
      this.formulario.elements.estrategia.replaceChildren(
        new Option("Comparar todas as estratégias", "todas"),
        ...metodos.map((metodo) => new Option(nomesAlgoritmos[metodo], metodo))
      );
    }
  }

  limpar() {
    this.resultado = null;
    this.raiz.querySelector("[data-resultado-analise]").textContent = "";
    for (const seletor of ["[data-extremos]", "[data-registro-analise]", "[data-metricas-analise]", "[data-exportar-metricas]"]) {
      this.raiz.querySelector(seletor).hidden = true;
    }
  }

  async executar() {
    if (!this.selecao || this.botao.disabled) return;
    const versao = ++this.versao;
    const valores = Object.fromEntries(new FormData(this.formulario));
    const acao = this.acao === "consulta-hash" ? "busca" : this.acao;
    if (this.acao === "consulta-hash") valores.estrategia = "hash";
    this.botao.disabled = true;
    this.raiz.querySelector("[data-resultado-analise]").textContent = "Medindo estratégias…";
    try {
      const resposta = await enviar("/api/investigacao/operacoes", "POST", {
        selecao: this.selecao, operacao: acao, ...valores
      });
      if (versao === this.versao) this.apresentar(resposta, acao);
    } catch (erro) {
      if (versao === this.versao) {
        this.limpar();
        this.raiz.querySelector("[data-resultado-analise]").textContent = erro.message;
      }
    } finally {
      if (versao === this.versao) this.botao.disabled = false;
    }
  }

  apresentar(r, acao) {
    this.resultado = r;
    const ns = (valor) => numero(valor, 0);
    const valido = (m) => m.valido ? "Equivalente" : "Divergência";
    const tabelaMetricas = this.raiz.querySelector("[data-metricas-analise]");
    const registro = this.raiz.querySelector("[data-registro-analise]");
    const estado = this.raiz.querySelector("[data-resultado-analise]");
    let interpretacao = "";
    if (acao === "ordenacao") {
      tabela(tabelaMetricas, ["Estratégia", "Tempo · ns", "Comparações", "Movimentações", "Memória auxiliar · posições", "Validação"],
        r.metricas.map((m) => [nomesAlgoritmos[m.estrategia], ns(m.tempo_ns), ns(m.comparacoes),
          ns(m.movimentacoes), ns(m.espaco_auxiliar_posicoes), valido(m)]));
      for (const extremo of ["maiores", "menores"]) {
        tabela(this.raiz.querySelector("[data-" + extremo + "]"), colunasEvidencia, r[extremo].map(celulasEvidencia));
      }
      this.raiz.querySelector("[data-extremos]").hidden = false;
      interpretacao = "A memória auxiliar indica posições contabilizadas nas estruturas em Python.";
    } else if (acao === "busca") {
      tabela(tabelaMetricas, ["Estratégia", "Passos", "Preparo · ns", "Consulta · ns", "Índice", "Validação"],
        r.metricas.map((m) => [nomesAlgoritmos[m.estrategia], ns(m.passos), ns(m.preparo_ns),
          ns(m.consulta_ns), m.indice_reutilizado ? "Reutilizado" : "Preparado", valido(m)]));
      registro.innerHTML = resumoRegistro(r.registro);
      if (r.diagnostico) registro.insertAdjacentHTML("beforeend", `<p>${this.diagnostico(r.diagnostico)}</p>`);
      registro.hidden = false;
      if (r.metricas.length > 1) interpretacao = "A comparação mede o primeiro acesso de cada estratégia.";
    } else if (acao === "hash") {
      tabela(tabelaMetricas, ["Etapa", "Atualização · ns", "Consulta · ns", "Passos", "Após a ação", "Validação"],
        r.metricas.map((m) => [m.etapa, ns(m.atualizacao_ns), ns(m.consulta_ns),
          ns(m.passos), m.encontrado ? "Encontrado" : "Ausente", valido(m)]));
      registro.innerHTML = resumoRegistro(r.registro) + `<p>${this.diagnostico(r.diagnostico)} ·
        preparo ${ns(r.consulta_original.preparo_ns)} ns · consulta ${ns(r.consulta_original.consulta_ns)} ns ·
        ${ns(r.consulta_original.passos)} passos</p><p><strong>UDI derivado ${escapar(r.udi_teste)}</strong> ·
        colisões antes das mutações: ${ns(r.diagnostico_inicial.colisoes)}</p>`;
      registro.hidden = false;
      interpretacao = "As mutações foram medidas na cópia do recorte.";
    } else {
      tabela(tabelaMetricas, ["Estratégia", "Carga", "Preparo · ns", "Consultas · ns", "Manutenção · ns", "Reconstrução isolada · ns", "Total · ns", "Validação"],
        r.metricas.map((m) => [nomesAlgoritmos[m.estrategia], m.cenario, ns(m.preparo_ns),
          ns(m.consulta_ns), ns(m.atualizacao_ns), ns(m.reconstrucao_ns), ns(m.tempo_ns), valido(m)]));
      const dinamicas = r.metricas.filter((m) => m.cenario === "Dinâmica");
      const menor = dinamicas.reduce((a, b) => a.tempo_ns <= b.tempo_ns ? a : b);
      interpretacao = `Nesta carga dinâmica, ${nomesAlgoritmos[menor.estrategia]} teve o menor tempo total
        medido (${ns(menor.tempo_ns)} ns). A reconstrução é uma medição separada.`;
    }
    if (acao === "ordenacao" && r.metricas.length > 1) {
      const menor = r.metricas.reduce((a, b) => a.tempo_ns <= b.tempo_ns ? a : b);
      interpretacao += ` Menor tempo neste recorte: ${nomesAlgoritmos[menor.estrategia]} (${ns(menor.tempo_ns)} ns).`;
    }
    estado.textContent = `${numero(r.quantidade, 0)} registros · ${r.equivalentes ? "Resultados validados" : "Divergência detectada"}. ${interpretacao}`;
    tabelaMetricas.hidden = false;
    this.raiz.querySelector("[data-exportar-metricas]").hidden = false;
  }

  diagnostico(dados) {
    return `${numero(dados.capacidade, 0)} baldes · carga ${numero(dados.fator_carga * 100)}% ·
      ${numero(dados.colisoes, 0)} colisões · maior balde: ${numero(dados.balde_maximo, 0)}`;
  }

  exportar() {
    if (!this.resultado) return;
    const r = this.resultado;
    const linhas = r.metricas.map((m) => ({
      nome_origem: r.origem_nome, quantidade: r.quantidade, ...r.selecao,
      ...r.configuracao, unidade_tempo: "ns", ...m
    }));
    const chaves = Object.keys(linhas[0]);
    const csv = [chaves, ...linhas.map((linha) => chaves.map((nome) => linha[nome]))]
      .map((linha) => linha.map((valor) => '"' + String(valor ?? "").replaceAll('"', '""') + '"').join(","))
      .join("\r\n");
    const url = URL.createObjectURL(new Blob(["\uFEFF", csv], {type: "text/csv;charset=utf-8"}));
    const link = document.createElement("a");
    link.href = url;
    link.download = "metricas_operacionais.csv";
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 500);
  }
}
