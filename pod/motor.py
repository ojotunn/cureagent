"""
Motor de triagem. Minimo de proposito.

Cada molecula que termina vira uma linha NA HORA. Sem lote, sem buffer, sem
esperar nada — foi exatamente isso que fez o motor trabalhar em silencio antes.
"""

import json, os, subprocess, sys, time
from multiprocessing import Pool

BASE = "/work"
VINA = BASE + "/vina"
REC = BASE + "/target/receptor.pdbqt"
SAIDA = BASE + "/out/scores.jsonl"
PROG = BASE + "/out/progresso.json"

CENTRO = ("2.49", "-24.48", "18.32")
TAM = ("22", "22", "22")


def doca(caminho):
    cid = os.path.basename(caminho)[:-6]
    cmd = [VINA, "--receptor", REC, "--ligand", caminho,
           "--center_x", CENTRO[0], "--center_y", CENTRO[1], "--center_z", CENTRO[2],
           "--size_x", TAM[0], "--size_y", TAM[1], "--size_z", TAM[2],
           "--exhaustiveness", "8", "--seed", "42", "--num_modes", "1", "--cpu", "1"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except Exception:
        return None
    for linha in r.stdout.splitlines():
        p = linha.split()
        if len(p) >= 2 and p[0] == "1":
            try:
                return {"id": cid, "score": float(p[1]), "t": int(time.time())}
            except ValueError:
                return None
    return None


def main():
    os.makedirs(BASE + "/out", exist_ok=True)

    feitos = set()
    if os.path.exists(SAIDA):
        for l in open(SAIDA):
            try: feitos.add(json.loads(l)["id"])
            except Exception: pass

    ligs = sorted(BASE + "/ligs/" + f for f in os.listdir(BASE + "/ligs")
                  if f.endswith(".pdbqt"))
    ligs = [l for l in ligs if os.path.basename(l)[:-6] not in feitos]

    n = os.cpu_count()
    print("motor: %d moleculas na fila, %d ja feitas, %d nucleos"
          % (len(ligs), len(feitos), n), flush=True)

    t0 = time.time()
    total = 0
    with open(SAIDA, "a", buffering=1) as fh:          # linha a linha, sem buffer
        with Pool(processes=max(1, n - 2)) as pool:
            for r in pool.imap_unordered(doca, ligs):
                if not r:
                    continue
                fh.write(json.dumps(r) + "\n")
                total += 1
                dt = time.time() - t0
                json.dump({
                    "triadas": total + len(feitos),
                    "nesta_sessao": total,
                    "seg_por_molecula": round(dt / total, 2),
                    "por_hora": int(total / max(dt, 1) * 3600),
                    "nucleos": n,
                    "receptor": "TcCYP51 3KHM",
                    "atualizado": time.strftime("%Y-%m-%d %H:%M:%S"),
                }, open(PROG, "w"))
                if total % 10 == 0:
                    print("  %d triadas · %.1f min · %d/hora"
                          % (total, dt / 60, total / max(dt, 1) * 3600), flush=True)
    print("fim: %d em %.1f min" % (total, (time.time() - t0) / 60), flush=True)


if __name__ == "__main__":
    main()
