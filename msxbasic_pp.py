#!/usr/bin/env python3
"""
MSX BASIC Pre-Processor
=======================
Funcionalidades:
  - Numeração automática de linhas (exceto linhas de declaração de recursos)
  - Labels começados com ':' (ex: :LOOP), resolvidos em GOTOs/GOSUBs
  - Macros via #DEFINE nome valor  e  #DEFINE nome(args) corpo
  - Includes via #INCLUDE "arquivo"
  - Recursos via #RESOURCE($nome, TIPO, arquivo)
    -> ao usar $nome no código, substitui pelo índice ordinal do recurso (1-based)

Uso:
  python msxbasic_pp.py entrada.bas [-o saida.bas] [--start 10] [--step 10]
"""

import re
import sys
import os
import argparse
from copy import deepcopy


# ─────────────────────────────────────────────────────────────────────────────
# Tipos de recurso que geram declarações no topo do programa (sem número de linha)
# ─────────────────────────────────────────────────────────────────────────────
RESOURCE_HEADER_TYPES = {"FILE", "TEXT", "CODE", "BSAVE", "CSAVE"}


# ─────────────────────────────────────────────────────────────────────────────
# Utilitários
# ─────────────────────────────────────────────────────────────────────────────

def is_blank_or_comment(line: str) -> bool:
    """Linha vazia ou comentário puro (começa com ')."""
    s = line.strip()
    return s == "" or s.startswith("'")


def strip_inline_comment(line: str):
    """Remove comentário de fim de linha, respeitando strings. Retorna (codigo, comentario)."""
    in_str = False
    for i, ch in enumerate(line):
        if ch == '"':
            in_str = not in_str
        if not in_str and ch == "'":
            return line[:i].rstrip(), line[i:]
    return line.rstrip(), ""


# ─────────────────────────────────────────────────────────────────────────────
# Fase 1 – Leitura e expansão de #INCLUDE (recursiva)
# ─────────────────────────────────────────────────────────────────────────────

def read_with_includes(filepath: str, visited: set = None) -> list:
    """Lê arquivo e expande #INCLUDE recursivamente. Retorna lista de (linha, arquivo_origem)."""
    if visited is None:
        visited = set()

    real = os.path.realpath(filepath)
    if real in visited:
        raise RecursionError(f"Include circular detectado: {filepath}")
    visited.add(real)

    base_dir = os.path.dirname(filepath)
    result = []

    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        for raw in f:
            line = raw.rstrip("\n\r")
            m = re.match(r'^\s*#INCLUDE\s+"([^"]+)"\s*$', line, re.IGNORECASE)
            if m:
                inc_path = os.path.join(base_dir, m.group(1))
                result.extend(read_with_includes(inc_path, visited))
            else:
                result.append((line, filepath))

    visited.discard(real)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Fase 2 – Coleta de #DEFINE (macros simples e parametrizadas)
# ─────────────────────────────────────────────────────────────────────────────

class MacroTable:
    def __init__(self):
        self.simple: dict[str, str] = {}          # nome -> valor
        self.func: dict[str, tuple] = {}           # nome -> (params, corpo)

    def add(self, line: str) -> bool:
        """Processa linha #DEFINE. Retorna True se era diretiva."""
        m = re.match(
            r'^\s*#DEFINE\s+([A-Za-z_]\w*)(\(([^)]*)\))?\s+(.*?)\s*$',
            line, re.IGNORECASE
        )
        if not m:
            return False
        name = m.group(1).upper()
        params_raw = m.group(3)
        body = m.group(4)
        if params_raw is not None:
            params = [p.strip() for p in params_raw.split(",") if p.strip()]
            self.func[name] = (params, body)
        else:
            self.simple[name] = body
        return True

    def expand(self, text: str, depth: int = 0) -> str:
        """Expande macros no texto (até 20 níveis)."""
        if depth > 20:
            return text

        # Expande macros parametrizadas: NOME(a, b, ...)
        def replace_func(m):
            name = m.group(1).upper()
            if name not in self.func:
                return m.group(0)
            params, body = self.func[name]
            args_raw = m.group(2)
            args = [a.strip() for a in args_raw.split(",")]
            result = body
            for p, a in zip(params, args):
                result = re.sub(r'\b' + re.escape(p) + r'\b', a, result)
            return self.expand(result, depth + 1)

        pattern_func = r'\b(' + '|'.join(re.escape(k) for k in self.func) + r')\(([^)]*)\)'
        if self.func:
            text = re.sub(pattern_func, replace_func, text, flags=re.IGNORECASE)

        # Expande macros simples (palavra inteira, case-insensitive)
        for name, val in self.simple.items():
            text = re.sub(r'\b' + re.escape(name) + r'\b', val, text, flags=re.IGNORECASE)

        return text


