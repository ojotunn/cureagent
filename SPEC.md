# EHRLICH — SPEC congelada

**Ticker:** EHRLICH · **Dominio:** ehrlich.bio · **Rede:** Robinhood Chain (pons v2) · **Porta local:** 8440
**Data:** 13/09/2026 · **Estado:** FATIA 1 RODADA — alvo reprovado, ver seção 0

---

## 0. RESULTADO DA FATIA 1 (14/09/2026) — a cruzaína não passou

Custo: zero de GPU, zero de RunPod, zero de token. Só CPU local.

**O pipeline está correto — provado por controle positivo:**

| Sistema | Torsões | Pose 1 | Veredicto |
|---|---|---|---|
| 1STP / biotina + estreptavidina | 5 | **0,77 Å** | PASSOU |
| 1HVR / HIV protease (46 átomos) | 8 | **0,47 Å** | PASSOU |

**A cruzaína falhou em todos os 7 ligantes cristalográficos testados:**

| Cristal / ligante | Torsões | Pose 1 | Melhor das 9 |
|---|---|---|---|
| 4W5C / 3H7 | 0 | 2,65 Å | 2,65 Å |
| 4W5B / 3H5 | 2 | 7,56 Å | 2,22 Å |
| 4W5C / 3H6 | 3 | 8,37 Å | 1,67 Å |
| 4KLB / 1RV | 5 | 3,67 Å | 3,67 Å |
| 3KKU / B95 | 6 | (receptor com resíduo incompleto) | — |
| 1U9Q / 186 | 10 | 9,76 Å | 4,82 Å |
| 1ME3 / P10 | 14 | 7,59 Å | 6,26 Å |
| 1ME4 / T10 | 13 | 8,27 Å | 5,57 Å |

Um ligante de **zero torsões** falhando a 2,65 Å, num pipeline que acerta 0,47 Å
no controle, é propriedade do alvo: a fenda da cruzaína é rasa e aberta (típico
de protease de cisteína) e a função de score do Vina não reconhece as poses
cristalográficas ali. Confirmado por `score_only`: a pose do cristal do 1ME3
marca **−2,4 kcal/mol** enquanto poses erradas marcam **−6,9**.

**Enriquecimento (o teste que de fato importa para triagem):**
49 ativos medidos (ChEMBL) contra 590 decoys pareados por propriedade, receptor
1AIM, exhaustiveness 8 (ajuste de produção), 639 dockings, 61 min em 16 núcleos.

    AUC-ROC : 0,638     (corte definido ANTES de rodar: >= 0,70)
    EF 1%   : 4,3x      (apenas 2 ativos em 6 posições — n frágil)
    EF 5%   : 1,6x
    EF 10%  : 1,8x
    Nos 10 melhores scores: 2 ativos, 8 decoys

**Reprovado pelo critério que eu mesmo fixei antes de ver o número.**

**Ressalvas honestas deste teste (podem ter sido duras demais):**
1. Os decoys vieram do ChEMBL, que é uma base de compostos BIOATIVOS — vários
   são inibidores de outras proteases. Decoys presumidamente inertes (estilo
   DUD-E, tirados do ZINC) dariam um teste mais justo.
2. n = 49 ativos é pequeno.
3. Só uma estrutura receptora (1AIM) e um único exhaustiveness foram testados.

**Decisão pendente do Michel** (ver seção 10.1).

## 1. O que é, em uma linha

Um token cujas taxas viram hora de placa de vídeo triando milhões de moléculas
contra a **cruzaína** — alvo validado da doença de Chagas — com os resultados
publicados abertos e o nome de quem financiou cada lote gravado no dado.

## 2. A regra de honestidade (não negociável)

O site, os posts e qualquer texto do projeto **nunca** usam: *cura, remédio,
tratamento, descoberta, breakthrough*.

O lema, afirmativo e institucional: **"Open computational screening for neglected diseases. Every run published."**

Dizer "nao prometemos nada" repetidamente e DEFENSIVO e custa
credibilidade — quem se defende antes de ser acusado parece ter o que
esconder. A honestidade vive nos DADOS (falhas publicadas, estimativa
marcada como estimativa), nao em declaracao.

O roadmap descreve o que o projeto **vai gastar**, nunca o que o comprador vai
ganhar. Proibida qualquer frase do tipo "quando bater X, o token vale Y".

Motivo: sem promessa, não há nada a cobrar de nós. A prestação de contas é o
ativo principal do projeto — vale mais que a narrativa.

