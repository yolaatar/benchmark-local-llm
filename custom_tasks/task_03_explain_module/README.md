# Expliquer le pipeline de filtrage des morphometrics et de comptage d'axones

- **Catégorie** : analyser du code
- **Mode Aider** : `ask`
- **Dépôt** : AxonDeepSeg (clone local de `axondeepseg/axondeepseg`)
- **Commit de départ** : `cba1c42` (master, après PR #1005)
- **Fichiers donnés à Aider** : filter_morphometrics.py, count_axons.py, filter.yaml. Mode `ask` : aucun fichier modifié, la réponse est dans `final_answer`.

## Objectif

Explication d'un module récent que le modèle n'a pas pu voir à l'entraînement.

## Référence

Le code lui-même et la description de la PR #1005 (Armand Collin).

## Prompt

Dans `task.yaml` (champ `prompt`), envoyé tel quel, en anglais, à chaque modèle local et à Claude Code.

## Critères de revue (manuelle)

- [ ] Config YAML : 2 clés obligatoires (`myelinated`, `unmyelinated`), sinon `ValueError` ; liste de règles appliquées dans l'ordre ; `~` (None) = règle désactivée
- [ ] Règles exactes : `valid-g-ratio-only` garde 0 < g < 1 et retire les NaN ; `axon-diam-gt`, `solidity-gt` : `>` strict ; `axon-area-lt` : `<` strict ; règle inconnue = warning, pas d'erreur
- [ ] Sorties : `_filtered.xlsx` ou écrasement avec `-o` ; `-m` met à jour les masques
- [ ] Mise à jour des masques : carte d'instances (uaxon : `measure.label` ; myelinated : `_instance-map.png` 16 bits si présente, sinon watershed recalculé), IDs valides = 1re colonne **+1**, pixels des axones rejetés mis à 0, puis `merge_masks` reconstruit axonmyelin
- [ ] Comptage : mode xlsx (nombre de lignes) ou mode masque `-m` (composantes connexes de axonmyelin > 200) ; les fichiers `_filtered` ont priorité ; sortie CSV
- [ ] Chaînage : filter (éventuellement `-m`) puis count, qui reprend automatiquement les versions filtrées
- [ ] Pièges réels : un seuil `0` est traité comme désactivé (`if threshold:`) ; en mode masque les axones qui se touchent comptent pour un ; mode xlsx : crash si le fichier axon est absent ; `-o -m` écrase les masques d'origine ; dépendance à l'ordre de la 1re colonne du xlsx
- [ ] Aucune hallucination (option, fonction ou fichier inexistant)

Noter le verdict dans le JSON de résultat (`review.success` = true / false / "partial", `review.notes`).

## Rejouer avec Claude Code (Sonnet / Opus)

```powershell
cd benchmark-local-llm
.\.venv\Scripts\python.exe run_custom_tasks.py --prepare-manual claude-sonnet --tasks task_03_explain_module
cd work\task_03_explain_module\claude-sonnet\repo
claude --model sonnet        # ou: claude --model opus (et label claude-opus ci-dessus)
# coller le prompt affiché, laisser Claude Code travailler, noter le temps et le nombre de messages envoyés
cd ..\..\..\..
.\.venv\Scripts\python.exe run_custom_tasks.py --collect-manual claude-sonnet --tasks task_03_explain_module --elapsed <secondes> --messages <n> --answer-file reponse.md   # coller la réponse de Claude dans ce fichier
```
