# Centraliser la gestion des grandes images dans `ads_utils`

- **Catégorie** : refactor multi-fichiers
- **Mode Aider** : `code`
- **Dépôt** : AxonDeepSeg (clone local de `axondeepseg/axondeepseg`)
- **Commit de départ** : `cba1c42` (master)
- **Fichiers donnés à Aider** : ads_utils.py, apply_model.py, segment.py, count_axons.py, filter_morphometrics.py.

## Objectif

Deux extractions : (1) un context manager qui relève puis restaure `Image.MAX_IMAGE_PIXELS`, utilisé dans `imread`, `get_imshape` et `apply_model.axon_segmentation` (qui aujourd'hui ne restaure jamais la limite) ; (2) un helper argparse `add_allow_large_images_argument` qui remplace les 3 copies du bloc `--allow-large-images`.

## Référence

Pas de référence upstream. Motivation : la même logique a nécessité 3 PRs de correctif (#974, #988, #1007).

## Prompt

Dans `task.yaml` (champ `prompt`), envoyé tel quel, en anglais, à chaque modèle local et à Claude Code.

## Critères de revue (manuelle)

- [ ] Context manager correct : restauration dans un `finally` (ou `@contextmanager` avec try/finally), no-op si False
- [ ] Plus aucune manipulation manuelle de `Image.MAX_IMAGE_PIXELS` dans imread/get_imshape/apply_model (`git grep MAX_IMAGE_PIXELS`)
- [ ] `apply_model` : variable d'env `ADS_ALLOW_LARGE_IMAGES` conservée ; la limite couvre bien l'appel à nnU-Net
- [ ] Helper argparse utilisé dans les 3 CLI, même `dest`, même défaut ; textes d'aide raisonnables
- [ ] Signatures publiques inchangées ; tests existants OK : `python -m pytest test/test_ads_utils.py test/morphometrics -q` dans l'env `ads`
- [ ] Pas de code mort, pas d'import inutilisé, diff lisible

Noter le verdict dans le JSON de résultat (`review.success` = true / false / "partial", `review.notes`).

## Rejouer avec Claude Code (Sonnet / Opus)

```powershell
cd benchmark-local-llm
.\.venv\Scripts\python.exe run_custom_tasks.py --prepare-manual claude-sonnet --tasks task_05_refactor
cd work\task_05_refactor\claude-sonnet\repo
claude --model sonnet        # ou: claude --model opus (et label claude-opus ci-dessus)
# coller le prompt affiché, laisser Claude Code travailler, noter le temps et le nombre de messages envoyés
cd ..\..\..\..
.\.venv\Scripts\python.exe run_custom_tasks.py --collect-manual claude-sonnet --tasks task_05_refactor --elapsed <secondes> --messages <n>
```
