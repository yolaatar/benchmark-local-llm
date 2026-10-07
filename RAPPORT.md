# Rapport : LLM codeurs locaux vs Claude Code sur AxonDeepSeg

Banc de test monté et exécuté le 2026-09-18 pour une présentation au labo NeuroPoly.
Ce fichier consigne tous les résultats, observations et remarques faites pendant le montage et les runs.
Mode d'emploi du banc : `NOTES.md`. Données brutes : `results/*.json`, logs : `results/logs/`, clones de travail : `work/`.

Sommaire :
1. Machine et installation (incidents compris)
2. Modèles retenus et mesures
3. Choix de méthode et limites
4. Benchmark standardisé (Aider polyglot)
5. Tâches AxonDeepSeg : résultats et observations détaillées
6. Claude Code sur backend local
7. Claude Code Sonnet (backend Anthropic)
8. Trouvailles annexes sur le code d'ADS
9. Enseignements pour la présentation
10. Points ouverts

---

## 1. Machine et installation

- Windows 11, RTX 5060 Ti 16 Go (driver 591.86), 32 Go RAM, 206 Go libres.
- Ollama 0.34.2 (winget), Aider 0.86.2 dans un venv Python 3.12.10, harnais aider au tag `v0.86.2`, exercices `polyglot-benchmark@7e0611e`.
- GPU validé : modèle 100 % en VRAM (`size_vram == size`), 87 % d'utilisation GPU, ~450 tok/s sur un 0.5B.

Incidents et remarques :
- `python` n'est pas dans le PATH (Python 3.12 installé mais invisible) ; `ollama` non plus dans les shells ouverts avant l'install.
- `ollama search` n'existe pas dans le CLI : recherche faite sur ollama.com/library. La page "coder" est polluée par des modèles communautaires ; il faut regarder la bibliothèque officielle.
- `pip install -e vendor/aider` échoue : litellm récent contient des chemins > 260 caractères et Windows Long Paths est désactivé. Contourné en gardant `aider-chat` 0.86.2 et en alignant le harnais sur le tag `v0.86.2`. L'install ratée avait monté des dépendances ; re-épinglées (`pip check` propre, `requirements.lock.txt`).
- Contexte par défaut d'Ollama : 4 096 tokens, trop court pour Aider.
- **RAM** : au premier run complet, seulement 3,9 Go de RAM libres sur 31 (League of Legends, Riot, Discord, ~10 process Brave) ; Claude Code a tué le benchmark faute de mémoire. Relancé après fermeture des applis (23 Go libres). Le 35B met ~9 Go en RAM : fermer jeux et navigateur avant un run.

## 2. Modèles retenus et mesures

Constat de recherche : chez Qwen, aucun modèle "coder" plus récent que qwen2.5-coder n'existe en 7B ou 14B ; les générations 2026 (qwen3-coder, qwen3-coder-next, variantes `-coding` de qwen3.6) n'existent qu'à partir de 27B.

| Palier | Modèle | Archi | Téléchargement | VRAM (ctx 16k) | GPU | Génération | Prompt |
|---|---|---|---|---|---|---|---|
| Léger | qwen2.5-coder:7b | dense 7.6B Q4 | 4,7 Go | 5 483 Mio | 100 % | 81 tok/s | ~3 500 tok/s |
| Moyen | qwen2.5-coder:14b | dense 14.8B Q4 | 9,0 Go | 11 545 Mio | 100 % | 41 tok/s | ~1 700 tok/s |
| Haut | qwen3.6:35b-a3b-coding | MoE 35.5B / 3B actifs Q4 | 22 Go | 14 392 Mio + ~9 Go RAM | 59 % | 68-89 tok/s | ~970 tok/s |

