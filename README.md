# A Million Keys

Open virtual screening against a neglected-disease target, with every result
published as it came out — including the ones that failed.

**We screen. We publish. We promise nothing else.**

This repository contains no claim about curing, treating or discovering
anything. It contains a docking pipeline, the runs it produced, and the numbers
those runs gave.

---

## Status — 14 September 2026

The first target, **cruzain** (the major cysteine protease of *Trypanosoma
cruzi*, a validated Chagas disease target), was **rejected by our own
criterion**.

| Test | Result |
|---|---|
| Positive control — biotin / streptavidin (1STP) | **0.77 Å** pose 1 |
| Positive control — HIV protease (1HVR, 46 atoms) | **0.47 Å** pose 1 |
| Cruzain — pose reproduction, 7 crystal ligands | **0 / 7** within 2.0 Å |
| Cruzain — enrichment, 49 actives vs 590 decoys | **AUC 0.638** (cutoff 0.70) |

The pipeline reproduces crystallographic poses to sub-angstrom accuracy on
textbook cases. It fails on cruzain — including on a ligand with **zero
rotatable bonds**. Scoring the true crystal pose of 1ME3/P10 gives **−2.4
kcal/mol** while wrong poses score **−6.9**: the scoring function does not
recognise the real pose in this shallow, open cleft.

The 0.70 AUC cutoff was fixed **before** the run, not after seeing the number.

### Caveats we are not hiding

- Decoys were drawn from ChEMBL, a library of **bioactive** compounds. Inert
  decoys (ZINC, DUD-E style) would be a fairer test.
- n = 49 actives is small.
- One receptor structure, one exhaustiveness setting.

Next: rerun with fair decoys, and test **TcCYP51** — a deep, enclosed,
heme-containing site, the opposite of cruzain. Changing target means changing
`site/alvo.json` and one PDB file.

---

## What is here

    SPEC.md                    frozen spec: economics, target, pipeline, roadmap
    scripts/
      valida_alvo.py           superposition, redocking, cross-docking
      valida_pose.py           pose validation on drug-like crystal ligands
      controle_positivo.py     same pipeline on textbook cases — is the code right?
      diagnostico.py           score_only / local_only: search error or prep error?
      busca_cristais.py        finds non-covalent crystal ligands for a target
      coleta_chembl.py         pulls measured inhibitors from ChEMBL
      enriquecimento.py        actives vs property-matched decoys, AUC and EF
      exporta_site.py          consolidates every result into site/data/dados.json
    site/                      the page (English); alvo.json holds the target
    servir.bat                 serves the site at http://localhost:8440

Code comments are in Portuguese; everything user-facing is in English.

## Reproducing

Requires Python 3.10+, then:

    pip install rdkit meeko gemmi pdb2pqr numpy pillow

Download AutoDock Vina 1.2.5 (Windows binary) into `tools/vina.exe`:
<https://github.com/ccsb-scripps/AutoDock-Vina/releases>

Then, in order:

    python scripts/controle_positivo.py     # does the pipeline work at all?
    python scripts/busca_cristais.py        # which crystals can validate this target?
    python scripts/valida_pose.py           # pose reproduction
    python scripts/coleta_chembl.py         # measured inhibitors
    python scripts/enriquecimento.py prep
    python scripts/enriquecimento.py dock   # ~1 h on 16 cores
    python scripts/enriquecimento.py metricas
    python scripts/exporta_site.py

Structures download themselves from the RCSB. Seeds are fixed, so runs repeat.

## Method

AutoDock Vina 1.2.5 · Meeko 0.8 · RDKit · gemmi. Receptor protonation, box
centre and size, seeds and exhaustiveness are recorded in the scripts and in
`SPEC.md`.

Three traps this project hit, documented so others do not repeat them:

1. **Check `LINK` records before picking a validation crystal.** 2OZ2 and 1AIM
   have their ligand covalently bound to Cys25. Non-covalent docking can never
   reproduce those poses, and the failure looks like a broken pipeline.
2. **Superpose using the ligand's own chain.** Aligning by best-RMSD chain puts
   the ligand 30–55 Å from the site in multi-copy structures, which reads as a
   false "allosteric" result.
3. **Run a positive control before blaming the target — or the code.**

## Licence and data

Crystal structures: RCSB PDB. Measured activities: ChEMBL. Compound libraries
are used, never redistributed.
