# MSX BASIC Pre-Processor

![Python](https://img.shields.io/badge/Python-3.8%2B-blue) ![License](https://img.shields.io/badge/License-GPL-green) ![Platform](https://img.shields.io/badge/Platform-MSX-red)

> English version: [README_EN.md](README_EN.md)

Pré-processador de linha de comando para programas escritos em MSX BASIC. Recebe um arquivo fonte `.bas` com sintaxe estendida e gera um arquivo BASIC puro com numeração de linhas, pronto para ser carregado no MSX ou em um emulador.

---

## Índice

- [Visão geral](#visão-geral)
- [Instalação](#instalação)
- [Uso](#uso)
- [Funcionalidades](#funcionalidades)
  - [Numeração automática de linhas](#numeração-automática-de-linhas)
  - [Labels](#labels)
  - [Macros com #DEFINE](#macros-com-define)
  - [Includes com #INCLUDE](#includes-com-include)
  - [Recursos com #RESOURCE](#recursos-com-resource)
- [Tabela de diretivas](#tabela-de-diretivas)
- [Exemplos](#exemplos)
- [Fluxo de processamento](#fluxo-de-processamento)
- [Limitações conhecidas](#limitações-conhecidas)
- [Como contribuir](#como-contribuir)

---

## Visão geral

O MSX foi um padrão de microcomputadores pessoais muito popular nos anos 80. Sua linguagem de programação nativa, o MSX BASIC, exige que cada linha de código seja numerada manualmente — uma limitação que torna a manutenção de programas maiores bastante trabalhosa.

O **MSX BASIC Pre-Processor** (`msxbasic_pp.py`) resolve esse problema ao introduzir uma camada de pré-processamento: o programador escreve o código sem se preocupar com números de linha, usa labels simbólicos para desvios, define macros reutilizáveis e organiza o projeto em múltiplos arquivos. O pré-processador cuida de traduzir tudo isso para o BASIC puro que o MSX espera.

Também há diretivas para facilitar o uso de recursos no MSXBAS2ROM, usando nomes de recursos ao inves de números.

---

## Instalação

Não há dependências externas. Basta copiar o arquivo para o diretório do projeto (ou para qualquer diretório no PATH do sistema) e garantir que o Python 3.8 ou superior esteja instalado.

```bash
# Verificar versão do Python
python --version

# Copiar o script para o diretório do projeto
cp msxbasic_pp.py /seu/projeto/
```

---

## Uso

```
python msxbasic_pp.py entrada.bas [-o saida.bas] [--start N] [--step N] [--verbose]
```

| Argumento     | Descrição                                              | Padrão              |
|---------------|--------------------------------------------------------|---------------------|
| `entrada.bas` | Arquivo fonte com sintaxe estendida                    | (obrigatório)       |
| `-o saida.bas`| Arquivo de saída                                       | `<entrada>_out.bas` |
| `--start N`   | Número da primeira linha gerada                        | `10`                |
| `--step N`    | Incremento entre linhas consecutivas                   | `10`                |
| `--verbose`   | Exibe mapa de labels, tabela de recursos e o programa gerado | desativado    |

**Exemplos de invocação:**

```bash
# Saída padrão (gera jogo_out.bas)
python msxbasic_pp.py jogo.bas

# Saída explícita, linhas de 5 em 5, modo verbose
python msxbasic_pp.py jogo.bas -o jogo_final.bas --step 5 --verbose

# Numeração começando em 100
python msxbasic_pp.py jogo.bas --start 100 --step 10
```

---

## Funcionalidades

### Numeração automática de linhas

Todas as linhas de código do arquivo fonte são numeradas automaticamente na saída. O número inicial e o incremento são configuráveis via `--start` e `--step`.

Linhas de declaração de recursos (`FILE`, `TEXT`) são movidas para o topo do programa **sem número de linha**, conforme exigido pelo MSXBAS2ROM.

**Fonte:**
```basic
FILE "level1.bin"
FILE "sounds.bin"

SCREEN 5,2
COLOR 15,0,0
```

**Saída:**
```basic
FILE "level1.bin"
FILE "sounds.bin"
10 SCREEN 5,2
20 COLOR 15,0,0
```

---

### Labels

Qualquer linha pode iniciar com `:NOME` para definir um label. Labels servem como marcadores simbólicos que substituem números de linha nos comandos de desvio.

**Definição:**

```basic
:LOOP
  A = A + 1
  IF A > 10 THEN GOTO :FIM
  GOTO :LOOP
:FIM
  PRINT A
```

**Regras:**

- Um label pode estar sozinho em uma linha ou seguido de código na mesma linha.
- Labels sozinhos são **fundidos** com a linha de código imediatamente seguinte, sem consumir um número de linha extra.
- Múltiplos labels podem apontar para a mesma linha.
- Referências a labels são resolvidas automaticamente nos comandos de desvio.

**Comandos de desvio suportados:**

| Sintaxe no fonte           | Exemplo gerado       |
|----------------------------|----------------------|
| `GOTO :LABEL`              | `GOTO 100`           |
| `GOSUB :LABEL`             | `GOSUB 200`          |
| `THEN :LABEL`              | `THEN 300`           |
| `ELSE :LABEL`              | `ELSE 400`           |

**Fonte:**
```basic
:LOOP
  PRINT "Contando..."
  C = C + 1
  IF C < 10 THEN GOTO :LOOP
PRINT "Fim"
```

**Saída:**
```
10 PRINT "Contando..."
20 C = C + 1
30 IF C < 10 THEN GOTO 10
40 PRINT "Fim"
```

---

### Macros com #DEFINE

O pré-processador suporta dois tipos de macros, inspirados na sintaxe do pré-processador C.

#### Macros simples

```basic
#DEFINE NOME valor
```

Substitui todas as ocorrências da palavra `NOME` pelo valor definido. A substituição respeita limites de palavra — `NOME` não é substituído dentro de identificadores maiores.

```basic
#DEFINE LARGURA 256
#DEFINE ALTURA  192

PRINT LARGURA, ALTURA
```

**Saída:**
```
10 PRINT 256, 192
```

#### Macros parametrizadas

```basic
#DEFINE NOME(param1, param2) corpo
```

Funcionam como macros de função da linguagem C, com substituição dos parâmetros no corpo.

```basic
#DEFINE LOG(m) PRINT "LOG:";m

LOG("Iniciando o programa")
LOG("Valor Aleatório:";RND(0))
```

**Saída:**
```
10 PRINT "LOG:";"Iniciando o programa"
20 PRINT "LOG:";"Valor Aleatório";RND(0)
```

A expansão é recursiva até 20 níveis, permitindo macros que referenciam outras macros.

---

### Includes com #INCLUDE

```basic
#INCLUDE "caminho/para/arquivo.bas"
```

Inclui o conteúdo de outro arquivo no ponto da diretiva, antes do processamento. O caminho é resolvido relativamente ao arquivo que contém o `#INCLUDE`.

- Inclusão recursiva é suportada: um arquivo incluído pode incluir outros.
- O pré-processador detecta inclusões circulares e reporta erro, evitando loops infinitos.

**Exemplo de organização de projeto:**

```
jogo.bas
rotinas/
  espera.bas
  musica.bas
```

```basic
' jogo.bas
#INCLUDE "rotinas/espera.bas"
#INCLUDE "rotinas/musica.bas"

:INICIO
  GOSUB :TOCA_MUSICA
  GOSUB :ESPERA_TECLA
  GOTO :INICIO
```

---

### Recursos com #RESOURCE (MSXBAS2ROM)

```basic
#RESOURCE($NOME, TIPO, nome_do_arquivo)
```

Registra um arquivo de recurso externo e associa a ele um índice ordinal (baseado em 1). Esse índice substitui `$NOME` em qualquer ponto do código-fonte, evitando o uso de números mágicos.

**Tipos suportados que geram declaração no header:**

| Tipo    | Declaração gerada no header |
|---------|-----------------------------|
| `FILE`  | `FILE "arquivo"`            |
| `TEXT`  | `TEXT "arquivo"`            |
| `CODE`  | `CODE "arquivo"`            |
| `BSAVE` | `BSAVE "arquivo"`           |
| `CSAVE` | `CSAVE "arquivo"`           |

**Fonte:**
```basic
#RESOURCE($MAPA, FILE, level1.bin)
#RESOURCE($SONS, FILE, sounds.bin)
#RESOURCE($SPRITES, FILE, sprites.bin)

CMD PLYLOAD $MAPA, $SONS
CMD SPRLOAD $SPRITES
```

**Saída:**
```
FILE "level1.bin"
FILE "sounds.bin"
FILE "sprites.bin"
10 CMD PLYLOAD 1, 2
20 CMD SPRLOAD 3
```

Comentários inline nas declarações `FILE`/`TEXT` são removidos automaticamente. Uma declaração `FILE "arquivo" ' comentário` no corpo do código também é movida para o header sem número de linha.

---

## Tabela de diretivas

| Diretiva                              | Descrição                                                  |
|---------------------------------------|------------------------------------------------------------|
| `#DEFINE NOME valor`                  | Define uma macro de substituição simples                   |
| `#DEFINE NOME(p1, p2) corpo`          | Define uma macro parametrizada                             |
| `#INCLUDE "arquivo.bas"`              | Inclui o conteúdo de outro arquivo no ponto da diretiva    |
| `#RESOURCE($VAR, TIPO, arquivo)`      | Registra um recurso e associa um índice ordinal a `$VAR`   |
| `:LABEL`                              | Define um label para uso em comandos de desvio             |
| `FILE "arquivo"` (no corpo do código) | Movido para o header sem número de linha                   |
| `TEXT "arquivo"` (no corpo do código) | Movido para o header sem número de linha                   |

---

## Exemplos

### Programa completo com labels e macros

**Fonte (`contador.bas`):**
```basic
#DEFINE MAX 10

SCREEN 0
:LOOP
  PRINT C
  C = C + 1
  IF C >= MAX THEN GOTO :FIM
  GOTO :LOOP
:FIM
  PRINT "Fim!"
  END
```

**Saída (`contador_out.bas`):**
```
10 SCREEN 0
20 PRINT C
30 C = C + 1
40 IF C >= 10 THEN GOTO 70
50 GOTO 20
60 PRINT "Fim!"
70 END
```

---

### Projeto com recursos e includes

**Fonte (`jogo.bas`):**
```basic
#RESOURCE($MAPA, FILE, level1.bin)
#RESOURCE($SONS, FILE, sounds.bin)
#INCLUDE "rotinas.bas"

:INICIO
  CMD PLYLOAD $MAPA, $SONS
  GOSUB :INICIALIZA
  GOTO :INICIO
```

**Saída (`jogo_out.bas`):**
```
FILE "level1.bin"
FILE "sounds.bin"
10 ' (conteúdo de rotinas.bas)
...
N  CMD PLYLOAD 1, 2
N  GOSUB <linha de INICIALIZA>
N  GOTO 10
```

---

## Fluxo de processamento

O pré-processador executa as seguintes etapas em ordem:

1. **Leitura e expansão de includes** — o arquivo principal e todos os `#INCLUDE` são lidos recursivamente, com detecção de ciclos.
2. **Coleta de `#DEFINE`** — a tabela de macros é construída a partir das diretivas encontradas.
3. **Coleta de `#RESOURCE`** — a tabela de recursos é construída e os índices ordinais são atribuídos.
4. **Primeira passagem** — separação entre header e corpo; detecção de labels; remoção de comentários inline em declarações de recursos; expansão de macros e substituição de variáveis de recurso.
5. **Fusão de labels puros** — labels que aparecem sozinhos em uma linha são fundidos com a linha de código seguinte.
6. **Numeração automática** — as linhas do corpo recebem números sequenciais.
7. **Segunda passagem** — referências a labels (`GOTO :X`, `GOSUB :X`, etc.) são substituídas pelos números de linha correspondentes.
8. **Geração da saída** — header (sem numeração) seguido do corpo numerado é gravado no arquivo de saída.

---

## Limitações conhecidas

- **Macros parametrizadas com vírgulas em strings:** o parser de argumentos de macros divide os parâmetros por vírgula sem considerar strings entre aspas. Uma chamada como `MACRO("a,b", c)` será interpretada incorretamente, tratando `"a` e `b"` como argumentos separados.
- **Sem validação de sintaxe BASIC:** o pré-processador não verifica se o código gerado é BASIC válido. Erros de sintaxe só serão detectados ao carregar o programa no MSX ou emulador.
- **Labels devem ser únicos:** definir o mesmo label mais de uma vez resulta em erro de pré-processamento. O pré-processador detecta a duplicata e aborta com mensagem de erro.
- **Macros não são higienicas:** a expansão de macros parametrizadas é puramente textual, sem isolamento de escopo. Conflitos de nomes entre parâmetros e variáveis do programa devem ser gerenciados pelo programador.

---

## Como contribuir

Contribuições são bem-vindas. Para colaborar:

1. Faça um fork do repositório.
2. Crie uma branch para a sua alteração (`git checkout -b minha-feature`).
3. Escreva testes para o comportamento novo ou corrigido, quando aplicável.
4. Abra um pull request descrevendo o que foi alterado e a motivação.

Ao reportar um bug, inclua o arquivo fonte `.bas` que reproduz o problema e a saída (ou erro) obtida.