# ─────────────────────────────────────────────────────────────────────────────
# Fase 3 – Coleta de #RESOURCE
# ─────────────────────────────────────────────────────────────────────────────

class ResourceTable:
    def __init__(self):
        self.resources: list[dict] = []          # ordem de inserção = índice ordinal
        self.name_to_index: dict[str, int] = {}  # $NOME -> ordinal 1-based

    def add(self, line: str) -> bool:
        """Processa linha #RESOURCE($nome, TIPO, arquivo). Retorna True se era diretiva."""
        m = re.match(
            r'^\s*#RESOURCE\s*\(\s*\$([A-Za-z_]\w*)\s*,\s*([A-Za-z_]\w*)\s*,\s*(.+?)\s*\)\s*$',
            line, re.IGNORECASE
        )
        if not m:
            return False
        var_name = m.group(1).upper()
        rtype    = m.group(2).upper()
        rfile    = m.group(3).strip().strip('"')

        if var_name in self.name_to_index:
            raise ValueError(f"Recurso '${ var_name}' já definido.")

        index = len(self.resources) + 1          # 1-based
        self.resources.append({"name": var_name, "type": rtype, "file": rfile, "index": index})
        self.name_to_index[var_name] = index
        return True

    def expand(self, text: str) -> str:
        """Substitui $NOME pelo índice ordinal do recurso."""
        def replace(m):
            var = m.group(1).upper()
            if var in self.name_to_index:
                return str(self.name_to_index[var])
            return m.group(0)   # mantém se não reconhecido
        return re.sub(r'\$([A-Za-z_]\w*)', replace, text)

    def header_lines(self) -> list[str]:
        """Gera as linhas de declaração de recurso (sem número de linha)."""
        lines = []
        for r in self.resources:
            if r["type"] in RESOURCE_HEADER_TYPES:
                lines.append(f'{r["type"]} "{r["file"]}"')
        return lines


# ─────────────────────────────────────────────────────────────────────────────
# Fase 4 – Primeira passagem: coleta de labels e corpo do programa
# ─────────────────────────────────────────────────────────────────────────────

RESOURCE_DECL_RE = re.compile(
    r'^\s*(FILE|TEXT|CODE|BSAVE|CSAVE)\s+"[^"]*"\s*$', re.IGNORECASE
)

