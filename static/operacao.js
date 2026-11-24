"use strict";

const controleOperacional = new ControleOperacional();
const mapaUnidades = new Map(Array.from(document.querySelectorAll("[data-unidade]"),
  (cartao) => [cartao.dataset.unidade, cartao]));
const unidadesOperacionais = {temperatura_processo: "°C", rpm: "rpm", torque: "Nm", desgaste: "min"};
const fasesAtivas = ["Em execução", "Pausada"];

function definirTexto(elemento, valor) {
  if (elemento.textContent !== valor) elemento.textContent = valor;
}

function descreverMotivo(motivo) {
  if (motivo.valor == null) return motivo.nome;
  return `${motivo.nome}: ${numero(motivo.valor)} ${motivo.unidade} ·
    ${motivo.nivel === "falha" ? "limite" : "alerta a partir de"}
    ${numero(motivo.nivel === "falha" ? motivo.limite : motivo.alerta)} ${motivo.unidade}`;
}

function estadoVisual(maquina) {
  return maquina.execucao.fase === "Pausada" ? "Pausada" : maquina.estado_atual;
}

function apresentarUnidade(maquina) {
  const cartao = mapaUnidades.get(maquina.codigo);
  cartao.querySelector("[data-investigar-maquina]").href = caminhoOcorrencia(
    maquina.codigo, maquina.ocorrencia_recente
  );
  const fase = maquina.execucao.fase;
  const estado = estadoVisual(maquina);
  const movimentando = fase === "Em execução" && maquina.sensores.rpm > 0 && estado !== "Falha";
  const visual = estado.toLowerCase();
  cartao.dataset.visual = visual;
  cartao.dataset.emMovimento = String(movimentando);
  const seloEstado = cartao.querySelector("[data-estado]");
  seloEstado.className = "selo " + visual;
  definirTexto(seloEstado, estado);
  if (maquina.sensores.rpm > 0) {
    // A cadência é uma escala visual. Os ciclos do Python seguem o seu próprio relógio.
    const rpm = maquina.sensores.rpm;
    const cadencia = Math.min(2.4, Math.max(.4, 2.6 - rpm / 1200));
    cartao.style.setProperty("--cadencia", cadencia.toFixed(3) + "s");
    cartao.style.setProperty("--cadencia-prensa", (cadencia * 1.28 + .24).toFixed(3) + "s");
  }
  const avisoMovimento = {
    parada: "MECANISMO EM REPOUSO", pausada: "MOVIMENTO CONGELADO",
    falha: "MOVIMENTO BLOQUEADO", alerta: "OPERAÇÃO EM ALERTA"
  }[visual] || (movimentando ? "MECANISMO ATIVO" : "AGUARDANDO LEITURA");
  definirTexto(cartao.querySelector("[data-movimento]"), avisoMovimento);
  for (const sensor of cartao.querySelectorAll("[data-sensor]")) {
    const campo = sensor.dataset.sensor;
    const info = maquina.indicadores[campo];
    const valor = maquina.sensores[campo === "temperatura" ? "temperatura_c" : campo];
    const casas = campo === "temperatura" || campo === "torque" ? 1 : 0;
    definirTexto(sensor.querySelector("[data-valor]"), numero(valor, casas));
    sensor.dataset.nivel = info.nivel;
    sensor.title = `${info.nome} · alerta a partir de ${numero(info.alerta)} ${info.unidade} ·
      falha a partir de ${numero(info.limite)} ${info.unidade}${info.nivel === "normal" ? "" :
        " · leitura do ciclo: " + numero(info.valor) + " " + info.unidade}`;
  }
  const carga = maquina.carga_percentual;
  definirTexto(cartao.querySelector("[data-carga]"), carga == null ? "—" : numero(carga, 0) + "%");
  const medidor = cartao.querySelector("[data-carga-barra]");
  medidor.value = carga ?? 0;
  medidor.dataset.sobrecarga = String(carga >= 100);
  const lote = maquina.execucao;
  const percentual = lote.total ? 100 * lote.realizados / lote.total : 0;
  definirTexto(cartao.querySelector("[data-ciclos]"), lote.total
    ? `Lote ${numero(lote.realizados, 0)}/${numero(lote.total, 0)} · Total ${numero(maquina.ciclo, 0)}`
    : `Ciclos registrados · ${numero(maquina.ciclo, 0)}`);
  definirTexto(cartao.querySelector("[data-percentual]"), numero(percentual, 0) + "%");
  cartao.querySelector("[data-progresso]").value = percentual;
  let condicao;
  if (maquina.motivos.length) {
    condicao = maquina.motivos.slice(0, 2).map(descreverMotivo).join(" / ");
    if (maquina.motivos.length > 2) condicao += " / +" + (maquina.motivos.length - 2);
    if (estado === "Pausada") condicao = "Último alerta · " + condicao;
  } else {
    condicao = {
      "Concluída": "Lote concluído. Leituras disponíveis no histórico.",
      "Interrompida": "Lote interrompido. Ciclos registrados preservados.",
      "Pausada": "Lote pausado. Últimas leituras preservadas."
    }[fase] || (estado === "Parada" ? "Máquina parada. Pronta para iniciar."
      : movimentando ? "Sensores dentro dos limites operacionais." : "Aguardando a primeira leitura do lote.");
  }
  definirTexto(cartao.querySelector("[data-condicao]"), condicao);

  const comandos = estado === "Falha" ? ["reiniciar"]
    : fase === "Pausada" ? ["retomar", "interromper"]
    : fase === "Em execução" ? ["pausar", "interromper", "falha"]
    : ["iniciar"];
  cartao.querySelector("[data-controles]").inert = false;
  cartao.querySelectorAll("[data-comando]").forEach((botao) => {
    botao.hidden = !comandos.includes(botao.dataset.comando);
  });
  cartao.querySelector("[data-configurar]").hidden = !comandos.includes("iniciar");
  cartao.querySelector("[data-ver-falha]").hidden = estado !== "Falha";
}