## 3. Economia

| Item | Valor | Fonte |
|---|---|---|
| Taxa de lançamento | 0,0005 ETH (~$1,25) | lida da chain |
| Supply | 1.000.000.000 (fixo) | pons |
| Taxa do criador | **5%** em cada negociação da curva | escolhida; teto da pons é 10% |
| Graduação | 4,2 ETH arrecadados | pons |
| Dev buy | **0 no lançamento** | capital em risco só depois da resposta do mercado |
| Taxa da curva (pons) | 1% | não é nossa |

**Ordem de pagamento do agente, sempre nesta sequência:**

1. Reserva de gás
2. Reserva de 7 dias de placa (o projeto não pode morrer por falta de caixa)
3. **Cofre do roadmap** — 50% do excedente, vinculado à fase atual
4. **Criador** — 50% do excedente

Os dois últimos aparecem no site com valor acumulado. Nada de airdrop, prêmio,
sorteio ou distribuição a holders — decisão do Michel.

**A carteira do agente é NOSSA**, não a do claudeploy. O creatorFeeRecipient
aponta para ela. Não usamos attach_agent: aquele agente sabe fazer buyback e
airdrop, não sabe fazer docking.

**Travas da carteira** (padrão Yuna): não transfere para endereço arbitrário, só
para os dois destinos fixos (cofre e criador). Teto diário de gasto com Claude
configurável, com corte automático.

## 4. O alvo científico

- **Proteína:** cruzaína (cisteíno-protease de *Trypanosoma cruzi*), alvo
  validado para Chagas, com inibidores reais já obtidos por triagem virtual.
- **Estrutura primária: PDB 1AIM.** Escolhida porque a literatura mostra que o
  docking encontra hits com o Glu208 rotacionado para o bolso S2 (conformação do
  1AIM) e **não encontra nada no 1ME3**, onde o Glu208 aponta para o solvente.
  Essa escolha não é estética — é a diferença entre achar e não achar.
- **Validação do protocolo: PDB 1ME3 e 1ME4** (1,20 Å, ligantes P10 e T10,
  **não-covalentes** — verificado: nenhum registro LINK). O redocking tem que
  reproduzir a pose cristalográfica (critério: RMSD <= 2,0 A) antes de a triagem
  valer qualquer coisa.
  **CORREÇÃO 14/09/2026:** a versão anterior desta spec mandava validar por
  redocking do K777 no 2OZ2. Está errado e foi verificado no próprio arquivo:
  `LINK SG CYS A 25 - C27 D1R 1,65 A` — o K777 está **ligado covalentemente** à
  Cys25, e o 1AIM também (`LINK SG CYS A 25 - CM ZYA 1,81 A`, fluorometil
  cetona). Docking não-covalente não reproduz essas poses; o redocking falharia
  e a conclusão errada seria "o protocolo é ruim". Complexos covalentes servem
  como referência do sítio, nunca como teste de validação.
- **Teste que realmente importa — cross-docking:** docar P10 e T10 no receptor de
  triagem (1AIM, sem o ligante covalente). Redocking no próprio cristal é
  auto-consistente e fácil; reproduzir a pose num receptor diferente é o que
  prova que o 1AIM serve como alvo prospectivo.
- **Cys25:** o estado de protonação da cisteína catalítica muda o resultado.
  Decisão de preparação documentada e justificada no repo, não escolhida no
  escuro.
- **Biblioteca:** ZINC-22 (compostos tangíveis, compráveis de verdade — é isso
  que torna o resultado utilizável por um laboratório).

## 5. Pipeline

- **Motor:** Vina-GPU 2.1 (200–400x sobre o Vina de CPU, conforme publicado).
- **Placa:** RTX 4090 na RunPod, **$0,34/h**, cobrada por segundo.
- **Lote por compra:** cada compra dispara um lote de moléculas com o endereço do
  comprador atrelado. Estimativa derivada: ~0,1–0,3 s por molécula, então um lote
  de ~1.800 moléculas leva ~6 minutos de placa. O comprador vê o lote dele nascer
  e terminar.
- **Fila:** compras simultâneas entram numa fila; se ela crescer, o orquestrador
  sobe pods adicionais (cobrança por segundo permite) e desliga quando vazia.
  **Sem compra = sem placa ligada = sem custo.**
- **Resultados:** score por composto, pose, ID ZINC, lote, financiador,
  timestamp. Publicados abertos. **Nunca redistribuímos a biblioteca** — só os
  resultados (o ZINC exige permissão escrita para redistribuir subconjuntos
  grandes; resultado de docking não é subconjunto da biblioteca).
