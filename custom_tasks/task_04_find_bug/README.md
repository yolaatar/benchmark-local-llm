# Masque axonmyelin manquant avec un modèle 3 classes (#1003)

- **Catégorie** : analyser du code
- **Mode Aider** : `code`
- **Dépôt** : AxonDeepSeg (clone local de `axondeepseg/axondeepseg`)
- **Commit de départ** : `bb108a4` (avant la PR #1005)
- **Fichiers donnés à Aider** : apply_model.py, segment.py, merge_masks.py (un humain pointerait vers ces fichiers ; Claude Code, lui, explore seul).

## Objectif

Le prompt décrit seulement le symptôme, comme un rapport d'utilisateur. Le modèle doit remonter à la comparaison d'égalité de liste.

## Référence

Issue #1003, corrigée dans PR #1005 : dans `apply_model.axon_segmentation`, `is_axonmyelin_seg = ['axon', 'myelin'] == output_classes` devient `{'axon', 'myelin'} <= set(output_classes)`. 2 lignes.

## Prompt

Dans `task.yaml` (champ `prompt`), envoyé tel quel, en anglais, à chaque modèle local et à Claude Code.

## Critères de revue (manuelle)

- [ ] Cause racine identifiée : l'égalité stricte de listes échoue dès qu'il y a une 3e classe
- [ ] Correctif minimal équivalent : test d'inclusion (subset) ou `'axon' in ... and 'myelin' in ...`
- [ ] Bonus finesse : remarque que `merge_masks(new_masks[0], new_masks[1])` suppose que axon et myelin sont les 2 premières classes après tri, et rend l'appel robuste (indices par nom)
- [ ] Pas de 'correctifs' parasites dans segment.py ou merge_masks.py
- [ ] Explication claire

Noter le verdict dans le JSON de résultat (`review.success` = true / false / "partial", `review.notes`).

## Rejouer avec Claude Code (Sonnet / Opus)

```powershell
cd benchmark-local-llm
.\.venv\Scripts\python.exe run_custom_tasks.py --prepare-manual claude-sonnet --tasks task_04_find_bug
cd work\task_04_find_bug\claude-sonnet\repo
claude --model sonnet        # ou: claude --model opus (et label claude-opus ci-dessus)
# coller le prompt affiché, laisser Claude Code travailler, noter le temps et le nombre de messages envoyés
cd ..\..\..\..
.\.venv\Scripts\python.exe run_custom_tasks.py --collect-manual claude-sonnet --tasks task_04_find_bug --elapsed <secondes> --messages <n>
```
