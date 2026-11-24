# Guia de Apresentação — IndustrialData

## 1. Contextualização e objetivo

- Organização e consulta de registros industriais para investigar alertas e falhas.
- AI4I 2020 como fonte de observações sintéticas para os experimentos. A telemetria das máquinas é gerada pelo simulador da aplicação.
- Em quais condições a economia nas consultas compensa os custos de preparação e manutenção de um índice?

## 2. Arquitetura da solução

- Python e Flask no servidor, com interface web para operação, investigação e análise experimental.
- A arquitetura orientada a objetos separa responsabilidades. `RegistroIndustrial` representa as medições, `RepositorioRegistros` persiste a coleção, `ServicoIndustrial` coordena a operação e `ServicoInvestigacao` seleciona as evidências.
- Os contratos de ordenação e busca permitem trocar estratégias sem alterar o fluxo dos serviços. `ExecutorExperimentos` aplica essas estratégias sob condições controladas. [Diagrama e contratos](academico.md#arquitetura-e-contratos)

## 3. Simulação e gerenciamento de registros

- O torno CNC, a fresadora e a prensa industrial geram leituras de rotação, torque, temperatura e desgaste. Limiares determinam alertas e falhas.
- A investigação associa a ocorrência à máquina, ao ciclo e ao UDI da medição. O UDI permite consultar o registro correspondente.
- A coleção de trabalho permite cadastrar, alterar, remover e exportar registros. As alterações cadastrais preservam o histórico operacional arquivado.

## 4. Algoritmos implementados

- **Insertion Sort, Merge Sort e Heap Sort** ordenam as evidências por medição, com desempate pelo UDI, para identificar valores críticos.
- **Busca sequencial, binária e por interpolação** recuperam registros por UDI. A binária e a interpolação usam uma estrutura ordenada por identificador.
- **Tabela hash própria com encadeamento** atende consultas exatas por UDI e permite observar o efeito das colisões.

## 5. Metodologia experimental

- Entradas de 500, 2.000 e 8.000 registros, com variação da ordem inicial e da distribuição das chaves conforme o ensaio.
- Lotes de 1.000 consultas, metade presentes e metade ausentes. A carga estática executa consultas e a dinâmica intercala 100 mutações.
- Cargas-alvo da hash de 0,25, 0,50 e 0,75. A comparação considera a dispersão das chaves, as colisões e as sondas.
- Tempo, contagem de operações e pico de alocações Python são medidos separadamente. O custo total considera preparação, consultas e manutenção.

## 6. Resultados e conclusões

- O Insertion Sort foi sensível à ordem inicial. O custo de consulta por interpolação aumentou com chaves concentradas. A busca binária apresentou tempos semelhantes nos dois perfis.
- Com 8.000 registros, 1.000 consultas e 100 mutações, a hash apresentou mediana de custo total de 2,66 ms, seguida da binária com 17,82 ms.
- A hash é uma opção para consultas exatas em cargas semelhantes à medida. A binária é uma opção quando se precisa manter a coleção ordenada. A distribuição das chaves, a capacidade da tabela, o ambiente e o custo de persistência podem mudar a escolha. [Resultados de referência](resultados/interpretacao.md)

## 7. Demonstração sugerida

1. Em **Análise de Ocorrências**, execute o cenário demonstrativo da M-01 com a máquina sem lote aberto.
2. Na ocorrência produzida, identifique o equipamento, o ciclo e a medição associada.
3. Consulte o UDI e ordene as evidências por torque ou temperatura.
4. Use **Comparar desempenho** para abrir o recorte no Laboratório de Algoritmos.
5. Apresente as medições de referência e justifique a recomendação técnica para a carga observada.
