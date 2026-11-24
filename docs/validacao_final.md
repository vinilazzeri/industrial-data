# Validação final do IndustrialData

Validação realizada em 24/11/2026. Escopo auditado contra o enunciado oficial `Projeto_Final_MECAI_Ciencia_de_Dados_Python_OO.pdf`, encontrado no diretório pai do projeto. A auditoria abrangeu código, protocolo acadêmico, integração, navegador e preservação dos dados.

## Ambiente e inspeção

- Windows 11 Pro, compilação 26200, AMD Ryzen 7 7800X3D, 16 processadores lógicos e aproximadamente 31 GiB de RAM. Python CPython 3.11.0. Os algoritmos executaram na CPU.
- Flask 3.1.3, Matplotlib 3.10.8, pytest 8.4.2 e Chart.js 4.5.1. A verificação de navegador usou Playwright 1.65.2 e Microsoft Edge 158.0.4370.33 em modo headless. Para a suíte e a reprodução final, foi criado um ambiente virtual novo com `requirements.txt`.
- Documentação inspecionada em `README.md`, `docs/academico.md`, `docs/apresentacao.md` e `docs/resultados/interpretacao.md`, junto aos CSVs, JSONs e PNGs arquivados.
- Código inspecionado em `app.py`, `core/web.py`, `dominio.py`, `repositorio.py`, `projecao.py`, `servicos.py`, `simulacao.py`, `investigacao.py`, `algoritmos.py`, `experimentos.py`, `trabalhos.py`, `academico.py`, `estatisticas.py` e `graficos.py`. Foram verificadas as páginas Jinja, os scripts de operação, gráficos, ocorrências, registros e laboratório e os testes em `tests/`.
- A suíte usa `tmp_path`. A execução de navegador definitiva criou uma pasta e um servidor em uma porta efêmera para cada cenário. Os resultados acadêmicos novos foram gravados em um diretório de validação. A pasta do projeto não tem metadados Git.

O servidor congela a semente global e os limites efetivos no início de cada lote. Cada ciclo deriva sua sequência pseudoaleatória da semente, do equipamento e do contador local. A gravação usa substituição atômica de snapshots CSV. Os UDIs novos são maiores que o maior UDI da coleção de trabalho e que o último da telemetria arquivada. A ocorrência referencia a dupla máquina/ciclo e o UDI daquele ciclo. A projeção mantém correções e remoções da coleção de trabalho, preservando a telemetria histórica. A navegação carrega o recorte por meio dos filtros na URL e o executor processa a entrada congelada em outro processo.

## Nove cenários industriais

Cada cenário começou com máquina parada, fase Inativa, ciclo zero e desgaste zero, em uma instância nova. Os padrões iniciais são 1.500 rpm/40 Nm no torno, 1.560 rpm/44 Nm na fresadora e 1.440 rpm/37 Nm na prensa. A temperatura de processo de referência é 310 K (36,85 °C). Os limites padrão são 2.900 rpm, 80 Nm, 324 K (50,85 °C) e 250 min. O alerta começa em 85% dos limites de torque e rotação, 4 K abaixo do limite térmico e 80% do limite de desgaste. Atingir um limite caracteriza falha.

