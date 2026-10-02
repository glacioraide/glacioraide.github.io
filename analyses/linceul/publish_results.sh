#!/usr/bin/env bash
# Publie un paquet de résultats produit par pipeline.py en tant que GitHub Release.
# La publication déclenche le workflow qui reconstruit et déploie le site.
#
# Usage : ./publish_results.sh <work_dir>
# Prérequis :
#   - pixi (https://pixi.sh) : gh est exécuté via `pixi exec gh`, sans installation ;
#   - un jeton GitHub dans GH_TOKEN (recommandé : fine-grained token limité à ce dépôt,
#     permission Contents: read & write), ou une session `pixi exec gh auth login`.
set -euo pipefail

GH=(pixi exec gh)

WORK=$(realpath "$1")
REPO=glacioraide/glacioraide.github.io
ARCHIVE="$WORK/linceul-results.tar.gz"
META="$WORK/bundle/metadata.json"

read -r ANALYSIS_DATE ST_VERSION < <(python3 -c "
import json; m = json.load(open('$META'))
print(m['analysis_date'], m['staketracker']['version'])")

# Tag lisible et unique : linceul-results-2026-10-02T1930
TAG="linceul-results-$(date -d "$ANALYSIS_DATE" +%Y-%m-%dT%H%M)"

"${GH[@]}" release create "$TAG" "$ARCHIVE" --repo "$REPO" \
    --title "Résultats Linceul du $(date -d "$ANALYSIS_DATE" +%d/%m/%Y)" \
    --notes "Analyse du $ANALYSIS_DATE avec staketracker $ST_VERSION. Contenu : données journalières, métadonnées, détections brutes, config et pipeline utilisés." \
    --latest=false

echo "Publié : https://github.com/$REPO/releases/tag/$TAG"
