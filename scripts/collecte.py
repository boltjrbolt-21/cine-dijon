#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Collecte les seances de cinema de l'agglomeration dijonnaise et produit data/seances.json.

Source : l'endpoint JSON interne d'AlloCine utilise par leurs pages "seances"
         https://www.allocine.fr/_/showtimes/theater-<code>/d-<AAAA-MM-JJ>/p-<page>/
         Une requete par salle et par jour ; le segment "d-" veut une date.

Usage :
    python scripts/collecte.py                 # ecrit data/seances.json
    python scripts/collecte.py --jours 10      # nombre de jours a interroger
    python scripts/collecte.py --sortie x.json # autre fichier de sortie

Aucune dependance externe : uniquement la bibliotheque standard.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

try:  # base des fuseaux presente sur les serveurs GitHub ; absente parfois sous Windows
    from zoneinfo import ZoneInfo
    PARIS = ZoneInfo("Europe/Paris")
except Exception:  # repli : decalage d'hiver, suffisant pour dater le jour courant
    PARIS = timezone(timedelta(hours=1))

RACINE = Path(__file__).resolve().parent.parent

# --- Salles suivies -------------------------------------------------------
# Les codes sont ceux d'AlloCine (visibles dans l'URL salle_gen_csalle=XXXX.html).
CINEMAS = [
    {
        "code": "P2788",
        "reservation": "https://dijon.cineville.fr/",
        # Le groupe Cineville sert son programme dans le HTML de cette page
        # (__NEXT_DATA__), avec les identifiants de reservation de chaque
        # seance : on y pioche les liens qu'AlloCine ne donne pas.
        "programme": "https://dijon.cineville.fr/programmes/dijon",
        "vad": "https://dijon.cineville.fr/vad/",
        "nom": "Cinéville Dijon",
        "alias": "ex-Olympia",
        "ville": "Dijon",
        "adresse": "16 avenue Maréchal Foch, 21000 Dijon",
        "type": "multiplexe",
    },
    {
        "code": "W2101",
        "reservation": "https://www.pathe.fr/cinemas/cinema-pathe-dijon",
        "nom": "Pathé Dijon",
        "alias": "",
        "ville": "Dijon",
        "adresse": "10 avenue Albert 1er, 21000 Dijon",
        "type": "multiplexe",
    },
    {
        "code": "P0771",
        "reservation": "https://www.pathe.fr/cinemas/cinema-cine-cap-vert",
        "nom": "Ciné Cap Vert",
        "alias": "",
        "ville": "Quetigny",
        "adresse": "ZA des Charrières, 21800 Quetigny",
        "type": "multiplexe",
    },
    {
        "code": "P0120",
        # Aucun des trois liens fournis par AlloCine ne fonctionne (2026-09-21) :
        # relay.mvtx.us dit "Sold Out", cines-dijon.com n'existe plus (NXDOMAIN)
        # et tickets.allocine.fr renvoie 404. On n'en propose aucun.
        "liens_seance": False,
        "reservation": "https://www.ticketingcine.com/cine/XPH3YLKO.html",
        # Le Darcy appartient au groupe Cineville et publie son programme sur
        # katorza.fr, avec la meme structure que Cineville Dijon.
        "programme": "https://www.katorza.fr/katorza/alaffiche/darcy",
        "vad": "https://www.katorza.fr/vad/",
        "nom": "Le Darcy",
        "alias": "",
        "ville": "Dijon",
        "adresse": "8 place Darcy, 21000 Dijon",
        "type": "art et essai",
    },
    {
        "code": "P0121",
        "reservation": "https://www.ticketingcine.com/cine/8LR6XUG6.html",
        "nom": "Eldorado",
        "alias": "",
        "ville": "Dijon",
        "adresse": "21 rue Alfred de Musset, 21000 Dijon",
        "type": "art et essai",
    },
    {
        "code": "W2100",
        "reservation": "",
        "nom": "Cinémathèque Jean Douchet",
        "alias": "Cinémathèque régionale de Bourgogne",
        "ville": "Dijon",
        "adresse": "Dijon",
        "type": "art et essai",
    },
]

