# Execução de referência

Medições em Windows build 26200, AMD Ryzen 7 7800X3D, CPython 3.11.0, semente-base 42. A configuração completa está nos CSV. Foram cronometradas 525 repetições em 105 configurações, com uma passagem de memória independente por repetição. As quantidades abaixo são medianas dessa execução, arredondadas para leitura.

| Experimento | Séries de dados | Figura |
| --- | --- | --- |
| Ordenação | [Brutos](ordenacao_brutos.csv) · [Métricas](ordenacao_resumo.csv) | [Crescimento das ordenações](ordenacao.png) |
| Busca | [Brutos](busca_brutos.csv) · [Métricas](busca_resumo.csv) · [Compensação](busca_compensacao.csv) | [Custo das buscas](busca.png) |
| Hash | [Brutos](hash_brutos.csv) · [Métricas](hash_resumo.csv) | [Efeito do fator de carga](hash.png) |
| Sistema | [Brutos](sistema_brutos.csv) · [Métricas](sistema_resumo.csv) | [Custo total com atualizações](sistema.png) |

## Ordenação

Com 8.000 registros, o Insertion Sort passou de **7.999 comparações e 2,21 ms** na entrada ordenada para **31.996.000 comparações e 2.574,62 ms** na inversa. A combinação de prefixo já ordenado e desempate por UDI explica por que a distribuição de repetições no torque ainda teve cerca de 16 milhões de comparações.

Na entrada aleatória de mesmo tamanho, Merge Sort e Heap Sort consumiram aproximadamente **18,94 ms** e **23,25 ms**, respectivamente. A função nativa `sorted`, medida como referência, consumiu **2,51 ms** no mesmo caso. Ela opera na implementação nativa do CPython e explora regularidades dos dados. As contagens de operações são comparáveis entre as três estratégias próprias.

## Busca e compensação

Com 8.000 UDIs regulares, o lote de 1.000 consultas por interpolação gastou cerca de **0,25 ms** após o preparo. Cada consulta sondou uma posição. No mesmo n sob concentração e lacunas, a interpolação gastou **121,78 ms** após o preparo e examinou em média aproximadamente **1.043 posições** por consulta presente. A busca binária gastou cerca de **1,07 ms** de consulta em ambos os perfis, com cerca de **12 sondas** presentes.

Nos UDIs concentrados, o modelo estimou a compensação da busca binária frente à sequencial perto de **121 consultas** e da hash perto de **17**. A grade empírica registrou a primeira vitória em **250** e **50** consultas, respectivamente. A interpolação concentrada apresentou estimativa de **1.348 consultas** e nenhum prefixo observado até 1.000 com vantagem sobre a sequencial. No perfil regular, a interpolação venceu pela primeira vez no prefixo de 250. Os limites refletem a grade e a variação do relógio.

## Efeito do fator de carga

A mesma base de 8.000 chaves concentradas produziu o seguinte diagnóstico:

| Carga-alvo | Capacidade | Colisões | Maior balde | Passos presentes | Passos ausentes |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 0,25 | 32.000 | 3.086 | 40 | 2,214 | 0,224 |
| 0,50 | 16.000 | 3.681 | 41 | 3,332 | 0,476 |
| 0,75 | 10.667 | 1.530 | 2 | 1,182 | 0,652 |

A capacidade de 10.667 reduziu a concentração dos resíduos dessas chaves e obteve a menor mediana de custo total neste n. As capacidades pares deixam os baldes ímpares livres para este perfil de chaves presentes pares. Por isso, consultas ausentes em chaves de paridades diferentes afetam a média, e o fator de carga precisa ser interpretado junto com a dispersão.

## Atualizações

Medianas do tempo total em milissegundos, com 8.000 registros, 1.000 consultas e 100 mutações na carga dinâmica:

| Estratégia | Estática | Dinâmica | Mediana das atualizações na dinâmica |
| --- | ---: | ---: | ---: |
| Sequencial | 135,65 | 142,76 | 7,74 |
| Binária | 17,24 | 17,82 | 0,13 |
| Interpolação | 138,61 | 139,45 | 0,17 |
| Hash | 2,59 | 2,66 | 0,04 |

A busca sequencial examinou mais de 5,9 milhões de posições nos dois roteiros e ainda precisou localizar chaves de edição e remoção na versão dinâmica. A busca binária localizou as mutações por dicotomia e pagou os deslocamentos do vetor. A tabela hash manteve o menor tempo total neste desenho, com manutenção restrita aos baldes. Os dados sustentam o uso de hash para consultas exatas com perfis semelhantes e da binária quando uma coleção ordenada ou comportamento estável em chaves irregulares é importante. Para extrapolar a bases reais, é necessário medir a distribuição de resíduos e o custo de I/O da persistência.

As figuras de tempo usam faixas centradas na mediana com largura do IIQ, quando visível. As medições brutas estão disponíveis para calcular intervalos com os quartis exatos.

