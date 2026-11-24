# IndustrialData

### Sistema de Monitoramento Industrial Simulado e Análise de Algoritmos

**Instituição:** Universidade de São Paulo — ICMC  
**Programa:** MECAI  
**Disciplina:** Análise de Algoritmos

**Integrantes:**

| Nome | Número USP |
|---|---|
| Vinicius Lazzeri | 15979921 |
| Rafael Nascimento | 18616390 |
| Wendel Avila | 18616319 |

## Apresentação

O IndustrialData é uma aplicação web local que representa a investigação de alertas e falhas em equipamentos industriais. A ordenação destaca medições críticas, a busca recupera registros por identificador e os índices permitem estudar o custo de consultas repetidas sobre um histórico. O projeto integra esses fluxos a uma avaliação experimental de algoritmos próprios.

**Em quais condições o custo de preparação e manutenção de índices é compensado pelo ganho nas consultas a registros industriais?**

## Objetivos

O objetivo geral é avaliar estratégias de processamento de registros industriais em diferentes volumes e cargas de trabalho. Os objetivos específicos são:

- Simular operações e investigar ocorrências a partir de registros com procedência identificável.
- Gerenciar a coleção de trabalho por cadastro, edição, remoção, consulta, importação e exportação CSV.
- Implementar e comparar três ordenações, três buscas e uma tabela hash com encadeamento.
- Medir tempo, operações e memória, incluindo os efeitos da preparação e da manutenção de índices.

## Funcionamento da aplicação

**Simulação → Ocorrência → Investigação → Consulta e Ordenação → Experimentos.**

No cenário demonstrativo, o torno CNC falha por desgaste no 12º ciclo do lote. O usuário abre a ocorrência, ordena as medições por torque ou temperatura, consulta o UDI associado e compara as estratégias no Laboratório. A investigação operacional trabalha com os registros daquele recorte. A avaliação acadêmica usa um protocolo reproduzível para estudar fatores como volume, distribuição das chaves e frequência de atualizações.

## Arquitetura e tecnologias

A aplicação usa Python 3.11+, Flask e Jinja2 no servidor, HTML5, CSS3 e JavaScript na interface e Chart.js para os gráficos. Os registros e a telemetria persistem em CSV. Configurações e resultados experimentais também usam JSON.

| Módulos | Responsabilidade |
|---|---|
| `app.py`, `core/web.py`, `templates/`, `static/` | Inicialização, páginas, API JSON/CSV e interface. |
| `core/dominio.py`, `core/repositorio.py`, `core/projecao.py`, `core/servicos.py` | Validação, persistência, projeção da telemetria na coleção e consistência dos índices. |
| `core/simulacao.py`, `core/investigacao.py` | Geração de ciclos, classificação de ocorrências e seleção de evidências. |
| `core/algoritmos.py`, `core/experimentos.py`, `core/trabalhos.py` | Estratégias próprias, protocolo de medição e execução em segundo plano. |

A orientação a objetos separa entidade, repositório, serviços e estratégias. Contratos comuns permitem que os clientes troquem de algoritmo sem reescrever o fluxo de consulta ou ordenação. [Diagrama, contratos e análise de corretude](docs/academico.md)

## Base de dados

O **AI4I 2020 Predictive Maintenance Dataset**, da UCI Machine Learning Repository, contém 10.000 observações sintéticas com identificador UDI, tipo de produto, temperaturas do ar e do processo, rotação, torque, desgaste e indicadores de falha. O arquivo original `data/ai4i2020.csv` é preservado. Alterações em **Registros** afetam a coleção de trabalho.

