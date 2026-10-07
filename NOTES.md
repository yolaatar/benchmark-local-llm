# Banc de test : LLM codeurs locaux (Ollama) vs Claude Code

Machine : Windows 11, RTX 5060 Ti 16 Go (driver 591.86), 32 Go RAM, 206 Go libres sur C: au départ.
Mis en place le 2026-09-18.

## TL;DR

```powershell
cd benchmark-local-llm
.\run_all.ps1                 # VRAM + benchmark Aider (25 exos x 3 modèles) + tâches maison
.\claude-local.ps1            # Claude Code sur qwen3.6 35B local (claude tout court = backend Anthropic normal)
```

Suite (serveur partagé sur tassan, harnais OpenCode / Claude Code, multi-utilisateurs) : `LAB_BRIEF.md` (synthèse pour la présentation) et `lab_server/PLAN.md` (runbook + scripts). Test de charge : `concurrency_bench.py`.

Résultats : `results/aider_benchmark_<modele>.json`, `results/custom_<tache>_<modele>.json`, `results/vram_*.json`, logs dans `results/logs/`.

---

## 1. Installation

| Composant | Version | Comment |
|---|---|---|
| Ollama | 0.34.2 | `winget install Ollama.Ollama`, binaire dans `%LOCALAPPDATA%\Programs\Ollama` (pas dans le PATH des shells déjà ouverts) |
| Python | 3.12.10 | déjà installé (`%LOCALAPPDATA%\Programs\Python\Python312`), `python` n'est pas dans le PATH |
| Aider | 0.86.2 | `.venv` dédié : `python -m venv .venv` puis `pip install aider-chat` |
| Harnais benchmark | tag `v0.86.2` du repo aider | `vendor/aider`, aligné sur la version installée |
| Exercices | `Aider-AI/polyglot-benchmark` @ `7e0611e` | `vendor/polyglot-benchmark` |

Dépendances figées dans `requirements.lock.txt` (`pip install -r requirements.lock.txt` pour recréer le venv).

**Validation GPU** : `qwen2.5-coder:0.5b` chargé à 100 % en VRAM (`/api/ps` : `size_vram == size`), GPU à 87 % d'utilisation, ~450 tok/s. Ollama tourne bien sur CUDA, pas sur CPU.

Incidents rencontrés :
- `pip install -e vendor/aider` échoue : litellm récent contient des chemins > 260 caractères et Windows Long Paths n'est pas activé. Contourné en utilisant le paquet `aider-chat` 0.86.2 et en positionnant le repo aider sur le tag `v0.86.2` (pas besoin de toucher au registre). L'install ratée avait monté des versions de dépendances, elles ont été re-épinglées (`pip check` propre).
- `ollama search` n'existe pas dans le CLI : recherche faite sur ollama.com/library.

## 2. Modèles retenus

Recherche sur ollama.com/library le 2026-09-18. Constat : chez Qwen, **il n'existe pas de modèle "coder" plus récent que qwen2.5-coder dans les paliers 7B et 14B**. Les générations récentes (qwen3-coder, qwen3-coder-next, variantes `-coding` de qwen3.6) n'existent qu'en 27B et plus.

| Palier | Modèle Ollama | Archi | Téléchargement | VRAM réelle (ctx 16k) | Répartition | Génération | Prompt |
|---|---|---|---|---|---|---|---|
| Léger | `qwen2.5-coder:7b` | dense 7.6B, Q4_K_M | 4,7 Go | 5 483 Mio | 100 % GPU | 81 tok/s | ~3 500 tok/s |
| Moyen | `qwen2.5-coder:14b` | dense 14.8B, Q4_K_M | 9,0 Go | 11 545 Mio | 100 % GPU | 41 tok/s | ~1 700 tok/s |
| Haut | `qwen3.6:35b-a3b-coding` | MoE 35.5B / 3B actifs, Q4_K_M | 22 Go | 14 392 Mio (+ ~9 Go en RAM) | 59 % GPU / 41 % CPU | 68 à 89 tok/s | ~970 tok/s |