function caminhoOcorrencia(codigo, ocorrencia) {
  const argumentos = new URLSearchParams({origem: codigo});
  if (ocorrencia) argumentos.set("ocorrencia", ocorrencia);
  return "/ocorrencias?" + argumentos;
}

function apresentarEventos(destino, eventos) {
  destino.innerHTML = eventos.length ? eventos.map((evento) => {
    const estado = evento.fase === "Pausada" ? "Pausada" : evento.estado;
    const motivos = evento.motivos?.map(descreverMotivo).join(" / ") || "";
    return `<div class="evento"><span class="glifo neutro">${escapar(evento.equipamento)}</span>
      <div><strong>${escapar(evento.descricao)}</strong><small>Ciclo ${numero(evento.ciclo, 0)}${motivos
        ? " · " + escapar(motivos) : ""}</small>${evento.ocorrencia
          ? `<a class="link" href="${escapar(caminhoOcorrencia(evento.equipamento, evento.ocorrencia))}">Investigar ocorrência</a>`
          : ""}</div>${selo(estado)}</div>`;
  }).join("") : '<p class="estado-vazio">Ainda não há eventos neste período.</p>';
}

function tendenciaOperacional(id, aviso, maquinas, campo) {
  const serie = maquinas.map((maquina) => ({
    nome: maquina.codigo,
    valores: maquina.historico.map((r) => ({
      x: r.ciclo, y: r[campo === "temperatura_processo" ? "temperatura_c" : campo]
    }))
  }));
  porId(aviso).hidden = serie.some((item) => item.valores.length);
  const assinatura = campo + "/" + serie.map((item) => item.nome).join("/");
  const tela = porId(id);
  const grafico = Chart.getChart(tela);
  if (grafico && tela.dataset.serie === assinatura) {
    serie.forEach((item, i) => {
      grafico.data.datasets[i].data = item.valores;
      grafico.data.datasets[i].pointRadius = item.valores.length < 20 ? 3 : 1;
    });
    grafico.update("none");
  } else {
    tela.dataset.serie = assinatura;
    desenhar(id, "line", serie, {
      linear: true, eixoX: "Ciclo", eixoY: unidadesOperacionais[campo],
      legenda: maquinas.length > 1, inteirosX: true
    });
  }
}

