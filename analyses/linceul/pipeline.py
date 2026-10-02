"""Pipeline d'analyse du site Linceul : photos -> paquet de résultats publié sur le site.

Usage (avec l'environnement Python de staketracker) :

    python pipeline.py --staketracker /chemin/staketracker --work /chemin/travail

Étapes :
1. détection de la balise sur chaque période (scripts/detect_stakes.py de staketracker) ;
2. filtrage et conversion en mètres (scripts/analyze_results.py) ;
3. météo Open-Meteo sur la période couverte (scripts/fetch_meteo.py) ;
4. agrégation journalière et raccord des périodes pour la page web ;
5. écriture du paquet <work>/bundle et de l'archive <work>/linceul-results.tar.gz :
   données web, métadonnées, résultats de détection, et copie de cette config et de ce pipeline.

Variation de la surface : quand la surface monte (neige), la partie visible de la balise
raccourcit ; quand elle baisse (fonte, vent), elle s'allonge.
  variation_surface = -(hauteur_visible - hauteur_visible_de_référence)
Chaque période (réglage caméra différent) est raccordée à la précédente en supposant que
la surface n'a pas changé entre le dernier jour mesuré de l'une et le premier de la suivante.
"""

import argparse
import json
import shutil
import subprocess
import sys
import tarfile
import tomllib
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent


def run(cmd: list, cwd: Path) -> None:
    print("$", " ".join(str(c) for c in cmd), flush=True)
    subprocess.run([str(c) for c in cmd], cwd=cwd, check=True)


def git_info(path: Path) -> dict:
    def git(*args):
        res = subprocess.run(["git", "-C", str(path), *args], capture_output=True, text=True)
        return res.stdout.strip() if res.returncode == 0 else None

    return {
        "commit": git("rev-parse", "HEAD"),
        "tag": git("describe", "--tags", "--exact-match"),
        "dirty": bool(git("status", "--porcelain", "--untracked-files=no")),
    }


def daily_surface(cfg: dict, work: Path) -> pd.DataFrame:
    daily_all, offset_cm = [], 0.0
    for period in cfg["periods"]:
        df = pd.read_csv(
            work / f"{period['id']}_analysis" / "results_with_snow_level.csv", comment="#", parse_dates=["creation_date"]
        )
        df["day"] = df["creation_date"].dt.floor("D")
        daily = df.groupby("day").agg(
            hauteur_m=("balise_height_m_moving_average", "median"),
            n_photos=("balise_height_m", "size"),
        )
        daily = daily[daily["n_photos"] >= cfg["web"]["min_photos_per_day"]].copy()
        surface_cm = -(daily["hauteur_m"] - daily["hauteur_m"].iloc[0]) * 100 + offset_cm
        daily["surface_cm"] = surface_cm
        daily["lisse_cm"] = surface_cm.rolling(f"{cfg['web']['smooth_days']}D", center=True, min_periods=1).median()
        daily["periode"] = period["label"]
        offset_cm = daily["surface_cm"].iloc[-1]
        daily_all.append(daily)
    surface = pd.concat(daily_all).reset_index().rename(columns={"day": "date"})
    surface["date"] = surface["date"].dt.strftime("%Y-%m-%d")
    return surface[["date", "periode", "surface_cm", "lisse_cm", "n_photos"]].round(1)