VRAM mesurée avec `nvidia-smi` pendant une génération réelle (pic moins la VRAM déjà utilisée par Windows, ~1,4 Go), script `measure_vram.py`, détails dans `results/vram_*.json`.

**Contexte maximum** : qwen2.5-coder 7B et 14B sont limités à 32k par construction (Ollama plafonne `num_ctx` au `context_length` natif) ; qwen3.6 monte à 256k. Tâches maison : 32k pour les qwen2.5, 64k pour le 35B (à 64k : 14 481 Mio en VRAM, 54 % GPU, 90 tok/s). À 32k le 35B échouait : son raisonnement remplissait la fenêtre avant la réponse.

À 32k de contexte :

| Modèle | VRAM (ctx 32k) | Répartition | Génération |
|---|---|---|---|
| qwen2.5-coder:7b | 6 432 Mio | 100 % GPU | 81 tok/s |
| qwen2.5-coder:14b | 14 120 Mio | 93 % GPU (déborde un peu) | 33 tok/s (-20 %) |
| qwen3.6:35b-a3b-coding | 14 420 Mio | 58 % GPU | 86 tok/s |

### Pourquoi `qwen3.6:35b-a3b-coding` pour le palier haut

- C'est la variante MoE récente (publiée il y a ~2 semaines) que tu évoquais, avec un tag `-coding` dédié ("agentic coding").
- MoE à 3B paramètres actifs : même avec 41 % du modèle en RAM, la génération reste à ~70-89 tok/s, **plus rapide que le 14B dense qui tient entièrement en VRAM**. Un dense 32B (`qwen2.5-coder:32b`, ~20 Go) déborderait aussi, mais chaque token passerait par les couches en RAM : beaucoup plus lent.
- Le cache KV grossit très peu avec le contexte (archi hybride) : passer de 16k à 32k ne change presque rien.
- Modèle "thinking" : il raisonne avant de répondre (laissé activé, c'est son mode normal ; plus lent mais c'est aussi ce que fait Claude).

Alternatives écartées :
- `qwen3-coder-next` (80B MoE, **52 Go** en Q4) : ne tient pas dans 16 Go VRAM + 32 Go RAM.
- `qwen3-coder:30b` (MoE 3B actifs, 19 Go) : tiendrait un peu mieux, mais génération précédente (11 mois).
- `qwen3.6:27b-coding` (dense, 18 Go) : dense et plus gros que la VRAM, donc offload lent.
- `qwen3.5:9b` (6,6 Go) : plus récent que qwen2.5-coder:7b mais généraliste, pas "coder". Bon candidat si tu veux un palier léger de génération 2026 : ajoute-le dans `bench_config.MODELS` + les deux `aider_model_settings*.yml`.

**Point à mentionner en présentation** : les paliers 7B/14B sont de génération 2024, le 35B de génération 2026. L'écart entre paliers mélange donc taille *et* génération.

### RAM

Au moment des tests, seuls ~8 Go de RAM étaient libres (League of Legends, Riot, Discord, Brave, VS Code ouverts). Le 35B met ~9 Go en RAM : **ferme les jeux/navigateurs avant un run** pour des temps stables. `run_all.ps1` avertit sous 10 Go libres.

## 3. Arborescence

```
benchmark-local-llm/
  NOTES.md                         ce fichier (mode d'emploi)
  RAPPORT.md                       résultats, observations et remarques
  run_all.ps1                      point d'entrée unique (modèles locaux)
  run_aider_benchmark.py           étape 4
  run_custom_tasks.py              étape 5 (+ prepare/collect pour un rejeu manuel)
  run_claude_code_tasks.py         mêmes tâches avec Claude Code (Sonnet/Opus), headless
  run_claude_code_benchmark.py     même banc polyglot avec Claude Code, headless
  claude-local.ps1                 étape 6
  measure_vram.py                  mesures VRAM / débit
  bench_config.py                  liste des modèles, chemins, env commun
  bench_harness.py                 wrapper du harnais aider (force l'anglais)
  aider_model_settings.yml         settings Aider benchmark (ctx 16k)
  aider_model_settings_custom.yml  settings Aider tâches maison (ctx 32k qwen2.5, 64k qwen3.6)
  claude_code_local/Modelfile.*    variantes à contexte fixe pour Claude Code en local
  custom_tasks/task_0X_*/          README.md + task.yaml par tâche
  results/                         JSON de résultats + logs/
  vendor/aider, vendor/polyglot-benchmark
  tmp.benchmarks/                  dossiers de travail du harnais (un par run)
  work/                            clones de travail des tâches maison
```