| # | Equipamento e objetivo | Modo e ajustes | Semente e ciclos solicitados | Resultado esperado | Resultado observado |
|---|---|---|---|---|---|
| 1 | M-01, operação estável | Normal, padrões | 101, 3 | Concluir com 3 leituras normais | Aprovado. Três ciclos, desgaste de 2 a 6 min e lote Concluída. |
| 2 | M-01, esforço mecânico | Sobrecarga, torque de referência 50 Nm | 102, 3 | Alerta por torque entre 68 e 80 Nm e conclusão | Aprovado. Três leituras em alerta, com evento de torque desde o ciclo 1. A primeira foi 72,13 Nm. |
| 3 | M-01, falha por desgaste | Cenário demonstrativo, Desgaste acelerado, limite de 96 min | 42, 12 | Incrementos de 8 min, alerta no 10º e 11º ciclos e falha no 12º | Aprovado. Falha a 96 min no ciclo 12, UDI 10012 na instância vazia. A repetição em outra instância produziu as mesmas leituras. |
| 4 | M-02, operação independente | Normal, padrões | 201, 3 | Concluir com 3 leituras normais | Aprovado. Três ciclos, animação ativa em operação e parada ao concluir. |
| 5 | M-02, estresse térmico | Normal, processo de referência 322 K (48,85 °C) | 202, 3 | Alerta térmico a partir de 320 K, dentro do limite de 324 K | Aprovado. Três alertas. Primeira medição de processo 321,82 K (48,67 °C) e do ar 311,82 K. |
| 6 | M-02, falha e recuperação | Normal, processo 325 K (51,85 °C). Após rearme, 310 K | 203, 3 + 2 | Falhar no primeiro ciclo, bloquear e concluir o lote de recuperação após rearme | Aprovado. Falha a 324,93 K no primeiro ciclo. Após rearme, mais dois ciclos normais. UDIs 10001 a 10003, com histórico anterior preservado. |
| 7 | M-03, operação estável | Normal, padrões | 301, 3 | Concluir com 3 leituras normais | Aprovado. Três ciclos e movimento da prensa em operação. |
| 8 | M-03, esforço acima do limite | Sobrecarga, torque de referência 57 Nm | 302, 3 | Ultrapassar 80 Nm, registrar falha e bloquear novos ciclos | Aprovado. Falha por torque de 83,32 Nm no primeiro ciclo, com somente uma leitura. |
| 9 | M-03, pausa, retomada, interrupção e desgaste | Desgaste acelerado, limite local 40 min, 2 lotes | 303, 6 + 6 | Preservar a série parcial. Alertar a 32 min e falhar a 40 min no ciclo acumulado 5 | Aprovado. Na API, o primeiro lote foi interrompido após duas leituras. O novo lote preservou a progressão e falhou no ciclo 5. No Edge foram exercitados os controles e conferido o mesmo resultado final. |

Para cada cenário, os testes de API verificaram o estado inicial e final, as leituras reproduzíveis de RPM, torque, temperatura e desgaste, as médias por sensor, a associação entre eventos e ciclos, UDIs, CSV, consulta por hash e reabertura da instância. A verificação em Edge observou selos de estado, CSS de animação, linhas do histórico e estatísticas. Para cada máquina e cenário, os pontos de temperatura no Chart.js foram comparados com os ciclos e valores em °C retornados pela API.

A primeira versão do teste parametrizado usava a rotação de referência do torno para as três máquinas. A conferência foi corrigida para calcular as quatro leituras a partir dos parâmetros de cada equipamento e da sequência determinística do ciclo. A asserção da tabela hash no navegador também foi ajustada para conferir as três linhas exibidas sob o filtro ativo. Os arquivos acadêmicos completos foram verificados independentemente desse filtro.

### Teste conjunto de frota

Foram iniciadas M-01 a 1.400 rpm, M-02 a 73 Nm e M-03 com desgaste acelerado e limite de 16 min, cada uma com cinco ciclos configurados e sementes 71, 72 e 73 respectivamente. Dois envios concorrentes com os mesmos tokens produziram 3 e 0 ciclos. O reenvio com tokens já consumidos após resposta simuladamente perdida produziu 0. A M-01 pausou enquanto M-02 e M-03 avançaram, e a falha da M-03 no segundo ciclo deixou M-02 em execução. A M-02 foi interrompida e a M-01 concluiu. Resultaram 5, 3 e 2 ciclos, dez UDIs únicos e alertas atribuídos à M-02, verificados novamente após reabrir a instância.

## Integração e corretude

| Verificação | Evidência executada |
|---|---|
| Ocorrência, seleção e exportação | O cenário demonstrativo foi repetido após 16 ciclos normais em uma instância isolada. A falha ocorreu no ciclo 28 e o recorte padrão cobriu os ciclos 4 a 28. O ajuste para 20 a 28 devolveu 9 leituras no JSON e no CSV, com média de desgaste de 64 min e vínculo do ciclo de falha ao mesmo UDI. |
| Ordenações | Insertion, Merge e Heap produziram os mesmos nove registros em ordem de torque e UDI. Foram conferidos tempos e contagens. A suíte inclui empates, vazio, listas unitárias e preservação dos atributos. A tela Registros aceita as três estratégias e exporta todos os resultados da seleção ordenada. |
| Buscas e consistência após CRUD | As quatro estratégias concordaram para o UDI da falha e para uma ausência no recorte. A suíte também verificou duplicidade, imutabilidade do UDI, importação, exportação, alterações efetivas, reaproveitamento de índice em uma edição idêntica e reconstrução após remoção. Binária e interpolação preparam a coleção em ordem de UDI com Merge próprio. |
| Hash | Capacidade 1 gerou colisões deliberadas. A consulta depois da remoção devolveu ausência. A sequência operou numa cópia, e o histórico operacional e o CSV do recorte permaneceram idênticos. Os três fatores de carga foram conferidos nos artefatos acadêmicos. |
| Laboratório contextual | No Edge, o fluxo Ocorrência → Registros manteve o UDI e o recorte. O link ao laboratório acompanhou o filtro de fonte. Foram exercitados demonstração hash, custo do sistema, execução acadêmica contextual, retorno à ocorrência e downloads CSV/PNG. A ocorrência também foi verificada em viewport de 390 px. |
| Imutabilidade da execução | O experimento contextual hash com tamanhos 2, 5 e 9 exportou 45 linhas de dados brutos, registrou nove registros disponíveis, fonte e SHA-256 igual ao CSV de entrada sem BOM. A correção posterior de um torque marcou o recorte como alterado. O hash armazenado, o CSV de métricas e a telemetria original permaneceram iguais. |

