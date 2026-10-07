# Réécrire `test_filter_morphometrics.py`

- **Catégorie** : écrire du code
- **Mode Aider** : `code`
- **Dépôt** : AxonDeepSeg (clone local de `axondeepseg/axondeepseg`)
- **Commit de départ** : `cba1c42` (master, après PR #1005), fichier de test supprimé avant le run (`setup_cmds`)
- **Fichiers donnés à Aider** : le fichier de test à créer ; en lecture seule : filter_morphometrics.py, filter.yaml, test_aggregate.py (exemple de style).

## Objectif

Faire écrire une suite pytest pour le module de filtrage des morphometrics. Aider exécute les tests après chaque édit (`test_cmd` avec l'env conda `ads`) et renvoie les échecs au modèle, jusqu'à 3 corrections.

## Référence

`test/morphometrics/test_filter_morphometrics.py` d'Armand dans PR #1005 : 12 tests (read_config x3, règles myelinated x4, unmyelinated x4, main x2). Le diff du résultat se lit directement contre ce fichier.

## Prompt

Dans `task.yaml` (champ `prompt`), envoyé tel quel, en anglais, à chaque modèle local et à Claude Code.

## Critères de revue (manuelle)

- [ ] Les tests passent sur le code actuel (`python -m pytest test/morphometrics/test_filter_morphometrics.py` dans l'env `ads`)
- [ ] Conventions respectées : classe `TestCore`, `@pytest.mark.unit`, `tmp_path`
- [ ] Cas limites réellement testés : comparaisons strictes (`>` / `<`), seuil `~`/None désactivé, g-ratio hors ]0,1[ et NaN, règle inconnue (warning)
- [ ] `main()` testé de bout en bout avec de vrais .xlsx dans `tmp_path`
- [ ] Mutation check : inverser un `>` en `>=` dans `apply_unmyelinated_rules` doit faire échouer au moins un test
- [ ] Comparer la couverture avec les 12 tests de référence

Noter le verdict dans le JSON de résultat (`review.success` = true / false / "partial", `review.notes`).

## Rejouer avec Claude Code (Sonnet / Opus)

```powershell
cd benchmark-local-llm
.\.venv\Scripts\python.exe run_custom_tasks.py --prepare-manual claude-sonnet --tasks task_02_write_test
cd work\task_02_write_test\claude-sonnet\repo
claude --model sonnet        # ou: claude --model opus (et label claude-opus ci-dessus)
# coller le prompt affiché, laisser Claude Code travailler, noter le temps et le nombre de messages envoyés
cd ..\..\..\..
.\.venv\Scripts\python.exe run_custom_tasks.py --collect-manual claude-sonnet --tasks task_02_write_test --elapsed <secondes> --messages <n>
```