- **Determinismo:** seed fixa por lote, para qualquer pessoa poder reproduzir.

## 6. A tela (em inglês, sempre)

- Cruzaína em 3D girando no centro, translúcida, sítio ativo aceso.
- A molécula da vez encaixando, ao vivo.
- **Placar dos melhores encaixes**, com o endereço de quem financiou cada um.
- **Barra contra o recorde publicado:** o maior screening publicado nesse alvo
  triou ~4 milhões de compostos. A barra mostra nós contra esse número.
- Roadmap com custo real e estado de cada fase.
- Recibos: quanto entrou, quanto foi gasto, em quê, com hora.

## 7. Roadmap (é o site, não é enfeite)

| Fase | Entrega | Custo | Quem paga |
|---|---|---|---|
| 0 | Triagem-semente, 250k moléculas | ~$2–7 | criador |
| 1 | 1 milhão de moléculas triadas | ~$10–50 | fees |
| 2 | **Superar o recorde publicado (4M)** | ~$30–120 | fees |
| 3 | Comprar as 20 melhores (Enamine, ~3 semanas) | ~$1.000–3.000 | fees |
| 4 | Ensaio na enzima isolada, laboratório real | ~$2.000–8.000 | fees |
| 5 | Ensaio em célula infectada + citotoxicidade | ~$5.000–15.000 | fees |
| 6+ | Química medicinal, animal, humanos | — | **não é nosso** — DNDi / academia |

Chegar à bancada (fase 4) custa da ordem de **$3k a $11k**. Com taxa de 5%, isso
é volume acumulado na casa de $60k–220k.

Quando uma fase é paga, isso é um **evento**: post, hora exata, quantos
financiadores. Não é uma página parada.

## 8. Números: medido vs derivado

| Número | Estado |
|---|---|
| Taxa de lançamento, supply, graduação, taxa máxima | **confirmado na chain** |
| Preço da 4090 na RunPod ($0,34/h) | **confirmado** |
| Speedup do Vina-GPU (200–400x) | **publicado** |
| PDB 1AIM / 2OZ2, papel do Glu208 | **publicado** |
| Moléculas por hora no nosso alvo | **DERIVADO — medir na 1a hora de placa** |
| Custo por molécula | **DERIVADO — sai da medição acima** |
| Preço do composto na Enamine | **NÃO CONFIRMADO — contato direto** |
| Preço do ensaio no laboratório | **NÃO CONFIRMADO — conversa com lab** |

Nada marcado como DERIVADO ou NÃO CONFIRMADO vai para o site como preço fechado.
Publicar estimativa como se fosse preço mata a prestação de contas, que é o ativo
do projeto.

## 9. Ordem de execução

1. **Construir** pipeline + tela + agente.
2. **Medir** na placa: throughput real, custo real por molécula.
3. **Rodar a semente** — a tela enche com dado real, não com placeholder.
4. **Publicar o site** e mostrar no X. Sem token, sem ticker, sem nada à venda.
5. **Ler a reação.** Só então lançar o KEYS — com a tela já cheia.

O lançamento é a ÚLTIMA coisa. Se o passo 4 não colar, não existe token morto com
o nome do Michel, e o pipeline continua servindo para qualquer outro alvo.

## 9.1 Política de pagamento: nada adiantado

Decisão do Michel: **nenhum custo é pré-pago em volume.** Se o token morrer, não
pode haver dinheiro parado gasto à frente.

| Custo | Como é pago |
|---|---|
| Placa (RunPod) | por segundo, consumindo crédito em bloco pequeno (~$10) |
| Claude do agente | por uso; agente parado não gasta |
| Railway | plano que o Michel já paga; projeto novo é marginal |
| Domínio próprio | **NÃO COMPRAR** — subdomínio grátis do Railway até o token provar que vive |
| Compostos (fase 3) | só com o cofre do roadmap cheio; o dinheiro entra antes |
| Ensaio de laboratório (fases 4–5) | idem |
| Reserva de 7 dias de placa | formada com fee, não com o bolso; começa vazia e isso é ok |

**Construção é o único custo verdadeiramente adiantado**, e por isso vai fatiada,
com ponto de desistência entre as fatias:

