# Site web GLACIORAIDE

Source du site https://glacioraide.github.io, construit avec [Quarto](https://quarto.org).

Le site présente le projet GLACIORAIDE (EDYTEM et LAPP) et les résultats de suivi des glaciers
suspendus. La page [Linceul](https://glacioraide.github.io/linceul.html) montre l'évolution de la
surface du glacier du Linceul, mesurée par une caméra automatique et le logiciel
[staketracker](https://github.com/glacioraide/staketracker).

## Organisation

Ce dépôt ne contient que le **cadre du site** et le **code d'analyse**. Les **résultats** ne sont
pas versionnés dans git : ils sont publiés comme *GitHub Releases* et récupérés au moment de la
construction du site.

```
photos (serveur)  ──pipeline.py──▶  paquet de résultats  ──publish_results.sh──▶  GitHub Release
                                                                                       │
site en ligne  ◀──déploiement Pages──  rendu Quarto  ◀──téléchargement──  workflow GitHub Actions
```

| Fichier | Rôle |
| --- | --- |
| `index.qmd`, `about.qmd`, `linceul.qmd` | Pages du site |
| `_quarto.yml`, `styles.css` | Configuration, menu et style |
| `assets/` | Logos |
| `analyses/linceul/config.toml` | Paramètres de l'analyse (périodes, zones de recherche, seuils…) |
| `analyses/linceul/pipeline.py` | Pipeline d'analyse : photos → paquet de résultats |
| `analyses/linceul/publish_results.sh` | Publication du paquet en GitHub Release |
| `.github/workflows/publish.yml` | Construction et déploiement du site |
| `data/` | Résultats téléchargés (ignoré par git) |

## Modifier le site

Pour modifier le texte, le menu ou le style, éditer les fichiers `.qmd`, `_quarto.yml` ou
`styles.css`, puis pousser sur `main`. Le site est reconstruit et déployé automatiquement en
quelques minutes (onglet *Actions* du dépôt).

Pour prévisualiser en local, [installer Quarto](https://quarto.org/docs/get-started/), récupérer
les derniers résultats (voir [Récupérer les résultats en local](#récupérer-les-résultats-en-local)),
puis :

```bash
quarto preview
```

## Mettre à jour les résultats du Linceul

### Prérequis (une fois)

- Accès aux photos : `/uds_data/glacioraide/photos_sites/Linceul`.
- Un clone de staketracker **à la version indiquée dans `config.toml`**, avec son environnement :
  ```bash
  git clone https://github.com/glacioraide/staketracker ../staketracker
  cd ../staketracker && git checkout v0.2.0 && uv sync && cd -
  ```
- [pixi](https://pixi.sh), pour lancer `gh` sans l'installer (`pixi exec gh`).
- Un jeton GitHub, dans la variable `GLACIORAIDE_GH_TOKEN` : *fine-grained token* limité au dépôt
  `glacioraide/glacioraide.github.io`, permission *Contents: read & write*.

### 1. Lancer l'analyse

Depuis la racine de ce dépôt :

```bash
../staketracker/.venv/bin/python analyses/linceul/pipeline.py \
    --staketracker ../staketracker --work ../linceul-work
```

Le pipeline, pour chaque période définie dans `config.toml` :

1. détecte la balise sur chaque photo (`detect_stakes.py` de staketracker) ;
2. filtre les mesures et les convertit en mètres (`analyze_results.py`) ;
3. télécharge la météo Open-Meteo sur la période couverte (`fetch_meteo.py`) ;
4. agrège par jour et raccorde les périodes entre elles ;
5. écrit le paquet `../linceul-work/linceul-results.tar.gz`.

La détection prend une dizaine de minutes. Pour refaire seulement les étapes suivantes (après
avoir modifié l'agrégation, par exemple), ajouter `--skip-detection`.

Le pipeline s'arrête si la version de staketracker installée n'est pas celle de `config.toml`.

Pour vérifier le résultat avant publication : extraire le paquet dans `data/linceul/` puis lancer
`quarto preview` (voir ci-dessous).

### 2. Publier

```bash
GH_TOKEN="$GLACIORAIDE_GH_TOKEN" analyses/linceul/publish_results.sh ../linceul-work
```

Le script crée une release `linceul-results-<date>` contenant le paquet. Sa création déclenche le
workflow, qui reconstruit le site avec ce nouveau paquet.

Les anciennes releases restent disponibles et constituent l'historique des analyses. On peut
supprimer celles qui ne servent plus depuis la page *Releases* du dépôt.

### Récupérer les résultats en local

```bash
mkdir -p data/linceul
pixi exec gh release download <tag> --repo glacioraide/glacioraide.github.io \
    --pattern linceul-results.tar.gz --output - | tar xz -C data/linceul
```

La liste des tags est sur la page *Releases* du dépôt, ou avec
`pixi exec gh release list --repo glacioraide/glacioraide.github.io`.

## Contenu d'un paquet de résultats

| Fichier | Contenu |
| --- | --- |
| `surface_daily.csv` | Variation journalière de la surface (cm) : mesure du jour, tendance, nombre de photos |
| `meteo_daily.csv` | Température moyenne et chute de neige journalières (Open-Meteo) |
| `balise.jpg` | Illustration de la méthode affichée sur la page |
| `metadata.json` | Date d'analyse, version et commit de staketracker, commit du pipeline, détail des périodes |
| `detection/*.csv` | Détections brutes de staketracker, une ligne par photo |
| `pipeline/config.toml`, `pipeline/pipeline.py` | Copie exacte de la configuration et du pipeline utilisés |

Tout le paquet est publié sur le site, sous `data/linceul/`. La page affiche la date d'analyse et
la version de staketracker, et sa section *Provenance* renvoie vers ces fichiers.

## Ajouter une période (caméra déplacée ou nouvelles photos)

Les paramètres de détection dépendent du cadrage de la caméra. Après chaque maintenance ou
déplacement, ajouter une période dans `analyses/linceul/config.toml` :

```toml
[[periods]]
id = "p5"
label = "Été 2026"
input_dir = "linceul_mission.../appareil1/103RECNX"   # relatif à photos_root
roi = [x, y, largeur, hauteur]                         # zone de recherche de la balise, en pixels
threshold = 140
source = "description de l'origine de ces paramètres"
```

Pour choisir `roi` et `threshold`, suivre le guide de staketracker
[Choose the ROI and threshold](https://glacioraide.github.io/staketracker/how-to/roi-threshold/) :
prendre une photo où la balise est la plus longue, encadrer la balise avec une marge de 10 à
20 pixels, et contrôler la détection sur une douzaine de photos (`--save-annotated`).

Attention : les dossiers de mission peuvent contenir des copies de photos déjà traitées
(c'est le cas de `appareil1/100RECNX` et `101RECNX` dans `linceul_mission26062026`). Vérifier les
dates avant d'ajouter un dossier.

Commiter la modification de `config.toml` **avant** de lancer le pipeline, pour que le paquet
référence un commit publié.

## Changer de version de staketracker

1. Mettre à jour le clone : `cd ../staketracker && git fetch --tags && git checkout vX.Y.Z && uv sync`.
2. Mettre à jour `staketracker_version` dans `config.toml`, commiter.
3. Relancer le pipeline **sans** `--skip-detection` : la détection doit être refaite avec la
   nouvelle version.

## Déploiement

Le workflow `.github/workflows/publish.yml` se lance à chaque push sur `main`, à chaque nouvelle
release, ou à la main (onglet *Actions* → *Quarto Publish* → *Run workflow*). Il :

1. télécharge le paquet de la release `linceul-results-*` la plus récente dans `data/linceul/` ;
2. rend le site avec Quarto ;
3. le déploie sur GitHub Pages, sous forme d'artefact (aucune branche `gh-pages`).

Réglages GitHub nécessaires :

- *Settings → Pages → Source* : **GitHub Actions**.
- *Settings → Environments → github-pages → Deployment branches and tags* : `main` et le tag
  `linceul-results-*`. Un run déclenché par une release s'exécute sur le tag de la release : sans
  cette règle, son déploiement est refusé.

## Dépannage

| Symptôme | Cause et solution |
| --- | --- |
| Workflow en échec : *« Aucune release linceul-results-\* trouvée »* | Aucun paquet publié. Lancer le pipeline puis `publish_results.sh`. |
| Workflow en échec : *« Tag … is not allowed to deploy to github-pages »* | Règle de tag manquante dans l'environnement `github-pages` (voir [Déploiement](#déploiement)). En attendant, relancer le workflow à la main sur `main`. |
| `publish_results.sh` : *HTTP 401 / 403* | Jeton absent, expiré ou sans la permission *Contents: read & write*. Vérifier `GLACIORAIDE_GH_TOKEN` (`source ~/.bashrc`). |
| `pipeline.py` : *« staketracker X installé, Y attendu »* | Le clone n'est pas à la version de `config.toml`. Voir [Changer de version de staketracker](#changer-de-version-de-staketracker). |
| La page affiche *« avec modifications locales »* dans la provenance | Le pipeline a tourné avec du code non commité. Commiter, puis relancer le pipeline et republier. |
| Page Linceul vide en local | `data/linceul/` absent. Voir [Récupérer les résultats en local](#récupérer-les-résultats-en-local). |