function configurarDialogos() {
  const formulario = porId("parametros-maquina");
  const modal = porId("modal-configuracao");
  const erroFormulario = formulario.querySelector(".erro-form");
  let configurando;
  let indicadores;
  const modos = {
    Normal: "Operação padrão; adiciona 2 min de desgaste por ciclo.",
    Sobrecarga: "Eleva rotação, torque e temperatura; adiciona 3 min de desgaste.",
    "Desgaste acelerado": "Adiciona 8 min de desgaste por ciclo.",
    Personalizado: "Usa as referências informadas e adiciona 1 min de desgaste."
  };

  function mostrarFaixas() {
    definirTexto(porId("descricao-modo"), modos[formulario.elements.modo.value]);
    formulario.querySelectorAll("[data-faixa]").forEach((rotulo) => {
      const campo = rotulo.dataset.faixa;
      const indicador = indicadores[campo === "temperatura_c" ? "temperatura" : campo];
      const valor = formulario.elements[campo].valueAsNumber;
      rotulo.dataset.nivel = valor >= indicador.limite ? "falha" : valor >= indicador.alerta ? "alerta" : "normal";
      definirTexto(rotulo, `Faixa vigente · aviso ≥ ${numero(indicador.alerta)} · falha ≥ ${numero(indicador.limite)}`);
    });
  }

  function abrirConfiguracao(maquina) {
    configurando = maquina.codigo;
    indicadores = maquina.indicadores;
    porId("titulo-configuracao").textContent = "Configurar " + maquina.codigo;
    erroFormulario.textContent = "";
    for (const campo of ["rpm", "torque", "temperatura_c", "desgaste", "ciclos", "modo"]) {
      formulario.elements[campo].value = maquina.parametros[campo];
    }
    for (const campo of ["rpm", "torque", "temperatura_c", "desgaste"]) {
      const valor = maquina.limites_locais[campo === "temperatura_c" ? "temperatura" : campo];
      formulario.elements["limite_" + campo].value = valor == null ? ""
        : campo === "temperatura_c" ? Number((valor - 273.15).toFixed(8)) : valor;
    }
    mostrarFaixas();
    modal.showModal();
  }

  function abrirFalha(maquina) {
    porId("titulo-falha").textContent = maquina.codigo + " · Falha";
    porId("falha-contexto").textContent = `Ocorrência no ciclo ${numero(maquina.ciclo, 0)}. Reinicie a máquina para liberar um novo lote.`;
    const lista = porId("falha-motivos");
    lista.replaceChildren(...maquina.motivos.map((motivo) => {
      const item = document.createElement("li");
      item.textContent = descreverMotivo(motivo);
      return item;
    }));
    porId("modal-falha").showModal();
  }

  formulario.addEventListener("input", mostrarFaixas);
  formulario.addEventListener("submit", (evento) => {
    evento.preventDefault();
    erroFormulario.textContent = "";
    ocupado(evento.submitter, async () => {
      const valores = Object.fromEntries(new FormData(formulario));
      const limites = {};
      for (const campo of ["rpm", "torque", "temperatura_c", "desgaste"]) {
        const chave = "limite_" + campo;
        limites[campo] = valores[chave] || null;
        delete valores[chave];
      }
      await controleOperacional.configurar(configurando, {...valores, limites_locais: limites});
      modal.close();
      avisar("Parâmetros salvos para " + configurando + ".");
    }, (erro) => { erroFormulario.textContent = erro.message; });
  });

  mapaUnidades.forEach((cartao, codigo) => {
    cartao.querySelector("[data-configurar]").addEventListener("click", () => {
      const maquina = controleOperacional.painel?.maquinas.find((m) => m.codigo === codigo);
      if (maquina && !fasesAtivas.includes(maquina.execucao.fase)) abrirConfiguracao(maquina);
    });
    cartao.querySelector("[data-ver-falha]").addEventListener("click", () => {
      const maquina = controleOperacional.painel?.maquinas.find((m) => m.codigo === codigo);
      if (maquina?.estado_atual === "Falha") abrirFalha(maquina);
    });
    cartao.querySelectorAll("[data-comando]").forEach((botao) => {
      botao.addEventListener("click", () => ocupado(botao, async () => {
        await controleOperacional.comandar(codigo, botao.dataset.comando);
        if (botao.hidden && document.activeElement === document.body) {
          cartao.querySelector("[data-comando]:not([hidden])")?.focus();
        }
      }));
    });
  });
}

function iniciarPainel() {
  const campo = porId("tendencia-campo");
  const frota = porId("executar-todas");
  const desenharPainel = () => {
    if (!controleOperacional.painel) return;
    tendenciaOperacional("tendencia", "tendencia-vazia", controleOperacional.painel.maquinas, campo.value);
  };
  controleOperacional.observar((painel) => {
    for (const kpi of ["operando", "gerados", "alertas", "falhas"]) {
      definirTexto(porId(kpi), numero(painel[kpi], 0));
    }
    frota.disabled = !painel.maquinas.some((m) =>
      m.estado_atual !== "Falha" && !fasesAtivas.includes(m.execucao.fase)
    );
    apresentarEventos(porId("eventos"), painel.eventos);
    desenharPainel();
  });
  campo.addEventListener("change", desenharPainel);
  frota.addEventListener("click", async () => {
    frota.disabled = true;
    try {
      const resultado = await controleOperacional.comandar(null, "iniciar");
      avisar(`${numero(resultado.iniciadas, 0)} máquinas iniciadas.`);
    } catch (erro) {
      avisar(erro.message, true);
    }
  });
  controleOperacional.iniciar();
}

configurarDialogos();
controleOperacional.observar((painel) => painel.maquinas.forEach(apresentarUnidade));
if (document.body.dataset.pagina === "painel") iniciarPainel();
