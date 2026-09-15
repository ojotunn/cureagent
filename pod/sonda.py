"""Sonda so a disponibilidade de cristal. Nao doca nada, so consulta o RCSB."""
import sys
sys.argv = ["sonda", "x", "x", "x"]
import importlib.util
spec = importlib.util.spec_from_file_location("v", "/work/valida.py")
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)

TERMOS = [
    "Trypanosoma cruzi trypanothione reductase",
    "Trypanosoma cruzi glyceraldehyde-3-phosphate dehydrogenase",
    "Trypanosoma cruzi dihydroorotate dehydrogenase",
    "Trypanosoma brucei trypanothione reductase",
]
for t in TERMOS:
    print("\n===", t)
    try:
        c = v.acha_cristal(t)
        print("  -> %d candidatos: %s" % (len(c), [(x[1], x[2], x[3]) for x in c[:6]]))
    except Exception as e:
        print("  erro:", type(e).__name__, e)