def first_pass(raw_lines: list, macros: MacroTable, resources: ResourceTable,
               line_start: int, line_step: int):
    """
    Retorna:
      header_decls  – linhas sem número (declarações de recursos)
      body          – lista de dicts {label, content, src_line}
      label_map     – label -> número de linha BASIC (preenchido após numbering)
    """
    header_decls = []
    body = []

    in_header = True   # enquanto True, linhas de recurso vão para header

    for raw, origin in raw_lines:
        line = raw.strip()

        # Diretivas já processadas
        if macros.add(raw) or resources.add(raw):
            continue
        if re.match(r'^\s*#INCLUDE\b', raw, re.IGNORECASE):
            continue  # já expandido

        # Linha em branco / comentário puro -> pula
        if is_blank_or_comment(line):
            continue

        # Detecta label de início de linha NO RAW (antes da expansão de macros)
        # Label: linha começa com ':NOME' opcionalmente seguido de ':' e código
        label = None
        raw_stripped = raw.strip()
        label_m = re.match(r'^:([A-Za-z_]\w*):?[ \t]*(.*)', raw_stripped)
        if label_m:
            label        = label_m.group(1).upper()
            raw_content  = label_m.group(2).strip()   # parte após o label
        else:
            raw_content  = raw_stripped

        # Remove comentario inline antes de qualquer analise semantica
        raw_content, _comment = strip_inline_comment(raw_content)
        raw_content = raw_content.strip()

        # Verifica se e declaracao de recurso (FILE "...", TEXT "...", etc.)
        # Faz isso ANTES de expandir macros para nao corromper o nome do arquivo
        if in_header and RESOURCE_DECL_RE.match(raw_content):
            header_decls.append(raw_content)
            continue

        # Agora expande macros e recursos no conteudo (sem o label)
        content = macros.expand(raw_content)
        content = resources.expand(content)

        # Qualquer linha de código real (ou label) encerra a seção de header
        if content or label:
            in_header = False
            body.append({"label": label, "content": content, "origin": origin})

    return header_decls, body


# ─────────────────────────────────────────────────────────────────────────────
# Fase 5 – Numeração e mapa de labels
# ─────────────────────────────────────────────────────────────────────────────

def merge_labels(body: list) -> list:
    """Funde labels puros com a proxima linha de codigo, sem desperdicar numeros."""
    merged = []
    pending_labels = []

    for entry in body:
        if not entry["content"] and entry["label"]:
            pending_labels.append(entry["label"])
        else:
            new_entry = dict(entry)
            if pending_labels:
                all_labels = pending_labels + ([entry["label"]] if entry["label"] else [])
                new_entry["label"] = all_labels[0]
                new_entry["extra_labels"] = all_labels[1:]
            else:
                new_entry.setdefault("extra_labels", [])
            merged.append(new_entry)
            pending_labels = []

    for lbl in pending_labels:
        merged.append({"label": lbl, "extra_labels": [], "content": "", "origin": "<eof>"})

    return merged


def number_lines(body: list, start: int, step: int) -> dict:
    """Atribui numeros de linha ao corpo (ja fundido) e retorna mapa label->numero."""
    label_map = {}
    current = start
    for entry in body:
        entry["lineno"] = current
        if entry["label"]:
            if entry["label"] in label_map:
                raise ValueError(f"Label duplicado: :{entry['label']}")
            label_map[entry["label"]] = current
        for lbl in entry.get("extra_labels", []):
            if lbl in label_map:
                raise ValueError(f"Label duplicado: :{lbl}")
            label_map[lbl] = current
        if entry["content"]:
            current += step
    return label_map


# ─────────────────────────────────────────────────────────────────────────────
# Fase 6 – Segunda passagem: resolução de referências a labels
# ─────────────────────────────────────────────────────────────────────────────

# Comandos que aceitam número de linha como destino
GOTO_COMMANDS = re.compile(
    r'\b(GOTO|GOSUB|THEN|ELSE|RESTORE|RUN|LIST|DELETE|RENUM|AUTO|EDIT)\s+:([A-Za-z_]\w*)\b',
    re.IGNORECASE
)
# Também resolve referências isoladas em ON...GOTO/GOSUB
ON_GOTO_RE = re.compile(
    r'\b(ON\s+\w+\s+(?:GOTO|GOSUB))((?:\s*[:,]?\s*:([A-Za-z_]\w*))+)',
    re.IGNORECASE
)

def resolve_labels(content: str, label_map: dict) -> str:
    """Substitui :LABEL por número de linha nos comandos de desvio."""

    def replace_simple(m):
        cmd   = m.group(1)
        label = m.group(2).upper()
        if label not in label_map:
            raise ValueError(f"Label não definido: :{label}")
        return f"{cmd} {label_map[label]}"

    content = GOTO_COMMANDS.sub(replace_simple, content)

    # Substitui qualquer :LABEL restante que seja número de linha
    def replace_any(m):
        label = m.group(1).upper()
        if label in label_map:
            return str(label_map[label])
        return m.group(0)

    content = re.sub(r':([A-Za-z_]\w*)\b', replace_any, content)

    return content


