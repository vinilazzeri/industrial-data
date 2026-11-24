"use strict";

const urlMaquina = (codigo) => "/api/maquinas/" + encodeURIComponent(codigo);

class ControleOperacional {
  constructor() {
    this.painel = null;
    this.conectado = false;
    this.observadores = [];
    this.fila = Promise.resolve();
    this.timer = null;
    this.suspenso = false;
  }

  observar(observador) {
    this.observadores.push(observador);
  }

  iniciar() {
    document.addEventListener("visibilitychange", () => {
      if (document.hidden) clearTimeout(this.timer);
      else if (!this.suspenso) this.sincronizar();
    });
    addEventListener("pagehide", () => {
      this.suspenso = true;
      clearTimeout(this.timer);
    });
    addEventListener("pageshow", (evento) => {
      if (evento.persisted) {
        this.suspenso = false;
        this.sincronizar();
      }
    });
    this.sincronizar();
  }

  sincronizar() {
    return this.enfileirar(() => this.consultar()).catch(() => {});
  }

  enfileirar(tarefa) {
    clearTimeout(this.timer);
    const resultado = this.fila.then(tarefa);
    const fim = resultado.catch(() => {});
    this.fila = fim;
    fim.then(() => {
      if (fim === this.fila) this.agendar();
    });
    return resultado;
  }

  agendar() {
    if (document.hidden || this.suspenso) return;
    const ativo = this.conectado && this.painel?.operando;
    this.timer = setTimeout(() => {
      this.enfileirar(() => this.avancar()).catch(() => {});
    }, ativo ? 650 : 1800);
  }

  async consultar() {
    let painel;
    try {
      painel = await requisicao("/api/painel?leve=1", {cache: "no-store"});
    } catch (erro) {
      this.conexao(false);
      throw erro;
    }
    this.publicar(painel);
    return painel;
  }

  async avancar() {
    if (document.hidden || this.suspenso) return;
    if (!this.conectado || !this.painel?.operando) {
      await this.consultar();
      return;
    }
    const ativos = this.painel.maquinas.filter((m) => m.execucao.fase === "Em execução");
    const versoes = Object.fromEntries(ativos.map(({codigo, execucao}) => [
      codigo, {id: execucao.id, versao: execucao.versao}
    ]));
    let resposta;
    try {
      resposta = await enviar("/api/operacao/avancar", "POST", {versoes});
    } catch (erro) {
      this.conexao(false);
      throw erro;
    }
    this.publicar(resposta.painel);
  }

  comandar(codigo, acao) {
    const url = codigo ? urlMaquina(codigo) + "/" + acao : "/api/maquinas/iniciar";
    const maquina = this.painel?.maquinas.find((item) => item.codigo === codigo);
    return this.alterar(url, "POST", maquina ? {lote: maquina.execucao.id} : {});
  }

  configurar(codigo, campos) {
    return this.alterar(urlMaquina(codigo), "PATCH", campos);
  }

  alterar(url, metodo, corpo) {
    return this.enfileirar(async () => {
      let resposta;
      try {
        resposta = await enviar(url, metodo, corpo);
      } catch (erro) {
        await this.consultar().catch(() => {});
        throw erro;
      }
      await this.consultar();
      return resposta;
    });
  }

  conexao(conectado) {
    this.conectado = conectado;
    document.querySelectorAll("[data-conexao-aviso]").forEach((aviso) => {
      aviso.hidden = conectado;
    });
    if (!conectado) {
      document.querySelectorAll("[data-unidade]").forEach((cartao) => {
        cartao.dataset.emMovimento = "false";
        cartao.querySelector("[data-controles]").inert = true;
        cartao.querySelector("[data-movimento]").textContent = "CONEXÃO INTERROMPIDA";
      });
      const frota = porId("executar-todas");
      if (frota) frota.disabled = true;
    }
  }

  publicar(painel) {
    this.painel = painel;
    this.conexao(true);
    for (const observador of this.observadores) observador(painel);
  }
}