O simulador gera telemetria própria, identificada por máquina, ciclo e UDI. As correções nessa coleção preservam as leituras arquivadas no histórico operacional. Alertas e falhas simulados são classificados por regras didáticas de limiar. A aplicação opera sem modelos de aprendizado de máquina treinados. [Caracterização e procedência](docs/academico.md) · [AI4I 2020](https://doi.org/10.24432/C5HS5C)

## Simulação industrial

As máquinas são **M-01 — Torno CNC**, **M-02 — Fresadora** e **M-03 — Prensa industrial**. A configuração define rotação em rpm, torque em Nm, temperatura de processo, desgaste inicial em minutos e número de ciclos do lote. A semente é definida em **Dados e Configurações** e fixada no início do lote. A sequência também depende da máquina e do ciclo inicial.

Os modos são **Normal**, **Sobrecarga**, **Desgaste acelerado** e **Personalizado**. A sobrecarga eleva as referências de rotação, torque e temperatura. O desgaste acelerado acrescenta 8 min por ciclo. As condições operacionais são **Parada**, **Operando**, **Alerta** e **Falha**. **Pausada** é uma fase do lote que conserva as últimas leituras. A execução progressiva avança enquanto uma tela operacional visível solicita ciclos.

| Medição | Início do alerta padrão | Limite de falha padrão |
|---|---:|---:|
| Rotação | 2.465 rpm (85% do limite) | 2.900 rpm |
| Torque | 68 Nm (85% do limite) | 80 Nm |
| Temperatura de processo | 46,85 °C (4 °C abaixo do limite) | 50,85 °C |
| Desgaste | 200 min (80% do limite) | 250 min |

O alerta corresponde a uma leitura na faixa entre o limiar de alerta e o de falha. Atingir qualquer limite de falha interrompe o lote. Limites locais podem substituir os padrões. A interface operacional apresenta °C e os CSVs preservam Kelvin.

### Cenários de teste

Cada cenário parte de uma instância limpa e de uma máquina parada no ciclo zero. Os parâmetros iniciais de rotação e torque são 1.500 rpm e 40 Nm na M-01, 1.560 rpm e 44 Nm na M-02, e 1.440 rpm e 37 Nm na M-03. Todas partem de 36,85 °C e desgaste zero. A tabela indica os ajustes sobre esses padrões.

| Máquina | Cenário | Configuração | Semente | Ciclos previstos | Resultado esperado |
|---|---|---|---:|---:|---|
| M-01 | Operação estável | Normal | 101 | 3 | Três ciclos normais e conclusão. |
| M-01 | Sobrecarga mecânica | Sobrecarga, referência de 50 Nm | 102 | 3 | Torque entre 68 e 80 Nm, com três alertas e conclusão. |
| M-01 | Desgaste acelerado | Cenário demonstrativo, limite de 96 min | 42 | 12 | Alertas nos ciclos 10 e 11 e falha no 12º, ao atingir 96 min. |
| M-02 | Operação estável | Normal | 201 | 3 | Três ciclos normais e conclusão. |
| M-02 | Estresse térmico | Normal, processo a 48,85 °C | 202 | 3 | Três alertas acima de 46,85 °C e abaixo de 50,85 °C. |
| M-02 | Falha e recuperação | Normal, processo a 51,85 °C. Após reiniciar, 36,85 °C | 203 | 3 + 2 | Falha térmica no primeiro ciclo. O novo lote conclui dois ciclos normais e preserva o anterior. |
| M-03 | Operação estável | Normal | 301 | 3 | Três ciclos normais e conclusão. |
| M-03 | Sobrecarga operacional | Sobrecarga, referência de 57 Nm | 302 | 3 | Torque acima de 80 Nm e falha no primeiro ciclo. |
| M-03 | Controles e desgaste | Desgaste acelerado, limite local de 40 min | 303 | 6 + 6 | Pause após o primeiro ciclo, retome e interrompa após o segundo. O novo lote alerta a 32 min e falha a 40 min, no quinto ciclo acumulado. |

Inicie uma nova instância pelos comandos da seção de instalação. Defina a semente em **Dados e Configurações** e ajuste o modo, os parâmetros e o número de ciclos em **Máquinas**. Inicie o lote e observe estado, sensores e histórico. Para o cenário demonstrativo, use o botão em **Análise de Ocorrências** com a M-01 sem lote ativo ou pausado. [Evidências da API e do navegador](docs/validacao_final.md)

## Investigação de ocorrências

Cada alerta ou falha arquivado pode ser localizado pela combinação de **máquina, ciclo e UDI**. O recorte padrão inclui até 25 ciclos até a detecção. O intervalo pode ser ajustado para comparar sensores, identificar valores críticos por ordenação e confrontar as estratégias de busca. **Exportar evidências** gera o CSV do recorte. **Exportar métricas** gera o CSV das comparações. **Abrir em Registros** e **Comparar desempenho** levam o contexto à consulta e ao Laboratório, respectivamente.

## Algoritmos implementados

Para localizar um único registro, a busca sequencial pode dispensar a preparação de um índice. Em milhares de consultas à mesma coleção, um índice pode reduzir o custo total. O Laboratório estima o ponto de compensação e observa em quais lotes testados a economia aparece.

As ordenações usam uma medição numérica com desempate pelo UDI. Os custos de consulta abaixo consideram a estrutura já preparada.

| Algoritmo | Finalidade e complexidade | Pré-condições, vantagens e limites |
|---|---|---|
| Insertion Sort | Ordenar em Θ(n) no melhor caso e Θ(n²) no pior. | Adequado a entradas pequenas ou quase ordenadas. Muitas inversões elevam o custo. |
| Merge Sort | Ordenar em Θ(n log n). | Oferece custo previsível e usa vetor auxiliar. |
| Heap Sort | Ordenar em Θ(n log n) no pior caso, com construção da heap em Θ(n). | Garante o limite de pior caso. A API mantém chaves materializadas e uma lista de saída. |
| Busca sequencial | Consultar em Θ(n) no pior caso. | Aceita coleção sem ordem prévia. Pode percorrê-la inteira. |
| Busca binária | Consultar em Θ(log n) no pior caso. | Exige ordem por UDI. É previsível com chaves irregulares, mas manter o vetor ordenado pode exigir deslocamentos. |
| Busca por interpolação | Consultar em O(log log n) esperado para chaves uniformes e Θ(n) no pior caso. | Exige UDIs numéricos ordenados. Concentração e lacunas podem aumentar as sondas. |
| Tabela hash com encadeamento | Consultar em Θ(1 + α) esperado sob boa dispersão e Θ(n) no pior caso. | Atende consultas exatas por UDI. Capacidade e distribuição das chaves afetam colisões, tempo e memória. |

## Laboratório de Algoritmos

O **modo operacional** mede o recorte associado a uma máquina ou investigação. Demonstrações de mutação usam cópias de trabalho. O **modo acadêmico** executa experimentos reproduzíveis com entradas derivadas da origem escolhida. A bateria de referência usa o **Conjunto experimental controlado**, que mantém a mesma entrada e sequência de operações para as estratégias de um cenário. Os experimentos contextuais registram procedência, volume e SHA-256 da entrada congelada.

| Área | Foco |
|---|---|
| Ordenação | Tempo, comparações, movimentações e memória. |
| Busca | Preparação, consultas, passos e compensação frente à busca sequencial. |
| Tabela Hash | Capacidade, fator de carga, colisões e passos em consultas presentes e ausentes. |
| Custo do Sistema | Preparação, consultas e manutenção em cargas estáticas e dinâmicas. |

## Metodologia experimental

O perfil de referência usa **500, 2.000 e 8.000 registros**, semente-base **42** e **cinco repetições** por configuração. A ordenação cobre entradas aleatórias, crescentes, inversas e com medições repetidas. A busca usa **1.000 consultas**, metade presentes e metade ausentes, em UDIs regulares ou concentrados com lacunas. O ensaio hash usa fatores de carga-alvo **0,25, 0,50 e 0,75**. A carga dinâmica intercala **100 mutações**.

O tempo é medido com `perf_counter_ns()`. Comparações, movimentações e sondas são contabilizadas em passagem instrumentada, e o pico de alocações Python é medido separadamente com `tracemalloc`. As medições são resumidas por mediana e intervalo interquartil. O `sorted` nativo serve de referência separada.

**`T_total = T_preparação + T_consultas + T_manutenção`**

`T_preparação` mede a construção da estrutura usada para consultar. `T_consultas` mede a execução das buscas. `T_manutenção` mede o efeito de inserções, alterações e remoções na estrutura em memória. O total cronometrado do roteiro inclui ainda o custo de coordenação do laço, e a reconstrução isolada do índice é medida à parte. [Protocolo completo](docs/academico.md)

## Resultados e discussão

A execução arquivada reúne **105 configurações e 525 repetições**. Os resultados abaixo referem-se a 8.000 registros.

| Observação | Resultado de referência |
|---|---|
| Sensibilidade à ordem inicial | Insertion Sort fez 7.999 comparações na entrada crescente e 31.996.000 na inversa. |
| Distribuição dos UDIs | Em 1.000 consultas, a interpolação passou de 0,25 ms em chaves regulares para 121,78 ms em chaves concentradas, após o preparo. A binária levou cerca de 1,07 ms nos dois perfis. |
| Colisões na hash | Na base concentrada, as cargas-alvo 0,25, 0,50 e 0,75 geraram 3.086, 3.681 e 1.530 colisões. As capacidades produziram distribuições distintas de resíduos. |
| Carga dinâmica | Com 1.000 consultas e 100 mutações, as medianas do custo total foram 142,76 ms na sequencial, 17,82 ms na binária, 139,45 ms na interpolação e 2,66 ms na hash. |

Nas chaves concentradas, a hash superou a sequencial pela primeira vez no prefixo medido de 50 consultas, e a binária no de 250. A escolha depende do volume, da distribuição dos UDIs e da carga de atualização. A hash foi favorável para consultas exatas na carga medida. A binária oferece uma opção quando é útil manter uma representação ordenada. [CSVs, gráficos e interpretação](docs/resultados/interpretacao.md)

## Avaliação e entrega

O relatório de validação reúne evidências da API, do navegador e da reprodução dos experimentos. [Auditoria do enunciado](docs/validacao_final.md)

### Critérios de avaliação acadêmica

| Critério | Peso | Evidência no IndustrialData |
|---|---:|---|
| Sistema e dados | 15% | Coleção consultável, CRUD, CSV e estatísticas. `core/servicos.py` e `core/repositorio.py`. |
| Orientação a objetos | 20% | Entidade validada, repositório e estratégias intercambiáveis. `core/dominio.py` e `core/algoritmos.py`. |
| Algoritmos próprios | 20% | Três ordenações, três buscas e tabela hash. `core/algoritmos.py`. |
| Complexidade e corretude | 15% | Recorrência, invariantes, custos e testes. `docs/academico.md` e `tests/`. |
| Investigação experimental | 20% | Protocolo, medições, quatro gráficos e interpretação. `core/experimentos.py` e `docs/resultados/`. |
| Entrega e apresentação | 10% | Instruções de execução, documentação e roteiro. `README.md` e `docs/apresentacao.md`. |

## Instalação e execução

Execute os comandos na raiz do projeto. A versão mínima adotada é **Python 3.11**.

### Windows — PowerShell

Instale o Python com o lançador `py`. O exemplo usa Python 3.11. Se tiver uma versão posterior, substitua `-3.11` pelo seletor correspondente.

```powershell
py -3.11 --version
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pytest -q
python app.py
```

Se a ativação estiver bloqueada, execute `Set-ExecutionPolicy -Scope Process Bypass` na sessão atual ou substitua `python` por `.\.venv\Scripts\python.exe` nos comandos seguintes.

### Ubuntu — Terminal Bash

Os comandos abaixo usam o Python 3.12 fornecido pelo Ubuntu 24.04 LTS. Se `python3 --version` mostrar uma versão anterior à 3.11, use o Ubuntu 24.04 LTS ou crie o ambiente virtual com o executável de um Python 3.11+ instalado separadamente com suporte a `venv`. [Pacote python3 do Ubuntu 24.04](https://packages.ubuntu.com/noble/python3) · [Pacote python3-venv](https://packages.ubuntu.com/noble/python3-venv)

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip

python3 --version
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pytest -q
python app.py
```

Em ambos os sistemas, abra [http://127.0.0.1:5000](http://127.0.0.1:5000) e encerre o servidor com `Ctrl+C`.

### Instâncias isoladas

`INDUSTRIALDATA_INSTANCIA` aponta para a pasta de registros, configurações e históricos da sessão. Os blocos abaixo iniciam uma instância demonstrativa nova e usam `--port 0` no Flask para que o sistema escolha uma porta livre. Abra o endereço informado no terminal. Para fixar a porta, substitua `0` por uma porta livre, como `5050`.

**PowerShell**

```powershell
$env:INDUSTRIALDATA_INSTANCIA = Join-Path (Get-Location) "instancia/demo-$([guid]::NewGuid())"
python -m flask --app core.web:criar_app run --port 0
```

**Bash**

```bash
mkdir -p instancia
pasta_demo=$(mktemp -d "$PWD/instancia/demo-XXXXXXXX") &&
  INDUSTRIALDATA_INSTANCIA="$pasta_demo" python -m flask --app core.web:criar_app run --port 0
```

Encerre o servidor e repita o bloco para iniciar outro cenário desde o ciclo zero. No PowerShell, use `Remove-Item Env:INDUSTRIALDATA_INSTANCIA` após a demonstração para voltar à instância padrão nessa sessão. No exemplo Bash, a variável vale apenas para o comando Flask.

### Execução dos experimentos

Os mesmos comandos funcionam em PowerShell e Bash com o ambiente virtual ativo.

```text
python -m core.academico --semente 42 --pasta instancia/reproducao
python -m core.graficos instancia/reproducao
python -m tests.verificar_resultados instancia/reproducao
```

A bateria pode levar vários minutos. A pasta de saída recebe dados brutos e agregados em CSV, resultados em JSON e quatro gráficos PNG. [Referência arquivada e interpretação](docs/resultados/interpretacao.md)

## Glossário técnico

| Conceito | Definição no projeto |
|---|---|
| UDI | Identificador inteiro, único e não negativo usado nas consultas. |
| Índice | Estrutura preparada para localizar registros por UDI, como a tabela hash ou o vetor ordenado. |
| Custo de preparação | Tempo para construir a estrutura de consulta a partir da coleção. |
| Custo de manutenção | Tempo para incorporar inserções, alterações e remoções. |
| Fator de carga | Razão entre registros ativos e baldes na tabela hash. |
| Colisão | Inserção de uma chave nova em um balde já ocupado. |
| Mediana | Valor central das medições ordenadas, ou média dos dois valores centrais. |
| Intervalo interquartil | Diferença entre o terceiro e o primeiro quartis, usada para indicar dispersão. |
| SHA-256 | Resumo criptográfico usado para identificar o conteúdo do recorte experimental. |

## Questões para estudo e apresentação

1. **Qual problema o IndustrialData procura resolver?** Investigar medições associadas a ocorrências e avaliar o custo de localizar e manter registros em diferentes cargas de trabalho.
2. **Por que a busca binária necessita de uma coleção ordenada por identificador?** A ordem por UDI permite descartar uma metade do intervalo após cada comparação com o elemento central.
3. **Como a orientação a objetos permite substituir estratégias algorítmicas?** O serviço e o executor operam por contratos comuns de ordenação e consulta. Cada implementação assume o trabalho interno da estratégia.
4. **Quando a tabela hash pode compensar seu custo de preparação e manutenção?** Quando a economia nas consultas e atualizações cobre o custo de preparo, sob uma capacidade e uma dispersão compatíveis com a carga.
5. **Por que os resultados experimentais não permitem afirmar que um algoritmo é sempre superior?** Tempo e memória variam com o volume, a distribuição dos UDIs, a frequência de atualizações e o ambiente de execução.

## Tópicos para apresentação

1. Contextualização do problema, origem dos dados e pergunta central.
2. Arquitetura orientada a objetos e troca de estratégias algorítmicas.
3. Demonstração da simulação, da investigação de ocorrências e do gerenciamento de registros.
4. Metodologia, resultados experimentais e custos de preparação, consulta e manutenção.
5. Recomendação técnica para a carga medida e limites da conclusão.

[Guia de apresentação](docs/apresentacao.md)

## Limitações e referências

A AI4I é sintética, e a simulação representa falhas por limiares didáticos. A persistência local reescreve arquivos CSV e pressupõe um processo Flask por pasta de instância. A carga dinâmica mede estruturas em memória. Os tempos dependem do hardware, da versão do Python e da carga concorrente. A generalização dos resultados exige medir o perfil de dados e a persistência do ambiente de interesse.

- Base da UCI sob licença CC BY 4.0. [AI4I 2020](https://doi.org/10.24432/C5HS5C) · [Licença](https://creativecommons.org/licenses/by/4.0/)
- Flask 3.1.3, Matplotlib 3.10.8 e pytest 8.4.2 em `requirements.txt`. Chart.js 4.5.1 e as fontes Inter e IBM Plex Mono acompanham a aplicação com suas licenças em `static/vendor/`. [Flask](https://flask.palletsprojects.com/) · [Matplotlib](https://matplotlib.org/) · [pytest](https://docs.pytest.org/) · [Chart.js](https://www.chartjs.org/docs/latest/)
- Codex foi usado como ferramenta de apoio à implementação, à validação e à documentação. [Fundamentação e atribuições](docs/academico.md) · [Protótipo no Figma](https://www.figma.com/make/TI8E0CYbi53geA7k2QgjHW/Industrial-Monitoring-Analytics-Platform)