## 4. Benchmark standardisé (Aider polyglot, sous-ensemble Python)

```powershell
.\.venv\Scripts\python.exe run_aider_benchmark.py                          # 3 modèles
.\.venv\Scripts\python.exe run_aider_benchmark.py --models qwen2.5-coder:7b
.\.venv\Scripts\python.exe run_aider_benchmark.py --resume                 # reprend les derniers runs
.\.venv\Scripts\python.exe run_aider_benchmark.py --num-exercises 3        # test rapide
```

- **Sous-ensemble** : 25 des 34 exercices Python du polyglot, tirés avec `random.Random(42)` (reproductible) :
  affine-cipher, beer-song, book-store, bottle-song, bowling, dominoes, dot-dsl, food-chain, forth, grade-school, hangman, list-ops, pig-latin, poker, react, rest-api, robot-name, sgf-parsing, simple-linked-list, transpose, two-bucket, variable-length-quantity, wordy, zebra-puzzle, zipper.
  Exclus : connect, go-counting, grep, paasio, phone-number, pov, proverb, scale-generator, tree-building.
- **Protocole aider standard** : 2 essais par exercice ; au 2e essai le modèle voit la sortie pytest. `pass_rate_1` = réussi du premier coup, `pass_rate_2` = réussi en au plus 2 essais.
- **Attention à l'échelle** : le polyglot regroupe les exercices Exercism *les plus durs* (ceux que la plupart des modèles ratent). Des scores bas pour 7B/14B sont normaux ; sur le polyglot complet, qwen2.5-coder-32b fait autour de 16 %.
- Sortie : `results/aider_benchmark_<modele>.json` (taux de réussite, liste réussis/ratés, temps total et par exercice, tokens envoyés/reçus, tok/s, réponses mal formées, timeouts de tests, détail par exercice). Coût : 0 $ en local, champ gardé pour comparer.

### Choix et écarts par rapport au harnais upstream (à assumer en présentation)

1. **Pas de Docker** : le harnais exige `AIDER_DOCKER` parce qu'il exécute du code écrit par le LLM sans relecture. Docker/WSL ne sont pas installés sur cette machine ; le runner pose `AIDER_DOCKER=1` et tourne en natif. Risque jugé faible (exercices algorithmiques, prompt "standard library only") mais non nul. Si tu veux l'isolation : installer Docker Desktop (WSL2, redémarrage), puis lancer le harnais dans le conteneur `benchmark/docker.sh`.
2. **`ollama_chat/` au lieu de `ollama/`** : `ollama/` passe par `/api/generate` avec un formatage de prompt fait par litellm ; `ollama_chat/` utilise `/api/chat` et le template de chat du modèle. C'est ce que recommande la doc aider.
3. **Anglais forcé** : sous Windows, aider détecte la locale (français) et ajoute "Reply in French" à chaque prompt. `bench_harness.py` force l'anglais pour rester comparable aux résultats publiés ; les tâches maison passent `--chat-language English`.
4. **`num_ctx` fixe** (16k benchmark, 32k tâches maison) : par défaut aider recalcule `num_ctx` à chaque requête, ce qui fait **recharger le modèle** par Ollama et pollue les temps.
5. **`num_predict` plafonné** (8192 ; qwen3.6 : 12288 en benchmark, 16384 en tâches maison) : Ollama ne s'arrête jamais sur un modèle qui boucle (il décale le contexte). Observé pendant la mise au point : 66 457 tokens générés en boucle par un petit modèle. Sans plafond, le harnais attendrait jusqu'à 24 h.
6. **Format d'édition `whole`** pour le benchmark (conseil du README aider pour les modèles locaux, exercices mono-fichier) et **`diff`** pour les tâches maison (fichiers réels trop gros pour être réécrits en entier).
7. Tests exécutés avec un timeout de 3 min (valeur du harnais) : un code qui boucle coûte 3 min par essai.