def illustration(cfg: dict, out: Path) -> None:
    """Deux vues de la balise, avec un repère orange à côté de la partie visible détectée."""
    from staketracker.detection import detect_stakes, stakes_vertical_size

    ill = cfg["illustration"]
    period = next(p for p in cfg["periods"] if p["id"] == ill["period"])
    params = {"wx": 0.9, "threshold": period["threshold"], "ksize": 1, "clahe_clip": 1.0, "clahe_tile": 2}
    x0, y0, x1, y1 = ill["crop"]
    scale, colour = 3, (0, 140, 255)
    tiles = []
    for name in ill["images"]:
        path = str(Path(cfg["photos_root"]) / period["input_dir"] / name)
        detected = detect_stakes(path, tuple(period["roi"]), params)
        size = stakes_vertical_size(detected)
        crop = cv2.resize(cv2.imread(path)[y0:y1, x0:x1], None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        bx = (max(px for px, _ in detected) - x0 + 8) * scale
        top, bottom = (size["y_min"] - y0) * scale, (size["y_max"] - y0) * scale
        cv2.line(crop, (bx, top), (bx, bottom), colour, 3)
        for y in (top, bottom):
            cv2.line(crop, (bx - 8, y), (bx + 8, y), colour, 3)
        tiles.append(crop)
    gap = np.full((tiles[0].shape[0], 12, 3), 255, np.uint8)
    cv2.imwrite(str(out), np.hstack([tiles[0], gap, tiles[1]]), [cv2.IMWRITE_JPEG_QUALITY, 85])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--staketracker", required=True, type=Path, help="Clone de staketracker (scripts/)")
    parser.add_argument("--work", required=True, type=Path, help="Dossier de travail")
    parser.add_argument("--config", type=Path, default=HERE / "config.toml")
    parser.add_argument("--skip-detection", action="store_true", help="Réutiliser les détections déjà présentes")
    args = parser.parse_args()

    import staketracker

    cfg = tomllib.loads(args.config.read_text())
    if staketracker.__version__ != cfg["staketracker_version"]:
        sys.exit(f"staketracker {staketracker.__version__} installé, {cfg['staketracker_version']} attendu")

    started = datetime.now().astimezone()
    work, st_dir = args.work.resolve(), args.staketracker.resolve()
    work.mkdir(parents=True, exist_ok=True)
    py = sys.executable

    # 1-2. Détection et analyse par période.
    for p in cfg["periods"]:
        det_dir = work / p["id"]
        if not (args.skip_detection and (det_dir / "detection_results.csv").exists()):
            run([py, "scripts/detect_stakes.py", "--input-dir", Path(cfg["photos_root"]) / p["input_dir"],
                 "--roi", *p["roi"], "--threshold", p["threshold"], "--output", det_dir, "--overwrite"], st_dir)
        run([py, "scripts/analyze_results.py", "--input", det_dir / "detection_results.csv",
             "--output", work / f"{p['id']}_analysis", "--px-per-metre", cfg["px_per_metre"], "--no-plots",
             "--overwrite"], st_dir)

    # 3. Météo sur la période couverte par les photos.
    detections = {
        p["id"]: pd.read_csv(work / p["id"] / "detection_results.csv", comment="#", parse_dates=["creation_date"])
        for p in cfg["periods"]
    }
    all_dates = pd.concat(d["creation_date"] for d in detections.values()).dropna()
    start, end = all_dates.min().strftime("%Y-%m-%d"), all_dates.max().strftime("%Y-%m-%d")
    run([py, "scripts/fetch_meteo.py", "--lat", cfg["meteo"]["latitude"], "--lon", cfg["meteo"]["longitude"],
         "--start", start, "--end", end, "--output", work / "weather.csv"], st_dir)

    # 4-5. Paquet de résultats.
    bundle = work / "bundle"
    shutil.rmtree(bundle, ignore_errors=True)
    for sub in ("detection", "pipeline"):
        (bundle / sub).mkdir(parents=True)

    surface = daily_surface(cfg, work)
    surface.to_csv(bundle / "surface_daily.csv", index=False)
    meteo = pd.read_csv(work / "weather.csv", parse_dates=["date"])
    meteo["date"] = meteo["date"].dt.strftime("%Y-%m-%d")
    meteo = meteo.rename(columns={"temperature_2m_mean": "temperature_c", "snowfall_sum": "neige_cm"})
    meteo[["date", "temperature_c", "neige_cm"]].round(1).to_csv(bundle / "meteo_daily.csv", index=False)
    illustration(cfg, bundle / "balise.jpg")

    for p in cfg["periods"]:
        shutil.copy(work / p["id"] / "detection_results.csv", bundle / "detection" / f"{p['id']}_detection_results.csv")
    shutil.copy(args.config, bundle / "pipeline" / "config.toml")
    shutil.copy(Path(__file__).resolve(), bundle / "pipeline" / "pipeline.py")

    periods_meta = []
    for p in cfg["periods"]:
        det, days = detections[p["id"]], surface[surface["periode"] == p["label"]]
        periods_meta.append({
            **{k: p[k] for k in ("id", "label", "input_dir", "roi", "threshold", "source")},
            "photos": int(len(det)),
            "first_photo": det["creation_date"].min().isoformat(),
            "last_photo": det["creation_date"].max().isoformat(),
            "valid_days": int(len(days)),
        })
    metadata = {
        "site": cfg["site"],
        "analysis_date": started.isoformat(timespec="seconds"),
        "staketracker": {"version": staketracker.__version__, **git_info(st_dir)},
        "pipeline": git_info(HERE),
        "px_per_metre": cfg["px_per_metre"],
        "meteo": {**cfg["meteo"], "source": "Open-Meteo", "start": start, "end": end},
        "web": cfg["web"],
        "periods": periods_meta,
    }
    (bundle / "metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n")

    archive = work / f"{cfg['site']}-results.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(bundle, arcname=".")
    print(f"\n{len(surface)} jours de mesure, du {surface['date'].iloc[0]} au {surface['date'].iloc[-1]}")
    print(f"Paquet : {archive}")


if __name__ == "__main__":
    main()
