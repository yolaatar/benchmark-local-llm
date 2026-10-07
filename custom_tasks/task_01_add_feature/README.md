# Ajouter `--allow-large-images` à `axondeepseg_morphometrics`

- **Catégorie** : écrire du code
- **Mode Aider** : `code`
- **Dépôt** : AxonDeepSeg (clone local de `axondeepseg/axondeepseg`)
- **Commit de départ** : `bb108a4` (juste avant `1d8809e`)
- **Fichiers donnés à Aider** : launch_morphometrics_computation.py, postprocessing.py et leurs 2 fichiers de test (la doc rst est laissée hors contexte : 12k tokens).

## Objectif

Réimplémenter le flag : option CLI, propagation jusqu'à `ads.imread` dans `launch_morphometrics_computation` et `load_mask`, et surtout le cas piège, `generate_and_save_colored_image_with_index_numbers` dans `postprocessing.py`, qui appelait `Image.open()` directement et contournait `ads_utils`.

## Référence

PR #1007 (commits `1d8809e` et `964b6a9`), issues #990 et #1006. Diff de référence : `git diff bb108a4 964b6a9`.

## Prompt

Dans `task.yaml` (champ `prompt`), envoyé tel quel, en anglais, à chaque modèle local et à Claude Code.

## Critères de revue (manuelle)

- [ ] Flag `--allow-large-images` ajouté à l'argparse, `store_true`, désactivé par défaut
- [ ] Propagé à **tous** les `imread` : image, prédiction, les 3 modes de `load_mask` (myelinated, unmyelinated, nerve)
- [ ] `postprocessing.py` : l'image d'index colorée passe par `ads.imread(..., allow_large_images=...)` (la référence) ou relève proprement la limite PIL
- [ ] Comportement par défaut inchangé, tests existants toujours OK
- [ ] Tests ajoutés : le flag est parsé et transmis (mock), et le chemin postprocessing est couvert
- [ ] Pas de modification hors périmètre

Noter le verdict dans le JSON de résultat (`review.success` = true / false / "partial", `review.notes`).

## Rejouer avec Claude Code (Sonnet / Opus)

```powershell
cd benchmark-local-llm
.\.venv\Scripts\python.exe run_custom_tasks.py --prepare-manual claude-sonnet --tasks task_01_add_feature
cd work\task_01_add_feature\claude-sonnet\repo
claude --model sonnet        # ou: claude --model opus (et label claude-opus ci-dessus)
# coller le prompt affiché, laisser Claude Code travailler, noter le temps et le nombre de messages envoyés
cd ..\..\..\..
.\.venv\Scripts\python.exe run_custom_tasks.py --collect-manual claude-sonnet --tasks task_01_add_feature --elapsed <secondes> --messages <n>
```