GENRES_FR = {
    "ACTION": "Action",
    "ADVENTURE": "Aventure",
    "ANIMATION": "Animation",
    "BIOPIC": "Biopic",
    "BOLLYWOOD": "Bollywood",
    "CLASSIC": "Classique",
    "COMEDY": "Comédie",
    "COMEDY_DRAMA": "Comédie dramatique",
    "CONCERT": "Concert",
    "DETECTIVE": "Policier",
    "DIVERS": "Divers",
    "DOCUMENTARY": "Documentaire",
    "DRAMA": "Drame",
    "EROTIC": "Érotique",
    "EXPERIMENTAL": "Expérimental",
    "FAMILY": "Famille",
    "FANTASY": "Fantastique",
    "HISTORICAL": "Historique",
    "HORROR": "Épouvante-horreur",
    "JUDICIAL": "Judiciaire",
    "MARTIAL_ARTS": "Arts martiaux",
    "MEDICAL": "Médical",
    "MUSIC": "Musical",
    "MUSICAL": "Comédie musicale",
    "OPERA": "Opéra",
    "PERFORMANCE": "Spectacle",
    "ROMANCE": "Romance",
    "SCIENCE_FICTION": "Science-fiction",
    "SHOW": "Show",
    "SPORT_EVENT": "Sport",
    "SPY": "Espionnage",
    "THRILLER": "Thriller",
    "WARMOVIE": "Guerre",
    "WESTERN": "Western",
}

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)
# Le segment "d-" attend une DATE (d-2026-09-23), pas un numero de jour : avec un
# numero, AlloCine ignore le parametre et renvoie toujours les deux jours a venir.
BASE = "https://www.allocine.fr/_/showtimes/theater-{code}/d-{jour}/p-{page}/"
FICHE = "https://www.allocine.fr/film/fichefilm_gen_cfilm={id}.html"
PAUSE = 1.2  # secondes entre deux requetes, pour rester poli
DELAI = 20   # secondes avant d'abandonner une requete
ESSAIS = 2   # tentatives par requete ; au-dela on perd plus de temps qu'on en gagne
# Garde-fou : une collecte normale prend trois minutes. Si AlloCine ignore la
# machine qui collecte, chaque requete expire et le travail s'eternise. Passe ce
# delai on abandonne SANS rien ecrire, pour ne pas publier des donnees tronquees.
DUREE_MAX = 15 * 60


def aujourdhui_paris() -> date:
    """Le jour a Dijon, meme si la machine qui collecte est en UTC."""
    return datetime.now(PARIS).date()


def journal(*args) -> None:
    print(*args, file=sys.stderr, flush=True)


def recupere(url: str, essais: int = ESSAIS) -> dict | None:
    """GET JSON avec quelques tentatives. Renvoie None en cas d'echec definitif."""
    for tentative in range(1, essais + 1):
        try:
            requete = urllib.request.Request(
                url,
                headers={
                    "User-Agent": UA,
                    "Accept": "application/json, text/plain, */*",
                    "Accept-Language": "fr-FR,fr;q=0.9",
                    "Referer": "https://www.allocine.fr/",
                },
            )
            with urllib.request.urlopen(requete, timeout=DELAI) as reponse:
                return json.loads(reponse.read().decode("utf-8"))
        except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as err:
            journal(f"    tentative {tentative}/{essais} échouée ({err})")
            if tentative < essais:
                time.sleep(2 * tentative)
    return None


def recupere_html(url: str) -> str | None:
    """GET d'une page HTML, memes egards que pour le JSON."""
    try:
        requete = urllib.request.Request(
            url, headers={"User-Agent": UA, "Accept-Language": "fr-FR,fr;q=0.9"}
        )
        with urllib.request.urlopen(requete, timeout=DELAI) as reponse:
            return reponse.read().decode("utf-8", "replace")
    except Exception as err:
        journal(f"    programme de la salle indisponible ({err})")
        return None


