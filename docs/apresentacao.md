# Demonstração do IndustrialData em 12 minutos

| Tempo | O que demonstrar | Evidência a citar |
| --- | --- | --- |
| 0:00–1:30 | Apresente o problema. Um analista precisa localizar medições de uma ocorrência e decidir como indexar o histórico. | AI4I 2020 é sintética e serve aos ensaios controlados. M-01, M-02 e M-03 produzem telemetria simulada própria. |
| 1:30–3:00 | Em **Visão Geral**, inicie M-02 e M-03. Pause uma delas e mostre o avanço da outra. | Sensores, progresso, CSV e estados independentes. |
| 3:00–5:00 | Abra **Análise de Ocorrências** e execute o cenário demonstrativo. Examine a falha da M-01 e o UDI associado. | Semente 42, desgaste inicial zero, incremento de 8 min por ciclo e limite de 96 min. O 12º ciclo do cenário dispara a falha da regra simulada. |
| 5:00–7:30 | Ordene por temperatura ou torque com as três estratégias. Busque o UDI pelas quatro opções. Consulte-o duas vezes pela hash. | Mesma ordenação com desempate por UDI. Mesmo registro nas quatro buscas. Tempos de preparo, consulta, passos e reutilização do índice. |
| 7:30–10:30 | Em **Comparar desempenho**, confirme o recorte trazido ao laboratório. Mostre a cópia de demonstração da hash e alterne para o modo acadêmico com origem controlada. Percorra as quatro abas. | Crescimento das ordenações, custo das buscas, efeito de carga e custo total estático/dinâmico. Explique mediana, dispersão, memória e a reconstrução isolada. |
| 10:30–12:00 | Apresente uma recomendação condicionada à carga, extraída do resultado que está na tela. Mostre o CSV de evidências ou o gráfico PNG. | Ponto de compensação quando observado, perfil das chaves, memória e limitações do relógio local. |

## Preparação

- Inicie o Flask e abra a Visão Geral. Deixe a M-01 sem lote ativo ou pausado antes do cenário.
- A rodada acadêmica completa pode levar minutos. Use os gráficos e CSV já medidos em [Resultados](resultados/interpretacao.md) e execute uma configuração curta ao vivo se houver tempo.
- A demonstração grava ciclos de verdade na M-01 e preserva a configuração escolhida para o próximo lote. Use **Reiniciar** em Máquinas depois de mostrar a falha.
- A conclusão operacional descreve as condições observadas segundo as regras do simulador. A conclusão computacional usa a medição da entrada exibida. Um valor extremo ou concomitante não estabelece causa física em uma operação real.