- **Fatia 1 — frente A** (preparação do alvo + validação do protocolo). Roda na
  máquina do Michel, sem RunPod. Custo ~$20–40. **Pergunta que ela responde:** o
  redocking do K777 no 2OZ2 reproduz a pose cristalográfica? Se não, o projeto
  morre aqui, barato, antes de qualquer tela.
- **Fatia 2 — frentes B, D, E** (pipeline na GPU + medição + semente + tela).
  Custo ~$50–150. **Entrega:** tela cheia com dado real e o custo por molécula
  MEDIDO. Publica e mostra no X, sem token.
- **Fatia 3 — frentes C, F, G** (agente + integração pons + lançamento). Custo
  ~$40–100. **Só se a fatia 2 gerar reação.**

## 10. Bloqueios conhecidos

1. **RunPod não autorizado.** O plugin está instalado, o OAuth não foi feito, e
   sessão não-interativa não abre esse fluxo. Sem isso não há medição. É o
   bloqueio numero 1.
2. **Como o agente paga a RunPod.** As fees chegam em ETH na Robinhood Chain; a
   RunPod cobra em cartão/crédito. Até confirmarmos se ela aceita cripto, o
   pagamento é **manual** (Michel converte e credita) e o site diz isso na cara.
   Não inventar automação que não existe.
3. **Licença ZINC.** Uso é livre; redistribuir subconjunto grande exige permissão
   escrita. Nosso plano publica resultados, não a biblioteca — ler os termos na
   fonte e registrar a leitura antes da primeira linha de código. (Lição do
   FlyWire: licença conferida no fim custa o projeto inteiro.)
4. **Laboratório parceiro.** Fases 4–5 dependem de um laboratório real. Alvo
   natural: **Open Chagas / DNDi** (plataforma aberta, workshop em São Paulo e
   Campinas em 2026) e grupos brasileiros de cruzaína. Molde comprovado: Malaria
   Box / Pathogen Box — manda-se o composto de graça, com o ensaio pago. **Nunca
   anunciar parceria antes de ela existir.**

## 10.1 O que fazer depois do resultado da fatia 1

Três caminhos, todos ainda em CPU local e custo de GPU zero:

- **A — refazer o teste com decoys justos.** Decoys do ZINC pareados por
  propriedade (presumidamente inertes) no lugar dos do ChEMBL. É a única forma
  honesta de saber se o 0,638 foi o alvo ou o teste. ~1-2 h de CPU.
- **B — trocar de alvo dentro de Chagas.** TcCYP51 (esterol 14-alfa-desmetilase)
  tem sítio profundo e fechado com heme, é o alvo dos azóis, tem cristais e
  ativos de sobra — o perfil oposto ao da cruzaína e historicamente bem
  comportado em docking. O pipeline já está pronto e validado: trocar de alvo é
  trocar arquivo. ~2 h de CPU.
- **C — parar.** A fatia 1 existe exatamente para isso. Custou o
  desenvolvimento e nada mais; o pipeline fica reaproveitável para qualquer
  alvo futuro.

Recomendação: **A e B juntos**, porque rodam na mesma noite de CPU e decidem o
alvo do projeto de vez. Só depois disso se fala em fatia 2.

## 11. Fora do escopo

- Airdrop, prêmio, sorteio, buyback, qualquer distribuição a holders.
- Carteira que transfere para endereço arbitrário.
- Qualquer afirmação sobre eficácia em humanos.
- Fases 6+ (química medicinal, animal, clínico).

## 12. Pior caso, com número

| Item | Custo |
|---|---|
| Lançamento (taxa + gás) | ~$2 |
| Railway, 3 dias | $0–5 |
| Semente na placa | $2–7 |
| Claude do agente, 3 dias | $3–9 |
| Placa depois da semente, sem compras | **$0** |
| **Operação total** | **~$10–25** |
| Construção (2–4 dias de Claude Code) | **$100–350** |

Token morto não sangra: placa só liga com compra. O risco real é o custo de
construir, e ele é gasto antes de existir token — por escolha, no item 9.

## 13. Frentes de trabalho

- **A** — preparação do alvo (1AIM, Cys25, validação por redocking do K777 em 2OZ2)
- **B** — pipeline Vina-GPU na RunPod + medição de throughput
- **C** — orquestrador de fila: compra → lote → resultado → crédito
- **D** — banco de resultados + publicação aberta (formato reprodutível)
- **E** — tela ao vivo (3D, placar, barra do recorde, roadmap, recibos)
- **F** — agente: contabilidade, recibos, posts, travas de carteira
- **G** — integração pons: leitura de compras, carteira do agente, lançamento
