"use strict";

const porId = (id) => document.getElementById(id);
const numero = (valor, casas = 2) => valor == null ? "—" : Number(valor).toLocaleString(
  "pt-BR", {maximumFractionDigits: casas}
);
const escapar = (valor) => String(valor ?? "").replace(/[&<>"']/g, (letra) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
})[letra]);
const rotulosMedicao = {
  temperatura_ar: ["Temperatura do ar", "K"], temperatura_processo: ["Temperatura", "K"],
  rpm: ["Rotação", "rpm"], torque: ["Torque", "Nm"], desgaste: ["Desgaste", "min"]
};
const nomesAlgoritmos = {
  sequencial: "Sequencial", binaria: "Binária", interpolacao: "Interpolação",
  hash: "Tabela hash", insercao: "Insertion Sort", intercalacao: "Merge Sort",
  heap: "Heap Sort", nativo: "Python sorted"
};
const coresGrafico = ["#48cfbf", "#65b8e9", "#f4b860", "#b6a1ef"];
let prazoMensagem;

async function requisicao(caminho, opcoes = {}) {
  let resposta;
  try {
    resposta = await fetch(caminho, opcoes);
  } catch {
    throw new Error("Sem conexão com o servidor local.");
  }
  if (resposta.status === 204) return null;
  const corpo = await resposta.json().catch(() => ({}));
  if (!resposta.ok) throw new Error(corpo.erro || "Falha ao consultar o servidor.");
  return corpo;
}

const enviar = (caminho, metodo, corpo) => requisicao(caminho, {
  method: metodo, headers: {"Content-Type": "application/json"}, body: JSON.stringify(corpo)
});

function avisar(texto, erro = false) {
  const aviso = porId("mensagem");
  aviso.textContent = texto;
  aviso.classList.toggle("erro", erro);
  aviso.hidden = false;
  clearTimeout(prazoMensagem);
  prazoMensagem = setTimeout(() => { aviso.hidden = true; }, erro ? 7000 : 4200);
}

async function ocupado(controle, executar, tratarErro = (erro) => avisar(erro.message, true)) {
  if (controle.disabled) return;
  controle.disabled = true;
  controle.setAttribute("aria-busy", "true");
  try {
    await executar();
  } catch (erro) {
    tratarErro(erro);
  } finally {
    controle.disabled = false;
    controle.removeAttribute("aria-busy");
  }
}

function selo(estado) {
  const classe = ["operando", "normal", "alerta", "falha", "parada", "pausada"].includes(estado.toLowerCase())
    ? estado.toLowerCase() : "parada";
  return `<span class="selo ${classe}">${escapar(estado)}</span>`;
}

function tabela(destino, colunas, linhas, vazio = "Nenhum registro encontrado.") {
  destino.innerHTML = linhas.length
    ? `<table><thead><tr>${colunas.map((c) => `<th scope="col">${escapar(c)}</th>`).join("")}</tr></thead>
       <tbody>${linhas.map((linha) => `<tr>${linha.map((c) => `<td>${c}</td>`).join("")}</tr>`).join("")}</tbody></table>`
    : `<p class="estado-vazio">${escapar(vazio)}</p>`;
}

function estatisticasTabela(destino, resumo) {
  tabela(destino, ["Medição", "Mínimo", "Q1", "Mediana", "Q3", "Máximo", "Média", "Desvio"],
    Object.entries(resumo.medicoes).map(([campo, dados]) => [
      rotulosMedicao[campo].join(" · "), ...["minimo", "q1", "mediana", "q3", "maximo", "media", "desvio"]
        .map((indicador) => numero(dados[indicador]))
    ]), "Ainda não há medições.");
}

function desenhar(id, tipo, series, {eixoX = "", eixoY = "", linear = false, etiquetas = [],
  legenda = true, zero = false, log = false, proporcao = false, inteirosX = false} = {}) {
  const tela = porId(id);
  Chart.getChart(tela)?.destroy();
  const eixo = (titulo) => ({
    grid: {color: "#263741"}, border: {color: "#344655"},
    ticks: {color: "#a3b8c5", maxTicksLimit: 9, font: {family: "IBM Plex Mono", size: 10}},
    title: {display: Boolean(titulo), text: titulo, color: "#a3b8c5", font: {size: 11}}
  });
  new Chart(tela, {
    type: tipo,
    data: {
      labels: etiquetas,
      datasets: series.map(({nome, valores, cor, raio, ordem}, indice) => {
        const pigmento = cor || coresGrafico[indice % coresGrafico.length];
        return {
          label: nome, data: valores, borderColor: pigmento,
          backgroundColor: tipo === "bar" ? pigmento + "a8" : pigmento,
          borderWidth: 2, pointRadius: raio ?? (valores.length < 20 ? 3 : 1), pointHoverRadius: 5,
          order: ordem ?? 0,
          fill: false, tension: .19, borderRadius: 4, maxBarThickness: 36
        };
      })
    },
    options: {
      animation: false, responsive: true, maintainAspectRatio: false,
      interaction: {mode: "nearest", intersect: false},
      scales: {
        x: {...eixo(eixoX), type: linear ? "linear" : "category",
          ticks: {...eixo(eixoX).ticks, precision: inteirosX ? 0 : undefined,
            callback: proporcao ? (valor) => numero(valor * 100, 1) + "%" : undefined}},
        y: {...eixo(eixoY), type: log ? "logarithmic" : "linear", beginAtZero: zero}
      },
      plugins: {
        legend: {display: legenda, labels: {color: "#c2d1db", usePointStyle: true, boxWidth: 7, pointStyleWidth: 7, padding: 16}},
        tooltip: {backgroundColor: "#182630", borderColor: "#3e5564", borderWidth: 1}
      }
    }
  });
}

porId("menu").addEventListener("click", () => {
  const aberto = porId("navegacao").classList.toggle("aberta");
  porId("menu").setAttribute("aria-expanded", String(aberto));
});
document.addEventListener("keydown", (evento) => {
  if (evento.key === "Escape" && porId("navegacao").classList.contains("aberta")) {
    porId("navegacao").classList.remove("aberta");
    porId("menu").setAttribute("aria-expanded", "false");
    porId("menu").focus();
  }
});
document.querySelectorAll("[data-fechar]").forEach((botao) => {
  botao.addEventListener("click", () => botao.closest("dialog").close());
});