# ─────────────────────────────────────────────────────────────────────────────
# Orquestrador principal
# ─────────────────────────────────────────────────────────────────────────────

def preprocess(input_path: str, output_path: str, line_start: int = 10, line_step: int = 10):
    macros    = MacroTable()
    resources = ResourceTable()

    # Fase 1: leitura + includes
    raw_lines = read_with_includes(input_path)

    # Fase 2-4: primeira passagem
    header_decls, body = first_pass(raw_lines, macros, resources, line_start, line_step)

    # Adiciona declarações geradas pelos #RESOURCE que não vieram do código
    resource_headers = resources.header_lines()
    # Mescla: declarações explícitas do código primeiro, depois as do #RESOURCE
    all_headers = list(dict.fromkeys(header_decls + resource_headers))

    # Fase 4b: funde labels puros com a proxima linha (evita desperdicar numeros)
    body = merge_labels(body)

    # Fase 5: numeracao
    label_map = number_lines(body, line_start, line_step)

    # Fase 6: segunda passagem + geracao de saida
    output_lines = []

    # Cabecalho sem numero de linha (deduplicado)
    for h in all_headers:
        output_lines.append(h)

    # Corpo numerado
    for entry in body:
        content = resolve_labels(entry["content"], label_map)
        # Linha de declaracao de recurso no corpo -> pula (ja esta no header)
        if RESOURCE_DECL_RE.match(content):
            continue
        # Emite apenas linhas com conteudo real
        if content:
            output_lines.append(f"{entry['lineno']} {content}")

    result = "\n".join(output_lines) + "\n"

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(result)

    return result, label_map, resources


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Pré-processador de MSX BASIC",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos de uso no source:
  #RESOURCE($MAPA, FILE, level1.bin)
  #RESOURCE($TEXTO, TEXT, intro.txt)
  #DEFINE SCREEN_W 256
  #DEFINE MAX(a,b) IF (a)>(b) THEN (a) ELSE (b)
  #INCLUDE "rotinas.bas"

  :INICIO
    SCREEN 2
    GOTO :LOOP
  :LOOP
    PRINT "Frame"; $MAPA
    GOTO :LOOP
"""
    )
    parser.add_argument("input",  help="Arquivo fonte .bas")
    parser.add_argument("-o", "--output", help="Arquivo de saída (padrão: <input>_out.bas)")
    parser.add_argument("--start", type=int, default=10,  help="Primeira linha (padrão 10)")
    parser.add_argument("--step",  type=int, default=10,  help="Incremento de linha (padrão 10)")
    parser.add_argument("--verbose", action="store_true", help="Mostra mapa de labels e recursos")

    args = parser.parse_args()

    if not os.path.isfile(args.input):
        print(f"Erro: arquivo não encontrado: {args.input}", file=sys.stderr)
        sys.exit(1)

    output = args.output or os.path.splitext(args.input)[0] + "_out.bas"

    try:
        result, label_map, resources = preprocess(
            args.input, output, args.start, args.step
        )
    except (ValueError, RecursionError, FileNotFoundError) as e:
        print(f"Erro de pré-processamento: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Saída gerada: {output}")

    if args.verbose:
        if label_map:
            print("\n── Labels ──────────────────────────")
            for lbl, ln in sorted(label_map.items(), key=lambda x: x[1]):
                print(f"  :{lbl:20s} -> linha {ln}")
        if resources.resources:
            print("\n── Recursos ────────────────────────")
            for r in resources.resources:
                print(f"  ${r['name']:20s} -> índice {r['index']:3d}  [{r['type']}] {r['file']}")

    if args.verbose:
        print("\n── Programa gerado ─────────────────")
        print(result)


if __name__ == "__main__":
    main()