## Auditoria do enunciado

| Critério | Peso | Evidências e situação |
|---|---:|---|
| Sistema e dados | 15% | Problema, usuário, hipóteses, esquema, unidades e caracterização AI4I em `docs/academico.md`. `RegistroIndustrial` valida atributos e UDI inteiro não negativo. Repositório e serviço rejeitam duplicatas, coordenam CRUD e invalidam índices. A página Registros exporta resultados ordenados, e estatísticas e histogramas atendem ao resumo do domínio. Verificado em código e nos testes de núcleo, API e investigação. |
| Orientação a objetos | 20% | Entidade imutável, repositório com snapshots, composição com serviço e simulador, `ABC` para ordenação e busca, `Protocol` para índice, objetos de métricas por execução, type hints, diagrama e contratos em `docs/academico.md`. As estratégias operacionais e experimentais foram exercitadas por contrato comum. |
| Algoritmos próprios | 20% | `core/algoritmos.py` contém Insertion, Merge recursivo, Heap com construção bottom-up e sift-down iterativo, buscas sequencial, binária e interpolação e hash encadeada com baldes em listas. `sorted` e mapas nativos são usados em validação, delineamento, referência ou metadados. Os métodos avaliados realizam seus próprios passos. |
| Complexidade e corretude | 15% | `docs/academico.md` descreve hipóteses, melhores e piores casos, espaço de trabalho, recorrência resolvida de Merge, invariantes, preparação, manutenção e custo de I/O. O exemplo da heap mostra construção e duas extrações. As contagens são executadas separadamente da cronometragem. |
| Investigação experimental | 20% | Três tamanhos comuns e quatro perfis de ordenação, 1.000 consultas em proporção 50/50, chaves regulares e concentradas, três fatores de carga, 100 mutações no cenário dinâmico, mesma carga entre estratégias, cinco repetições, semente e mediana/IIQ, tempo e memória separados. CSVs e quatro figuras conferidos. `sorted` aparece como referência nativa independente. A interpretação relaciona as escolhas ao perfil de uso, custos e hipóteses. |
| Entrega e apresentação | 10% | README, dependências, relatório acadêmico, roteiro, dados, CSVs e gráficos presentes. A execução pelo terminal foi conferida em ambiente novo. O enunciado também exige empacotamento em ZIP, declaração de contribuições individuais e participação dos três integrantes. As contribuições precisam ser fornecidas pelo grupo e a apresentação ainda será realizada. |

## Correção e testes de regressão

O executor acadêmico selecionava diretamente os objetos globais em vez de recebê-los por composição. Um teste com duas ordenações fornecidas pelo chamador reproduziu a limitação. `ExecutorExperimentos` passou a receber estratégias para os papéis existentes e a repassá-las às medições, incluindo a estratégia de busca na montagem e reconstrução da carga dinâmica. A coleção dinâmica padrão usa os contratos de armazenamento das estratégias nativas e admite um adaptador para outras estruturas. A aba Busca usa o contrato de consulta e publica diagnósticos extras quando o índice os fornece. A aba Tabela Hash exige diagnóstico para estudar o fator de carga. Três testes de regressão cobrem essa composição, incluindo um adaptador que separa a estratégia do índice. As implementações dos algoritmos, os limiares e as configurações padrão foram preservados.

A suíte final executada no ambiente novo passou com **61 testes**. Os nove cenários parametrizados, o teste conjunto, a integração contextual e as três regressões foram adicionados à suíte anterior. A checagem Ruff passou nos arquivos Python alterados. A checagem global indicou avisos preexistentes de estilo e análise estática fora dos arquivos modificados.