def compare(titre: str) -> str:
    """Titre reduit a l'essentiel, pour rapprocher deux sources qui ne
    l'ecrivent pas pareil (accents, ponctuation, mentions ajoutees)."""
    titre = unicodedata.normalize("NFKD", titre or "").encode("ascii", "ignore").decode()
    # "Partie 2" ici, "2" la : le mot saute, le numero reste, donc deux volets
    # d'une meme saga ne peuvent pas etre confondus.
    titre = re.sub(r"\b(au cinema|le film|version longue|partie|part)\b", " ", titre.lower())
    return re.sub(r"[^a-z0-9]+", "", titre)


def programme_vad(cinema: dict) -> dict[tuple[str, str], list[tuple[str, str]]]:
    """Liens de reservation seance par seance des salles du groupe Cineville.

    Leur programme est servi directement dans le HTML de la page, dans le
    script __NEXT_DATA__, et chaque seance y porte les trois identifiants qui
    composent l'URL de reservation : /vad/<cinema>/<seance>/<bordereau>.

    Renvoie un index (date ISO, "HH:MM") -> [(titre comparable, lien), ...] ;
    plusieurs films peuvent partager un horaire, d'ou la liste.
    """
    page, base = cinema.get("programme"), cinema.get("vad")
    if not (page and base):
        return {}

    html = recupere_html(page)
    if not html:
        return {}
    trouve = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not trouve:
        journal("    programme : structure inattendue, aucun lien direct")
        return {}
    try:
        props = json.loads(trouve.group(1))["props"]["pageProps"]
    except (json.JSONDecodeError, KeyError) as err:
        journal(f"    programme illisible ({err})")
        return {}

    index: dict[tuple[str, str], list[tuple[str, str]]] = {}
    for film in props.get("prog") or []:
        donnees = film.get("movie_data") or [{}]
        titre = compare(donnees[0].get("titre") or "")
        for jour in film.get("dates") or []:
            brut = str(jour.get("date") or "")
            if len(brut) != 8:
                continue
            date = f"{brut[:4]}-{brut[4:6]}-{brut[6:]}"
            for seance in jour.get("showtimes") or []:
                heure = seance.get("heure")
                trio = (seance.get("id_cinema"), seance.get("id_seance"),
                        seance.get("id_bordereau"))
                if not heure or not all(trio):
                    continue
                index.setdefault((date, heure), []).append(
                    (titre, f"{base}{trio[0]}/{trio[1]}/{trio[2]}")
                )
    journal(f"    programme de la salle : {sum(len(v) for v in index.values())} lien(s) direct(s)")
    return index


def lien_vad(index: dict, debut: str, titre: str) -> str | None:
    """Le lien correspondant a une seance d'AlloCine, s'il est identifiable
    sans ambiguite : meme date, meme heure, et meme film."""
    candidats = index.get((debut[:10], debut[11:16])) or []
    if not candidats:
        return None
    if len(candidats) == 1:
        return candidats[0][1]

    cible = compare(titre)
    for nom, lien in candidats:
        if nom == cible:
            return lien
    for nom, lien in candidats:
        if nom and cible and (nom.startswith(cible) or cible.startswith(nom)):
            return lien
    return None  # plusieurs films a cette heure, aucun ne correspond : on s'abstient


def nettoie_texte(texte: str | None) -> str:
    if not texte:
        return ""
    texte = re.sub(r"<[^>]+>", " ", texte)
    texte = (
        texte.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&quot;", '"')
        .replace("&#039;", "'")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
    )
    return re.sub(r"\s+", " ", texte).strip()


