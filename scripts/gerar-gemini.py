"""
Gerador de arte pela API do Gemini, direto no Google — sem revenda no meio.

POR QUE ESTE ARQUIVO EXISTE (23/08/2026): o modelo que resolveu a arte do show
("Nano Banana Pro", na Higgsfield) e o modelo de imagem do Google. A Higgsfield
e revenda: cobra em credito proprio e embute margem. Falando direto com a API,
o mesmo modelo sai pelo preco de tabela do Google.

O que ESTE arquivo NAO muda: a receita. Tudo que a gente aprendeu apanhando
continua valendo, e esta escrito aqui embaixo como regra, nao como comentario
solto:
  - nunca encadear mais de 2 edicoes (da 3a em diante a proporcao derrete);
  - instrucao de escala tem que ser MEDIVEL ("cada parede o dobro"), nunca
    adjetivo ("maior");
  - adjetivo de cor em prompt de cena inunda a cena inteira.

CHAVE: gere em https://aistudio.google.com  ->  Get API key. Depois:
    GEMINI_API_KEY=...            no .env da raiz do projeto (nao vai pro git)

Uso:
    python scripts/gerar-gemini.py --modelos
        lista os modelos de imagem disponiveis para a sua chave. Rode isto
        PRIMEIRO: o nome do modelo muda com o tempo e chutar da 404.

    python scripts/gerar-gemini.py <saida.png> "<prompt>" [ref1.png ref2.png]
        gera (ou edita, se passar imagem de referencia) e salva o PNG.

Variaveis opcionais:
    GEMINI_MODEL     nome do modelo (padrao: o primeiro de imagem que aparecer)
    GEMINI_RAZAO     proporcao, padrao 16:9
    GEMINI_TAMANHO   1K | 2K | 4K, padrao 4K
"""

import base64
import json
import mimetypes
import os
import sys
import time
import urllib.error
import urllib.request

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = "https://generativelanguage.googleapis.com/v1beta"
RAZAO = os.environ.get("GEMINI_RAZAO", "16:9")
TAMANHO = os.environ.get("GEMINI_TAMANHO", "4K")


def chave():
    """Da variavel de ambiente ou do .env da raiz — a mesma ordem que o resto
    do projeto usa, para nao existirem dois lugares de verdade."""
    k = os.environ.get("GEMINI_API_KEY", "").strip()
    if k:
        return k
    env = os.path.join(RAIZ, ".env")
    if os.path.exists(env):
        for linha in open(env, encoding="utf-8", errors="ignore"):
            if linha.strip().startswith("GEMINI_API_KEY"):
                return linha.split("=", 1)[1].strip()
    raise SystemExit(
        "Falta a chave. Pegue em https://aistudio.google.com (Get API key) e ponha\n"
        "  GEMINI_API_KEY=...\n"
        f"no arquivo {env}"
    )


# Erros que passam sozinhos: modelo lotado (503) e limite de taxa (429). Nao
# adianta reenviar na mao — o script espera e tenta de novo, dobrando a espera.
TRANSITORIOS = {429, 500, 502, 503, 504}


def pedir(caminho, corpo=None, tentativas=6):
    espera = 20
    for tentativa in range(1, tentativas + 1):
        req = urllib.request.Request(
            f"{BASE}/{caminho}",
            data=json.dumps(corpo).encode() if corpo else None,
            headers={"x-goog-api-key": chave(), "Content-Type": "application/json"},
            method="POST" if corpo else "GET",
        )
        try:
            # 4K com imagem de referencia passa de 5 min; 300s estourava.
            with urllib.request.urlopen(req, timeout=900) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            detalhe = e.read().decode(errors="ignore")[:400]
            if e.code not in TRANSITORIOS or tentativa == tentativas:
                raise SystemExit(f"API devolveu {e.code}:\n{detalhe}")
            print(f"   {e.code} — lotado. tentativa {tentativa}/{tentativas}, "
                  f"esperando {espera}s", flush=True)
        except (TimeoutError, urllib.error.URLError) as e:
            if tentativa == tentativas:
                raise SystemExit(f"rede falhou em {tentativas} tentativas: {e}")
            print(f"   rede instavel. tentativa {tentativa}/{tentativas}, "
                  f"esperando {espera}s", flush=True)
        time.sleep(espera)
        espera = min(espera * 2, 180)


def modelos_de_imagem():
    """Os modelos da conta que sabem DEVOLVER imagem. Listar em vez de cravar o
    nome no codigo: os nomes do Google mudam de versao e cravar da 404 meses
    depois, quando ninguem lembra por que quebrou."""
    dados = pedir("models")
    achados = []
    for m in dados.get("models", []):
        nome = m.get("name", "").replace("models/", "")
        if "image" in nome.lower() or "image" in json.dumps(m.get("supportedGenerationMethods", [])).lower():
            achados.append((nome, m.get("displayName", "")))
    return achados


def escolher_modelo():
    fixo = os.environ.get("GEMINI_MODEL", "").strip()
    if fixo:
        return fixo
    achados = modelos_de_imagem()
    if not achados:
        raise SystemExit("nenhum modelo de imagem disponivel para esta chave "
                         "(rode --modelos para ver a lista crua)")
    # Prefere o mais capaz quando houver escolha: "pro" antes de "flash".
    achados.sort(key=lambda a: ("pro" not in a[0], a[0]))
    return achados[0][0]


def gerar(destino, prompt, referencias=()):
    partes = [{"text": prompt}]
    # Imagem de referencia = edicao. Vale a regra das 2 edicoes: passar a saida
    # anterior como referencia repetidas vezes e o caminho para a arte derreter.
    for ref in referencias:
        tipo = mimetypes.guess_type(ref)[0] or "image/png"
        with open(ref, "rb") as f:
            partes.append({"inline_data": {"mime_type": tipo,
                                           "data": base64.b64encode(f.read()).decode()}})

    modelo = escolher_modelo()
    corpo = {
        "contents": [{"parts": partes}],
        "generationConfig": {
            "responseModalities": ["IMAGE"],
            "imageConfig": {"aspectRatio": RAZAO, "imageSize": TAMANHO},
        },
    }
    print(f"[{modelo}] {RAZAO} {TAMANHO}"
          + (f" · {len(referencias)} referencia(s)" if referencias else ""))
    resposta = pedir(f"models/{modelo}:generateContent", corpo)

    for cand in resposta.get("candidates", []):
        for parte in cand.get("content", {}).get("parts", []):
            dado = parte.get("inlineData") or parte.get("inline_data")
            if dado and dado.get("data"):
                os.makedirs(os.path.dirname(os.path.abspath(destino)), exist_ok=True)
                with open(destino, "wb") as f:
                    f.write(base64.b64decode(dado["data"]))
                print(f"-> {destino}")
                return destino
    # Sem imagem na resposta: quase sempre e recusa de conteudo ou prompt vazio.
    raise SystemExit("a resposta nao trouxe imagem:\n"
                     + json.dumps(resposta, indent=2)[:800])


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    if sys.argv[1] == "--modelos":
        for nome, rotulo in modelos_de_imagem():
            print(f"  {nome:46} {rotulo}")
        raise SystemExit(0)
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    gerar(sys.argv[1], sys.argv[2], sys.argv[3:])