Durée observée : voir section Résultats.

### Le même banc avec Claude Code

```powershell
.\.venv\Scripts\python.exe run_claude_code_benchmark.py --model sonnet
```

Mêmes exercices, mêmes consignes (celles du harnais aider), même protocole à 2 essais, tests exécutés par le script. Tourne sur ton quota d'abonnement, sans clé API ni ressource locale. Les fichiers de test sont **cachés pendant que le modèle travaille** et restaurés pour le scoring, sinon Claude Code les lirait (les modèles locaux ne les voyaient pas non plus). Outils autorisés : lecture, édition, et `python` mais pas `pytest`. Sortie : `results/claude_benchmark_<modele>.json`.

Réserve : Claude Code est un agent avec ses propres outils, aider utilise des formats d'édition. L'écart mesuré mélange donc modèle et outillage. Pour une comparaison à outil identique, il faut une clé API et `run_aider_benchmark.py` avec un modèle `anthropic/...`.

## 5. Tâches maison

Les 5 tâches, toutes sur AxonDeepSeg (clone local, commits figés) :

| Tâche | Base | Référence |
|---|---|---|
| 1. Ajouter `--allow-large-images` à `axondeepseg_morphometrics` | `bb108a4` | PR #1007 |
| 2. Réécrire `test_filter_morphometrics.py` (supprimé avant le run, aider lance pytest après chaque édit) | `cba1c42` | tests d'Armand, PR #1005 |
| 3. Expliquer le pipeline filter + count (mode `ask`) | `cba1c42` | code + description PR #1005 |
| 4. Bug #1003 : masque axonmyelin manquant avec un modèle 3 classes (symptôme seulement) | `bb108a4` | fix dans PR #1005 |
| 5. Refactor : centraliser la gestion des grandes images dans `ads_utils` (5 fichiers) | `cba1c42` | pas de référence upstream |