## Reprodução acadêmica

| Aba | Configurações | Repetições cronometradas | Figura |
|---|---:|---:|---|
| Ordenação | 48 | 240 | Crescimento das ordenações |
| Busca | 24 | 120 | Custo das buscas |
| Tabela Hash | 9 | 45 | Efeito do fator de carga |
| Custo do sistema | 24 | 120 | Preparação, consultas e atualizações |
| Total | 105 | 525 | Quatro gráficos |

O verificador conferiu dimensões e integridade dos PNGs, equivalência entre CSVs e JSONs, sementes e unidades, cinco repetições por cenário e recálculo de medianas e intervalos interquartis. A grade de compensação contém 18 comparações. A reconstrução isolada do índice foi registrada na execução nova para os cenários dinâmicos. O arquivo de referência anterior a essa métrica foi conferido com `--referencia`. Em cada combinação de tamanho e distribuição, uma checagem adicional obteve 500 consultas presentes, 500 ausentes e a mesma sequência de 100 mutações com a mesma semente.

As saídas dos algoritmos foram comparadas com oráculos pelo executor. A bateria completa foi repetida após o ajuste de composição e produziu as mesmas 105 configurações e 525 repetições. Após o ajuste posterior do diagnóstico, foram repetidos os perfis completos de Busca e Hash, com a mesma procedência e as mesmas métricas determinísticas. Os tempos se aplicam ao ambiente de medição, que também executou verificações desta auditoria. [Interpretação dos resultados de referência](resultados/interpretacao.md)

## Comandos e arquivos de evidência

```powershell
python -m pytest -q
python -m core.academico --semente 42 --pasta instancia/validacao_academica
python -m core.graficos instancia/validacao_academica
python -m tests.verificar_resultados instancia/validacao_academica
python -m tests.verificar_resultados docs/resultados --referencia
```

Com Playwright e Edge instalados, `python -m tests.verificar_navegador instancia/validacao_final/edge-novo` repete a verificação visual. O caminho de saída deve ser novo para registrar um histórico separado. A aplicação também respondeu com HTTP 200 a partir do ambiente virtual novo, via CLI do Flask com `--port 0` e instância isolada.

- `instancia/validacao_final/edge-final/cenario-01/` a `cenario-09/` contêm capturas `maquina.png` e os arquivos locais dos cenários. `cenario-03/` também contém CSV de evidências, CSV de métricas, capturas da ocorrência e do laboratório, os quatro PNGs exportados pelo navegador e o resultado do experimento contextual.
- `instancia/validacao_academica/` contém a primeira rodada acadêmica isolada. `instancia/validacao_final/academica-final/` contém a repetição completa com 17 arquivos validados. `instancia/validacao_final/reteste-busca-hash/` contém o reteste de Busca e Hash em escala completa após o ajuste do contrato de diagnóstico.
- As evidências de navegador cobrem Edge em um computador Windows, com uma checagem de largura de tela móvel. O teste de reenvio demonstra a idempotência do token após uma perda de resposta simulada, no escopo de um único processo Flask. A entrega e as contribuições individuais constam como pendências na auditoria.

## Integridade da instância principal

Foram comparados SHA-256 de 24 arquivos protegidos. A base AI4I, os resultados de referência, os registros da instância principal e seus experimentos mantiveram o hash inicial.

Na primeira tentativa de navegador, dois servidores estavam vinculados à porta 5000. A requisição chegou ao servidor preexistente da instância principal e registrou início, ciclo 49 (UDI 10136) e pausa da M-02 em `instancia/simulacoes.csv`. A tentativa foi interrompida. As execuções seguintes usaram portas efêmeras atribuídas ao servidor de teste e pastas exclusivas. O arquivo principal de simulação é a única divergência de hash detectada. A recuperação exata dependeria dos bytes anteriores, incluindo o identificador do lote substituído. A versão anterior exata não foi localizada e o arquivo não foi regravado com uma reconstrução aproximada.

| Arquivo | SHA-256 antes | SHA-256 depois |
|---|---|---|
| `instancia/simulacoes.csv` | `c32a33753307523c356f4345a21ebda013517dfb84bf93181f8e5ac981806961` | `0b6ad31ed3d3c84d943d76ea87efc3dd7a7391d51b358cb117502f238dc21f91` |

Os manifestos ficam em `instancia/validacao_final/integridade-inicial.json` e `integridade-final.json`. O SHA-256 da base AI4I coincide com o registrado em `docs/academico.md`.