- À 32k : 7B 6 432 Mio (100 %), 14B 14 120 Mio (**93 %, déborde, 33 tok/s**), 35B 14 420 Mio (58 %, 86 tok/s). À 64k, 35B : 14 481 Mio, 54 % GPU, 90 tok/s.
- **Le 35B MoE génère plus vite que le 14B dense** malgré 41 % du modèle en RAM (3B paramètres actifs par token). Son cache KV grossit très peu avec le contexte.
- Les qwen2.5-coder sont **plafonnés à 32k de contexte par construction** (Ollama ramène `num_ctx` au `context_length` natif) ; qwen3.6 monte à 256k.
- En contexte long, le 14B s'effondre : **~13 tok/s** sur un prompt de ~25k tokens (débordement RAM + attention longue).
- Écartés : qwen3-coder-next (52 Go, ne tient pas), qwen3-coder:30b (génération précédente), qwen3.6:27b dense (offload lent), qwen3.5:9b (généraliste ; candidat pour un palier léger 2026).
- Réserve : les paliers 7B/14B sont de 2024, le 35B de 2026. L'écart mélange taille et génération.

## 3. Choix de méthode et limites

Benchmark :
- Sous-ensemble : 25 des 34 exercices Python du polyglot, tirés avec `random.Random(42)`. Le polyglot regroupe les exercices Exercism **les plus durs** : des scores bas sont normaux (qwen2.5-coder-32b fait ~16 % sur le polyglot complet).
- **Pas de Docker** (ni Docker ni WSL sur la machine) : `AIDER_DOCKER=1` forcé, le code généré s'exécute en natif. Risque faible (exercices algorithmiques, stdlib) mais non nul.
- `ollama_chat/` au lieu de `ollama/` (recommandé par aider ; `ollama/` passe par `/api/generate` avec un formatage de prompt maison).
- **Anglais forcé** : sous Windows, aider détecte la locale et ajoute "Reply in French" à chaque prompt. `bench_harness.py` force l'anglais pour rester comparable aux résultats publiés.
- **`num_ctx` fixe** : sinon aider le recalcule à chaque requête et Ollama recharge le modèle, ce qui fausse les temps.
- **`num_predict` plafonné** : pendant la mise au point, un petit modèle a généré **66 457 tokens en boucle** (Ollama décale le contexte et ne s'arrête jamais) ; sans plafond, le harnais attend jusqu'à 24 h. Le test qui a révélé ça a aussi ralenti le 7B (46 au lieu de 81 tok/s) : run jeté et relancé.
- Format `whole` pour le benchmark (conseil aider pour modèles locaux), `diff` pour les tâches maison (vrais fichiers).
- Tests pytest avec timeout de 3 min : un code qui boucle coûte 3 min par essai (vu sur two-bucket).
- Bug du harnais sous Windows (split sur `/`) : sans effet sur des dossiers neufs.

Tâches maison :
- Clone neuf au commit figé, prompt identique en anglais, un seul message, pas d'auto-commit, timeout 30 min.
- Contexte : 32k pour les qwen2.5 (leur max), **64k pour le 35B** : à 32k il remplissait la fenêtre en réfléchissant avant de répondre (`truncated = 1`), relancé.
- **Timeout litellm de 600 s** : coupait les réponses lentes du 14B (8 192 tokens à ~13 tok/s = 640 s). Le runner passe maintenant `--timeout` ; feature × 14B relancée.
- Seule la tâche 2 donne à aider un `test_cmd` (pytest dans l'env conda `ads`, aider relance le modèle sur les échecs, 3 corrections max).
- Le clone a priorité sur l'install éditable d'ADS dans l'env `ads` (vérifié).
- Les tests qui ont besoin de `test/__test_files__` ne tournent pas dans les clones (données téléchargées à part) : tests de la feature non exécutés, refactor évalué avec les tests sans données (24 passent, identiques avant/après) plus une sonde.
- Asymétrie assumée : aider reçoit la liste des fichiers pertinents (`files` du task.yaml) ; Claude Code explore seul.
- Détecteur "contexte saturé" du runner initialement faux (le message aider est "exceeds the N token limit") : corrigé et recalculé sur tous les résultats.

## 4. Benchmark standardisé (Aider polyglot)

| Modèle | Outil | 1er essai | 2 essais | Temps / exercice | Durée |
|---|---|---|---|---|---|
| qwen2.5-coder 7B | aider | 4 % (1/25) | 8 % (2/25) | 17 s | ~15 min |
| qwen2.5-coder 14B | aider | 4 % (1/25) | 8 % (2/25) | 70 s | 30 min |
| qwen3.6 35B MoE | aider | 44 % (11/25) | 60 % (15/25) | 129 s | 60 min |
| **Sonnet 5** | **Claude Code** | **84 % (21/25)** | **96 % (24/25)** | 16 s | **7 min** |

Tokens générés côté local : 25k (7B), 46k (14B), 285k (35B) ; débits 59, 26 et 88 tok/s.
Sonnet : 104 tours au total, ~1,89 $ d'équivalent API (en pratique consommé sur le quota de l'abonnement, pas facturé), 3 exercices réussis au 2e essai (forth, list-ops, transpose), 1 échec (dot-dsl).

**Réserve sur la comparaison Sonnet** : les modèles locaux passent par aider (formats d'édition `whole`/`diff`), Sonnet par Claude Code (agent avec ses propres outils). Mêmes exercices, mêmes consignes, même protocole à 2 essais, tests exécutés par le harnais, fichiers de test cachés au modèle pendant qu'il travaille. Mais l'outillage diffère, donc l'écart mesuré mélange la qualité du modèle et celle du harnais qui l'entoure. Pour une comparaison à outil identique, il faudrait rejouer aider avec `--model anthropic/claude-sonnet-5`, ce qui demande une clé API (~0,70 $).
Variance observée : dot-dsl échoue ici, mais passait au 2e essai lors d'un essai préalable à 2 exercices. Un seul run par modèle, donc ces scores ont une marge.

- 100 % de réponses bien formées pour les 3, 0 exception du harnais.
- 7B : réussit affine-cipher (1er essai), robot-name (2e). 14B : pig-latin (1er), affine-cipher (2e). Exemples d'échecs : "1 bottles" et lignes vides dans beer-song, `raise` dans un lambda (SyntaxError) dans forth, fonction `best_hands` renommée dans poker, boucles infinies (two-bucket).
- 35B : 11 au 1er essai, 4 de plus au 2e (dominoes, grade-school, list-ops, wordy). Il génère 11x plus de tokens que le 7B (raisonnement), mais reste le plus rapide en tok/s.
- Les "Traceback" vus dans la console pendant le run venaient du code des modèles (sortie pytest, lint aider), pas du harnais.

## 5. Tâches AxonDeepSeg

| Tâche | Base | Référence |
|---|---|---|
| 1. Ajouter `--allow-large-images` à `axondeepseg_morphometrics` | `bb108a4` | PR #1007 |
| 2. Réécrire `test_filter_morphometrics.py` | `cba1c42` | tests d'Armand (PR #1005) |
| 3. Expliquer le pipeline filter + count | `cba1c42` | code + PR #1005 |
| 4. Bug #1003 (masque axonmyelin manquant, symptôme seulement) | `bb108a4` | fix dans PR #1005 |
| 5. Refactor : centraliser la gestion des grandes images (5 fichiers) | `cba1c42` | aucune (3 PRs de correctif sur ce code : #974, #988, #1007) |

Pour éviter le doublon avec la tâche 1, le bug #1006 (crash morphometrics sur grande image) n'a pas été repris ; #1003 est un vrai bug distinct, fermé le jour même.

### Synthèse (ma revue ; les champs `review` des JSON restent à remplir)

| Tâche | 7B | 14B | 35B | Sonnet |
|---|---|---|---|---|
| 1. Feature | ❌ rien appliqué | ❌ casse la CLI | ✅ 1 défaut | ✅ trouve un trou dans la PR |
| 2. Tests | ❌ fichier vide | ❌ fichier vide | ⚠️ 12/15 | ✅ 39/39, bat la référence |
| 2 bis. Tests, format `whole` | ⚠️ 12/15 puis dégradé | ⚠️ 10/13 | | |
| 3. Explication | ⚠️ générique | ⚠️ superficiel | ✅ 1 erreur | ✅ exacte, bug de doc trouvé |
| 4. Bug #1003 | ⚠️ fix dangereux | ✅ | ✅ | ✅ + corrige l'ordre |
| 5. Refactor | ❌ rien appliqué | ❌ rien appliqué | ⚠️ 2 régressions | ✅ aucune régression |

| Métriques locales | 7B | 14B | 35B |
|---|---|---|---|
| Temps total | 15 min | 15 min | 22 min |
| Appels LLM | 11 | 9 | 10 |
| Erreurs de format d'édition | 8 | 4 (+8 SEARCH ratés) | 3 |

### Tâche 1 : feature `--allow-large-images`

Piège principal : `generate_and_save_colored_image_with_index_numbers` appelle `Image.open()` directement et contourne `ads_utils`.

- **7B** (549 s, 4 appels) : chaque réponse atteint le plafond de 8 192 tokens (il déroule ou boucle), donc tronquée et hors format. Historique qui grimpe à 70k tokens pour une fenêtre de 32k. Abandon après 3 corrections, **aucune modification**.
- **14B** : premier essai coupé par le timeout litellm (réponses arrivant exactement toutes les 600 s). Relancé (369 s, 4 appels, 8 SEARCH/REPLACE qui ne matchent pas) : ajoute le flag et le passe à `load_mask(..., allow_large_images=...)` **sans changer la signature de `load_mask`**. Vérifié : `TypeError: load_mask() got an unexpected keyword argument 'allow_large_images'` dès le premier masque, donc **`axondeepseg_morphometrics` plante pour tout le monde, même sans le flag**. Mode nerve oublié. Faux correctif dans postprocessing (`Image.open(path, mode='r')` ne change rien). Pire que ne rien faire.
- **35B** : premier essai à 32k raté (prompt ~25k tokens, raisonnement qui remplit la fenêtre, réponse vide, solution écrite dans le "thinking"). À 64k (236 s, 2 appels) : propagation complète (image, prédiction, les 3 modes de `load_mask` dont nerve, appel postprocessing). CLI vérifiée : `-l, --allow-large-images` dans `-h`, pas de conflit. Défaut : `Image.MAX_IMAGE_PIXELS = None` **global et jamais restauré** dans postprocessing, ce qui désactive toute protection PIL pour le reste du process (la PR #1007 passe par `ads.imread`). Raccourci `-l` non demandé. Test postprocessing malin (limite abaissée à 100 px pour forcer l'erreur) ; test CLI qui ne vérifie pas l'effet du flag.

### Tâche 2 : réécrire les tests du filtrage

- **7B et 14B (format `diff`)** : suite plausible écrite dans un simple bloc ```python, sans le SEARCH vide qu'aider exige pour créer un fichier. Aider prend ça pour du texte : **fichier créé vide**, 1 seul appel. Le 14B conclut "Please review the proposed changes". Le test `main()` du 7B écrivait en plus du CSV dans un `.xlsx` et attendait une sortie `_filtered` en passant `-o` : il aurait échoué.
- **Contrôle format `whole`** : 7B, 15 tests dont **12 passent** au premier jet, puis ses 3 corrections **dégradent** la suite (état final : 9 tests, 8 OK, 1 échec, 9 erreurs). 14B, 13 tests, 10 passent, bloqué à 3 échecs sur 4 essais (631 s), et crée un fichier hors périmètre (`test/test_config.yaml`).
- **35B** (565 s, 3 appels) : 15 tests, **12 passent**. Premier appel hors format (16k tokens reçus). Il diagnostique correctement 2 des 3 échecs (loguru n'écrit pas dans le `caplog` de pytest ; Armand utilise `unittest.mock.patch`), puis **boucle dans son raisonnement** ("`caplog.text`? No." des dizaines de fois) jusqu'au plafond de 16k : réponse vide. 3e échec : test `main()` qui nomme mal ses fichiers uaxon ("Found 0 unmyelinated files").
- **Mutation testing** (4 mutations : `>` en `>=` sur solidity, `<` en `<=` sur area, bornes g-ratio, suppression du `+1`) : tests du 35B, 1/4 détectée (g-ratio) ; **tests de référence d'Armand, 1/4 aussi** (voir §8).

### Tâche 3 : expliquer filter + count

- **7B** (18 s) : structure correcte, contenu générique, aucune règle précise, pièges banals, et une justification inventée ("le mode masque sert quand les xlsx sont trop gros").
- **14B** (60 s) : correct, organisé (règles, fallback watershed si la carte d'instances manque, priorité des `_filtered`, chaînage), pas d'hallucination, mais superficiel (ni comparaisons strictes, ni `+1`, ni seuil `0`), pièges génériques.
- **35B** (80 s) : de loin le plus précis. `~` désactive la règle via `if threshold:`, comparaisons strictes, `+1` expliqué (labels 1-indexés), fallback watershed, seuil `> 200`, fragilité de `df.iloc[:, 0]`, et un vrai piège qu'aucun autre n'a vu : fichiers uaxon dérivés par `replace('_axon_', '_uaxon_')`, donc traités seulement s'il existe un fichier axon. **Une affirmation fausse, énoncée avec aplomb** : "merge_masks écrase l'axonmyelin d'origine même sans `--overwrite`". Faux : sans `-o` la sortie est `..._seg-axonmyelin_filtered.png`. Autre affirmation douteuse : "input stem dependency" (les masques sont exclus de la découverte, il n'y a pas de mauvais stem).
- Manqués par les trois : seuil `0` traité comme désactivé, axones qui se touchent comptés comme un seul en mode masque, crash du mode xlsx si le fichier axon est absent, `replace('axon', 'axonmyelin')` dans `merge_masks` (voir §8).

### Tâche 4 : bug #1003

- **7B** (10 s) : bonne ligne, mais **supprime la condition** : `merge_masks(new_masks[0], new_masks[1])` appelé pour tous les modèles, donc IndexError sur un modèle 1 classe ou fusion des mauvais masques sur un modèle sans axon/myelin. Variable `is_axonmyelin_seg` laissée morte.
- **14B** (23 s) : correct (`'axon' in output_classes and 'myelin' in output_classes` dans le `if`), variable morte.
- **35B** (41 s) : correct et propre, modifie la définition de `is_axonmyelin_seg` comme Armand.
- Aucun modèle local n'a relevé la dépendance à l'ordre `new_masks[0]` / `[1]`.

### Tâche 5 : refactor large-images

- **7B** (297 s) : 4 réponses hors format, rien appliqué.
- **14B** (382 s) : blocs SEARCH/REPLACE plausibles pour les 5 fichiers, mais la réponse mentionne `pyproject.toml` ; aider ajoute ce fichier au chat et, dans ce cas, **n'applique pas les édits** et redonne la main ; le modèle répond "Ok, I will proceed" sans bloc. Rien appliqué. Piège d'interaction modèle / outil.
- **35B** (401 s, 5 fichiers) : context manager correct (`@contextmanager` + try/finally) dans `imread` et `get_imshape`, helper argparse dans les 3 CLI, limite PIL restaurée dans `apply_model` (corrige le bug existant). **Deux régressions**, vérifiées avec une sonde (faux prédicteur nnU-Net) :

  | | env `ADS_ALLOW_LARGE_IMAGES` pendant (flag off) | env après | limite PIL après (flag on) |
  |---|---|---|---|
  | code d'origine | absent | nettoyé | 1 000 000 000 (jamais restaurée) |
  | refactor 35B | **`1`** | **`1` (fuite)** | 89 478 485 (restaurée) |

  Variable d'env posée à chaque segmentation même sans le flag, jamais nettoyée, alors que le prompt demandait de garder sa gestion. **Les tests existants passent à l'identique avant et après.** Détails : import `_LARGE_IMAGE_PIXEL_LIMIT` inutile, aide "~1000 Mpx".

## 6. Claude Code sur backend local

- **Pas de proxy nécessaire** : Ollama (depuis 0.14) expose nativement l'API Anthropic `/v1/messages` ; `ANTHROPIC_BASE_URL=http://localhost:11434` suffit. Plus simple et plus robuste que LiteLLM ou claude-code-proxy.
- L'API Anthropic ne transmet pas `num_ctx` : variantes `-cc` créées par Modelfile (0 Go de disque en plus). `qwen2.5-coder-7b-cc` est en réalité à 32k (max natif).
- Windows PowerShell transformait l'avertissement stderr de Claude Code ("claude.ai connectors are disabled...") en erreur fatale : corrigé dans `claude-local.ps1`.
- Test (lire `stats.py`, ajouter `median()`) : **35B** réussit en 49 s via les outils de Claude Code ; **7B** répond "Done." en 12 s **sans aucun appel d'outil, fichier inchangé**.

## 7. Claude Code Sonnet (backend Anthropic)

Lancé avec `run_claude_code_tasks.py --model sonnet` : même clone, même prompt, `claude -p` headless, édits auto-acceptés, shell limité (python/pytest/git en lecture), env conda `ads` dans le PATH, réglages utilisateur (CLAUDE.md global) exclus via `--setting-sources project,local`. Aucune ressource locale nécessaire hormis les commandes que Claude lance. Coût affiché = équivalent API ; avec le login claude.ai, c'est le quota de l'abonnement qui est consommé.

Modèle effectivement utilisé : `claude-sonnet-5` (Claude Code s'appuie aussi sur `claude-haiku-4-5` pour de petites tâches internes). Run fait en deux fois (pause demandée après les tâches 1 et 4), chaque tâche sur un clone neuf.

| Tâche | Temps | Tours | Coût (équiv. API) | Verdict |
|---|---|---|---|---|
| 1. Feature | 398 s | 48 | 0,70 $ | ✅ trouve un trou dans la PR de référence |
| 2. Tests | 89 s | 8 | 0,23 $ | ✅ 39 cas, tous verts, 3/4 mutations détectées |
| 3. Explication | 95 s | 11 | 0,24 $ | ✅ exacte, 12 pièges dont un bug de doc réel |
| 4. Bug #1003 | 23 s | 10 | 0,28 $ | ✅ + corrige la dépendance à l'ordre |
| 5. Refactor | 106 s | 24 | 0,35 $ | ✅ aucune régression (sonde) |
| **Total** | **~12 min** | 101 | **~1,80 $** | 5/5 |

Pour comparer : le 35B local a mis 22 min pour 1 succès net, 2 partiels et 2 résultats avec défauts ; 7B et 14B, 15 min chacun pour au mieux 1 succès.

- **Tâche 1 (feature)** : 398 s, 48 tours, ~0,70 $, 6 fichiers. ✅ **Meilleur résultat, meilleur que la PR de référence.** Propagation complète, et **seul à trouver un trou dans la PR #1007** : en mode nerve, `compute_axon_density` (compute_morphometrics.py) relit le masque nerve avec `imread` sans le flag (voir §8). Dans postprocessing, relève la limite PIL temporairement avec try/finally et la restaure (le 35B la désactivait globalement). Tests plus rigoureux : échec sans le flag / succès avec (limite PIL abaissée à 500 000 px), espions sur `imread`, vérification que la limite est restaurée. A téléchargé lui-même les données de test (`download_tests()`) et fait tourner 91 tests. Explique pourquoi il a gardé `Image.open` et signale le dossier `data-testing-*` laissé à la racine.
- **Tâche 2 (tests)** : 33 fonctions de test (39 cas avec la paramétrisation), **toutes vertes** sur le code actuel. Mutation testing : **3/4 détectées** (solidity, area, g-ratio ; seul le `+1` de `mask_updater` passe), contre 1/4 pour les tests d'Armand et 1/4 pour le 35B. Le seul des 4 modèles à dépasser la référence.
- **Tâche 3 (explication)** : exacte sur tous les points vérifiés, dit qu'il n'a rien exécuté. Couvre tout ce que les locaux avaient manqué : seuil `0` traité comme désactivé, `replace('axon', 'axonmyelin')` dans `merge_masks` (et `merge_masks` qui lit sans `allow_large_images`), connectivité 4 (filter/morphometrics) contre 8 (count en mode masque), priorité d'un `_filtered.xlsx` périmé, `-i` non requis dans count (`TypeError`), YAML vide qui donne `AttributeError`. Deux trouvailles de fond : **l'exemple de config de la doc ne fonctionne pas** (vérifié, voir §8) et **relancer `-m -o` corrompt les masques uaxon** (la carte d'instances est recalculée sur le masque déjà écrasé, les IDs du xlsx ne correspondent plus).
- **Tâche 4 (bug #1003)** : 23 s, 10 tours, ~0,28 $. Correctif identique à celui d'Armand (`{'axon', 'myelin'} <= set(output_classes)`) **et seul modèle à corriger la dépendance à l'ordre** (`new_masks[output_classes.index('axon')]`). Dit explicitement ce qu'il n'a pas vérifié (pas de test lancé, pas de modèle 3 classes).
- **Tâche 5 (refactor)** : context manager et helper argparse comme demandé, variable d'env gardée sous `if allow_large_images` et nettoyée. Il remarque que la lecture finale de la prédiction brute de nnU-Net dépendait de la limite relevée (ce que le 35B n'avait pas vu) et enveloppe donc toute la fonction. Garde le texte d'aide propre à chaque CLI (paramètre `help`), retire les imports devenus inutiles, conseille `git diff -w` pour la ré-indentation. Sonde : aucune variable d'env sans le flag, nettoyée après, limite PIL restaurée. Tests existants identiques à la base. Il a vérifié son context manager à part car les tests d'`ads_utils` ne tournent pas sans les données.

Comportements communs : répond systématiquement avec ce qu'il a vérifié et ce qu'il n'a pas vérifié, n'a jamais affirmé de faux, explore le repo au-delà des fichiers cités (compute_morphometrics.py, docs), lance les tests quand c'est possible (et va chercher les données de test si besoin).

## 8. Trouvailles annexes sur le code d'ADS

À remonter à l'équipe, indépendamment du benchmark :
1. **PR #1007 (`--allow-large-images` pour morphometrics) incomplète** : en mode nerve, `launch_morphometrics_computation` appelle `compute_axon_density(...)` (l. 408 à `964b6a9`), qui fait `imread(nerve_mask_path)` sans `allow_large_images` (compute_morphometrics.py l. 685). Une grande image en mode nerve plante encore malgré le flag. Trouvé par Sonnet ; correctif dans `work/task_01_add_feature/claude-sonnet/repo`.
2. **Doc du filtrage (PR #1005) fausse** : l'exemple de config de `docs/source/documentation.rst` (l. 711-717) écrit les règles comme un dictionnaire (`valid-g-ratio-only: True`) alors que le code attend une liste (`- valid-g-ratio-only: True`). Vérifié : avec l'exemple de la doc, **rien n'est filtré**, pas même les g-ratios invalides, seulement des warnings "Unknown rule". Trouvé par Sonnet.
3. **Relancer `axondeepseg_filter -m -o` corrompt les masques uaxon** : la carte d'instances uaxon est recalculée à partir du masque déjà écrasé, donc renumérotée, et les IDs du xlsx ne correspondent plus (analyse de Sonnet, non testée).
4. **Tests du filtrage (PR #1005)** : le test "strict comparisons" ne teste pas isolément les frontières `solidity` et `axon_area` (la ligne 0 est déjà éliminée par `axon-diam-gt`) ; le `+1` de `mask_updater` n'est couvert par aucun test. 3 mutations sur 4 passent inaperçues.
5. **`apply_model.axon_segmentation`** relève `Image.MAX_IMAGE_PIXELS` à 1e9 avec `--allow-large-images` et ne le restaure jamais (vérifié avec la sonde). C'est la motivation du refactor de la tâche 5.
6. **`merge_masks`** construit le nom de sortie avec `path_axon.name.replace('axon', 'axonmyelin')` : une image dont le nom contient "axon" voit toutes les occurrences remplacées.
7. **`filter_morphometrics`** : un seuil `0` est traité comme "règle désactivée" (`if threshold:`) ; les fichiers uaxon ne sont trouvés que via `replace('_axon_', '_uaxon_')` sur les fichiers axon.
8. **`apply_model`** : `merge_masks(new_masks[0], new_masks[1])` suppose qu'axon et myelin sont les 2 premières classes après tri (corrigé par Sonnet dans la tâche 4, pas dans le fix d'Armand).
9. **`count_axons`** en mode masque : les axones qui se touchent forment une seule composante connexe et sont comptés comme un seul.

## 9. Enseignements pour la présentation

0. **Sur le banc standardisé, Sonnet fait 96 % contre 60 % pour le meilleur local**, en 7 min contre 60, sans mobiliser la machine. Et **5/5 sur les tâches ADS en ~12 min pour ~1,80 $, sans ressource locale**, et meilleur que les références humaines sur 3 tâches (trou dans la PR #1007, tests plus stricts que ceux d'Armand, bug de doc trouvé). Le meilleur local (35B) : 22 min de GPU, 1 succès net, et des régressions silencieuses. L'écart qualitatif est bien plus grand que ce que suggère le benchmark polyglot.
1. **La génération compte plus que la taille.** 7B et 14B (2024) font jeu égal et médiocre (8 %) ; le 35B MoE (2026) fait 60 % et c'est le seul local qui livre sur les vraies tâches ADS. Il tourne plus vite que le 14B sur une carte à 16 Go.
2. **Les petits modèles échouent surtout sur l'outillage** : format d'édition, fichier vide, contexte saturé, timeouts, "Done." sans rien faire. Leur code n'est pas toujours absurde (12/15 tests du 7B en `whole`) mais n'arrive pas dans le repo.
3. **Les échecs dangereux sont silencieux** : la feature du 14B casse la CLI, le refactor du 35B passe tous les tests en changeant le comportement, le 35B affirme un faux piège avec aplomb. Relecture humaine obligatoire.
4. **Les modèles "thinking" locaux bouclent** : fenêtre remplie par le raisonnement, 16k tokens à tourner en rond. Sans plafond `num_predict`, Ollama ne s'arrête jamais.
5. **Le local demande beaucoup de réglages** : contexte, plafond de génération, timeouts, format d'édition, langue. Chaque réglage par défaut a produit un échec qui n'avait rien à voir avec la qualité du modèle.
6. **Coût réel du local** : 0 $ mais ~2 h de machine pour le banc complet, machine indisponible pendant ce temps, et un run tué faute de RAM.
7. Effet de bord utile : les tâches ont révélé de vrais trous dans les tests et le code d'ADS (§8).

## 10. Points ouverts

- Remplir les champs `review` des `results/custom_*.json` après ta propre revue.
- Rejouer avec Opus : `run_claude_code_tasks.py --model opus` (tâches) et `run_claude_code_benchmark.py --model opus` (banc).
- Comparaison à outil identique : rejouer le banc avec aider et `--model anthropic/claude-sonnet-5` (clé API requise, ~0,70 $).
- Signaler à l'équipe ADS les trouvailles du §8 (trou dans la PR #1007, doc du filtrage, tests du filtrage).
- Sonnet n'a tourné qu'une fois par tâche : un 2e passage donnerait une idée de la variance.
- Télécharger `test/__test_files__` pour exécuter les tests de la feature (tâche 1) dans les clones.
- Optionnel : essayer `qwen3.5:9b` comme palier léger 2026, et le format `whole` sur toutes les tâches pour les qwen2.5.
- Isolation Docker du benchmark si tu veux le rejouer à l'identique des conditions upstream.