Les tests ADS s'exécutent avec l'env conda `ads` (`C:\Users\Youssef\miniconda3\envs\ads\python.exe -m pytest ...` depuis la racine du clone, qui a priorité sur l'install éditable). Les tests qui ont besoin de `test/__test_files__` ne tournent pas dans les clones (données à télécharger).

Chaque dossier `custom_tasks/task_0X_*/` contient :
- `README.md` : objectif, critères de revue manuelle, commandes pour rejouer avec Claude Code ;
- `task.yaml` : la spec lue par le runner. **À remplir** avec les détails ADS / Erudi, puis `status: ready`.

Champs de `task.yaml` : `repo` (chemin local ou URL git), `base_ref` (commit SHA de départ, identique pour tous), `mode` (`code` = aider modifie des fichiers, `ask` = réponse seule), `files` (fichiers ajoutés au chat), `read_only`, `test_cmd` optionnel (lancé par aider après chaque édit, utiliser le Python de l'env du dépôt, pas celui du `.venv`), `setup_cmds`, `map_tokens`, `prompt`.

Conseils pour les remplir :
- `base_ref` figé : tout le monde part exactement du même état.
- Tâche "trouver un bug" : prendre un bug déjà corrigé dans l'historique et partir du commit *avant* le fix. Le vrai commit sert de corrigé.
- Prompt en anglais, auto-suffisant, identique pour les modèles locaux et Claude Code.
- Ne pas trop guider sur les fichiers si l'objectif est de tester la navigation dans le repo : aider a une repo map, Claude Code explore seul. Lister dans `files` ce qu'un humain donnerait naturellement.

```powershell
.\.venv\Scripts\python.exe run_custom_tasks.py --list
.\.venv\Scripts\python.exe run_custom_tasks.py                                   # toutes les tâches prêtes x 3 modèles
.\.venv\Scripts\python.exe run_custom_tasks.py --tasks task_04_find_bug --models qwen3.6:35b-a3b-coding
```

Option `--edit-format whole` : rejoue avec un autre format d'édition, résultats suffixés `-whole` (utilisé comme contrôle sur la tâche 2).

Pour chaque (tâche, modèle) : clone neuf du dépôt au `base_ref` dans `work/<tache>/<modele>/repo`, aider en non-interactif (`--message-file`, `--yes-always`, pas d'auto-commit), timeout de 30 min (aussi passé à aider via `--timeout`, sinon litellm coupe les requêtes à 600 s), puis `results/custom_<tache>_<modele>.json` avec : diff complet et fichiers touchés, temps écoulé, nombre d'appels LLM (1 = du premier coup ; au-delà ce sont les boucles automatiques d'aider : édit mal formé, lint, tests), tokens, réponse finale (tâches `ask`), et un champ `review` à remplir à la main. Le clone de travail est conservé pour inspecter le résultat.

Validé sur une tâche de démo (hors `custom_tasks/`) : édit appliqué et diff capturé, réponse `ask` capturée, timeout et flux manuel fonctionnels.

## 6. Rejouer les 5 tâches avec Claude Code (Sonnet / Opus)

**Automatique (recommandé)** : clone neuf au même commit, même prompt, `claude -p` headless, résultats au même format (`results/custom_<tache>_claude-<modele>.json`, avec en plus le nombre de tours et le coût). Tourne sur les serveurs d'Anthropic : pas besoin de GPU ni de RAM libre.

```powershell
.\.venv\Scripts\python.exe run_claude_code_tasks.py --model sonnet
.\.venv\Scripts\python.exe run_claude_code_tasks.py --model opus
.\.venv\Scripts\python.exe run_claude_code_tasks.py --model opus --tasks task_04_find_bug
```

Réglages : édits auto-acceptés (`--permission-mode acceptEdits`), shell limité à python/pytest/git en lecture/ls/cat, env conda `ads` en tête du PATH (Claude peut lancer les tests ADS), réglages utilisateur exclus (`--setting-sources project,local`, ton CLAUDE.md global n'influence pas le test). Coût affiché = équivalent API ; avec ton login claude.ai c'est le quota de l'abonnement qui est consommé.

**Manuel** (session interactive, même point de départ et même format de sortie) :

```powershell
# 1. clone neuf au base_ref + affichage du prompt
.\.venv\Scripts\python.exe run_custom_tasks.py --prepare-manual claude-sonnet --tasks task_01_add_feature

# 2. session Claude Code normale (backend Anthropic) dans le clone
cd work\task_01_add_feature\claude-sonnet\repo
claude --model sonnet            # ou --model opus, avec le label claude-opus aux étapes 1 et 3
#    coller le prompt, laisser travailler, chronométrer, compter les messages que TU envoies

# 3. capture du diff dans results/custom_task_01_add_feature_claude-sonnet.json
cd ..\..\..\..
.\.venv\Scripts\python.exe run_custom_tasks.py --collect-manual claude-sonnet --tasks task_01_add_feature --elapsed 312 --messages 1
#    tâches "ask" : coller la réponse dans un fichier et ajouter --answer-file reponse.md
```

Pour que la comparaison reste juste :
- un seul message (le prompt) si possible, comme pour aider ; si tu relances Claude, le compter dans `--messages` ;
- ne pas ajouter de contexte qu'aider n'a pas eu (pas de CLAUDE.md dans le clone, pas d'aide supplémentaire) ;
- noter aussi le coût affiché par `/cost` en fin de session dans `review.notes`.

## 7. Claude Code sur backend local

**Pas de proxy nécessaire** : depuis la v0.14, Ollama expose nativement l'API Anthropic Messages (`/v1/messages`), vérifié ici sur 0.34.2. Claude Code s'y branche en changeant simplement `ANTHROPIC_BASE_URL`. C'est plus simple et plus robuste que LiteLLM ou claude-code-proxy (un process et un point de panne en moins). Si tu veux quand même un proxy (pour journaliser les requêtes par exemple), LiteLLM s'ajoute facilement.

Comme l'API Anthropic ne permet pas de passer `num_ctx`, des variantes à contexte élargi sont créées à partir de `claude_code_local/Modelfile.*`. Elles réutilisent les mêmes poids : 0 Go de plus sur le disque.

| Variante | Base | Contexte |
|---|---|---|
| `qwen3.6-35b-cc` | qwen3.6:35b-a3b-coding | 64k |
| `qwen2.5-coder-7b-cc` | qwen2.5-coder:7b | 32k (son maximum natif) |
| `qwen2.5-coder-14b-cc` | qwen2.5-coder:14b | 32k (à 64k il déborderait fortement en RAM) |

### Basculer

**Claude Code normal** (backend Anthropic, ton login claude.ai) :
```powershell
claude
```

**Claude Code sur backend local**, version script (les variables ne vivent que le temps de la session, puis sont restaurées) :
```powershell
.\claude-local.ps1                # qwen3.6 35B
.\claude-local.ps1 -Model 7b      # ou 14b
```

**Version manuelle**, dans un terminal PowerShell dédié :
```powershell
$env:ANTHROPIC_BASE_URL   = "http://localhost:11434"
$env:ANTHROPIC_AUTH_TOKEN = "ollama"
$env:ANTHROPIC_API_KEY    = ""
$env:ANTHROPIC_DEFAULT_HAIKU_MODEL = "qwen3.6-35b-cc"   # appels "petit modèle" en arrière-plan
claude --model qwen3.6-35b-cc
```
Retour au normal : fermer ce terminal, ou
```powershell
Remove-Item Env:ANTHROPIC_BASE_URL, Env:ANTHROPIC_AUTH_TOKEN, Env:ANTHROPIC_DEFAULT_HAIKU_MODEL -ErrorAction SilentlyContinue
```

Alternative officielle Ollama : `ollama launch claude --model qwen3.6-35b-cc`.

Vérifié le 2026-09-18 avec `.\claude-local.ps1 -Model 35b -- -p "Read stats.py, then add a function median(values) to it." --permission-mode acceptEdits` : le 35B lit le fichier et ajoute un `median()` correct via les outils de Claude Code en 49 s ; `ANTHROPIC_BASE_URL` est bien vidée ensuite. Le 7B répond "Done." en 12 s sans appeler d'outil (fichier inchangé) : pour Claude Code en local, seul le 35B est utilisable.

Claude Code affiche sur stderr "claude.ai connectors are disabled because ANTHROPIC_API_KEY or another auth source is set" : normal, c'est le token `ollama`. Le script neutralise `ErrorActionPreference` pendant l'appel, sinon Windows PowerShell transforme cet avertissement en erreur fatale.

## 8. Résultats

**Rapport complet (résultats, observations détaillées, remarques, trouvailles sur ADS) : `RAPPORT.md`.**

Benchmark polyglot (25 exercices Python, 2 essais) :

| Modèle | 1er essai | 2 essais | Temps / exercice | Durée totale |
|---|---|---|---|---|
| qwen2.5-coder:7b | 4 % | 8 % | 17 s | ~15 min |
| qwen2.5-coder:14b | 4 % | 8 % | 70 s | 30 min |
| qwen3.6:35b-a3b-coding | 44 % | 60 % | 129 s | 60 min |

Tâches ADS (ma revue, les champs `review` des JSON restent à remplir) :

| Tâche | 7B | 14B | 35B |
|---|---|---|---|
| 1. Feature | ❌ rien appliqué | ❌ casse la CLI | ✅ 1 défaut |
| 2. Tests | ❌ fichier vide | ❌ fichier vide | ⚠️ 12/15 |
| 3. Explication | ⚠️ générique | ⚠️ superficiel | ✅ 1 erreur |
| 4. Bug #1003 | ⚠️ fix dangereux | ✅ | ✅ |
| 5. Refactor | ❌ rien appliqué | ❌ rien appliqué | ⚠️ 2 régressions |

Durée réelle d'un run complet `run_all.ps1` : ~2 h (benchmark ~1 h 45, tâches maison ~50 min).