def resume_court(synopsis: str, maxi: int = 190) -> str:
    """Premiere (ou deux premieres) phrase(s) du synopsis, coupee proprement."""
    if not synopsis:
        return ""
    phrases = re.split(r"(?<=[.!?])\s+", synopsis)
    sortie = ""
    for phrase in phrases:
        candidat = (sortie + " " + phrase).strip()
        if sortie and len(candidat) > maxi:
            break
        sortie = candidat
        if len(sortie) >= 90:
            break
    if len(sortie) > maxi:
        sortie = sortie[:maxi].rsplit(" ", 1)[0] + "…"
    return sortie


def version_lisible(cle: str, seance: dict) -> str:
    """VF / VOST / VO a partir de la cle de regroupement et des tags de la seance."""
    tags = seance.get("tags") or []
    sous_titre = "_st" in cle or any("Subtitle" in t for t in tags)
    if seance.get("diffusionVersion") == "LOCAL" or "multiple" in cle:
        return "VF"
    return "VOST" if sous_titre else "VO"


def personne(noeud: dict | None) -> str:
    if not noeud:
        return ""
    prenom = (noeud.get("firstName") or "").strip()
    nom = (noeud.get("lastName") or "").strip()
    return " ".join(p for p in (prenom, nom) if p)


def duree_minutes(runtime) -> int | None:
    """La duree arrive en secondes (7260) ou deja formatee ("1h 41min")."""
    if isinstance(runtime, (int, float)) and runtime:
        return round(runtime / 60)
    if isinstance(runtime, str):
        heures = re.search(r"(\d+)\s*h", runtime)
        minutes = re.search(r"(\d+)\s*min", runtime)
        total = int(heures.group(1)) * 60 if heures else 0
        total += int(minutes.group(1)) if minutes else 0
        return total or None
    return None


def genres_lisibles(champ) -> list[str]:
    """Les genres arrivent en codes ("THRILLER") ou en objets deja traduits."""
    sortie = []
    for genre in champ or []:
        if isinstance(genre, str):
            sortie.append(GENRES_FR.get(genre, genre.replace("_", " ").capitalize()))
        elif isinstance(genre, dict):
            # la traduction d'AlloCine arrive sans accents ("Science Fiction",
            # "Epouvante-horreur") : notre table passe d'abord.
            code = genre.get("tag") or ""
            nom = GENRES_FR.get(code) or genre.get("translate") or code.replace("_", " ").capitalize()
            if nom:
                sortie.append(nom)
    return sortie


def noeuds(champ) -> list[dict]:
    """Normalise credits/cast.

    AlloCine renvoie le meme contenu sous trois formes selon les reponses :
    une liste brute, {"nodes": [...]} ou {"edges": [{"node": ...}]}.
    """
    if isinstance(champ, list):
        source = champ
    elif isinstance(champ, dict):
        source = champ.get("nodes") or [a.get("node") for a in (champ.get("edges") or [])]
    else:
        return []
    return [n for n in source if isinstance(n, dict)]


def extrait_film(brut: dict) -> dict:
    synopsis = nettoie_texte(brut.get("synopsis") or brut.get("synopsisFull"))
    stats = brut.get("stats") or {}
    note_spectateurs = (stats.get("userRating") or {}).get("score")
    note_presse = (stats.get("pressReview") or {}).get("score")

    realisateurs = []
    for noeud in noeuds(brut.get("credits")):
        if ((noeud.get("position") or {}).get("name")) == "DIRECTOR":
            nom = personne(noeud.get("person"))
            if nom:
                realisateurs.append(nom)

    acteurs = []
    for noeud in noeuds(brut.get("cast")):
        nom = personne(noeud.get("actor") or noeud.get("voiceActor"))
        if nom:
            acteurs.append(nom)

    sortie, avertissement, classification = None, "", ""
    for parution in brut.get("releases") or []:
        date = (parution.get("releaseDate") or {}).get("date")
        if date and not sortie:
            sortie = date
        if parution.get("advice") and not avertissement:
            avertissement = nettoie_texte(parution["advice"])
        libelle = (parution.get("certificate") or {}).get("label")
        if libelle and not classification:
            classification = libelle

    duree = brut.get("runtime")
    identifiant = brut.get("internalId")

    return {
        "id": identifiant,
        "titre": nettoie_texte(brut.get("title")) or "Sans titre",
        "titre_original": nettoie_texte(brut.get("originalTitle")),
        "affiche": (brut.get("poster") or {}).get("url"),
        "duree_min": duree_minutes(duree),
        "genres": genres_lisibles(brut.get("genres")),
        "realisateurs": realisateurs[:3],
        "acteurs": acteurs[:4],
        "pays": [
            (p.get("localizedName") or p.get("name")) if isinstance(p, dict) else p
            for p in (brut.get("countries") or [])
        ][:2],
        "annee": ((brut.get("data") or {}).get("productionYear")),
        "synopsis": synopsis,
        "resume": resume_court(synopsis),
        "note_spectateurs": round(note_spectateurs, 1) if note_spectateurs else None,
        "note_presse": round(note_presse, 1) if note_presse else None,
        "sortie": sortie,
        "classification": classification,
        "avertissement": avertissement,
        "url": FICHE.format(id=identifiant) if identifiant else None,
        "seances": [],
    }


# Hotes dont les liens ne menent a rien. Un lien qui promet une reservation et
# echoue est pire que pas de lien : on les jette, et la page renvoie vers la
# billetterie de la salle ("reservation" ci-dessus).
#   relay.mvtx.us       relais d'AlloCine : aboutit toujours sur "Sold Out, or
#                       Not Available Online", verifie salle par salle et a
#                       plusieurs dates le 2026-09-21.
#   www.cines-dijon.com liens par seance du Darcy : ne fonctionnent pas, teste
#                       par Kevin le 2026-09-21 depuis son navigateur.
HOTES_ECARTES = {"relay.mvtx.us", "www.cines-dijon.com", "cines-dijon.com"}


def lien_billetterie(seance: dict) -> str | None:
    for billetterie in ((seance.get("data") or {}).get("ticketing") or []):
        for url in (billetterie.get("urls") or []):
            if not url:
                continue
            hote = urllib.parse.urlsplit(url).netloc.lower()
            if hote in HOTES_ECARTES:
                continue
            # AlloCine laisse passer des espaces et des point-virgules bruts
            # (…&code=VO; SUBTITLE) : non encodes, le lien casse la connexion.
            return urllib.parse.quote(url, safe=":/?&=#%+,@!$'()*~")
    return None


def collecte(jours: int) -> dict:
    films: dict[int, dict] = {}
    vues: set[tuple[int, str]] = set()  # (id de seance, code salle)
    etat_salles: list[dict] = []

    dates = [(aujourdhui_paris() + timedelta(days=n)).isoformat() for n in range(jours)]
    depart = time.monotonic()
    incomplet = False

    for cinema in CINEMAS:
        if incomplet:
            break
        code = cinema["code"]
        journal(f"  {cinema['nom']} ({code})")
        index_vad = programme_vad(cinema)
        total_seances = 0
        jours_avec_seances: set[str] = set()
        echecs = 0
        echec = False

        for jour in dates:
            if time.monotonic() - depart > DUREE_MAX:
                journal(f"    ABANDON : {DUREE_MAX // 60} minutes dépassées, "
                        f"la source ne répond pas normalement")
                incomplet = True
                break
            page = 1
            while True:
                donnees = recupere(BASE.format(code=code, jour=jour, page=page))
                time.sleep(PAUSE)
                if donnees is None:
                    # un jour peut échouer ponctuellement ; deux d'affilée sur la
                    # même salle, c'est qu'on est bloqué : inutile d'insister.
                    echecs += 1
                    if echecs >= 2:
                        echec = True
                    break

                resultats = donnees.get("results") or []
                for resultat in resultats:
                    brut = resultat.get("movie") or {}
                    identifiant = brut.get("internalId")
                    if not identifiant:
                        continue
                    if identifiant not in films:
                        films[identifiant] = extrait_film(brut)

                    for cle, liste in (resultat.get("showtimes") or {}).items():
                        for seance in liste or []:
                            marqueur = (seance.get("internalId"), code)
                            if marqueur in vues:
                                continue
                            vues.add(marqueur)
                            debut = seance.get("startsAt")
                            if not debut:
                                continue
                            films[identifiant]["seances"].append(
                                {
                                    "salle": code,
                                    "debut": debut,
                                    "version": version_lisible(cle, seance),
                                    "sme": cle.endswith("_sme"),
                                    "avant_premiere": bool(seance.get("isPreview")),
                                    "billetterie": (
                                        (lien_billetterie(seance)
                                         if cinema.get("liens_seance", True) else None)
                                        or lien_vad(index_vad, debut,
                                                    films[identifiant]["titre"])
                                    ),
                                }
                            )
                            total_seances += 1
                            jours_avec_seances.add(debut[:10])

                pagination = donnees.get("pagination") or {}
                if page >= (pagination.get("totalPages") or 1) or not resultats:
                    break
                page += 1

            if echec or incomplet:
                break

        journal(f"    {total_seances} séance(s) sur {len(jours_avec_seances)} jour(s)")
        etat_salles.append({
            **cinema,
            "seances_trouvees": total_seances,
            "jours_couverts": sorted(jours_avec_seances),
            "erreur": echec,
        })

    # horodatage en UTC : la page l'affiche ensuite à l'heure de Paris, ce qui
    # reste juste été comme hiver, y compris depuis un serveur GitHub.
    maintenant = datetime.now(timezone.utc)
    for film in films.values():
        film["seances"].sort(key=lambda s: s["debut"])

    jours_couverts = sorted({s["debut"][:10] for f in films.values() for s in f["seances"]})
    ordonnes = sorted(
        films.values(),
        key=lambda f: (-len(f["seances"]), -(f["note_spectateurs"] or 0), f["titre"]),
    )

    return {
        "incomplet": incomplet,
        "genere_le": maintenant.isoformat(timespec="seconds"),
        "source": "AlloCiné",
        "ville": "Dijon et agglomération",
        "jours": jours_couverts,
        "salles": etat_salles,
        "films": ordonnes,
    }


def main() -> int:
    analyseur = argparse.ArgumentParser(description="Collecte les séances de cinéma à Dijon.")
    analyseur.add_argument(
        "--jours", type=int, default=10,
        help="nombre de jours interrogés à partir d'aujourd'hui (défaut : 10)",
    )
    analyseur.add_argument(
        "--sortie", default=str(RACINE / "data" / "seances.json"), help="fichier JSON de sortie"
    )
    arguments = analyseur.parse_args()

    journal(f"Collecte des séances ({arguments.jours} jour(s) demandés)…")
    resultat = collecte(arguments.jours)

    nb_films = len(resultat["films"])
    nb_seances = sum(len(f["seances"]) for f in resultat["films"])
    salles_ok = [s for s in resultat["salles"] if not s["erreur"]]

    if resultat.pop("incomplet", False):
        journal("ÉCHEC : collecte interrompue avant la fin, le fichier n'est pas réécrit.")
        return 1
    if not salles_ok:
        journal("ÉCHEC : aucune salle n'a répondu, le fichier n'est pas réécrit.")
        return 1
    if nb_seances == 0:
        journal("ÉCHEC : aucune séance récupérée, le fichier n'est pas réécrit.")
        return 1

    destination = Path(arguments.sortie)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(resultat, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    journal(
        f"OK : {nb_films} film(s), {nb_seances} séance(s), "
        f"{len(resultat['jours'])} jour(s) — {destination}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
