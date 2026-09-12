import os
import math
import requests
import time
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import Flask, render_template, jsonify

app = Flask(__name__)

API_KEY = os.environ.get("FOOTBALL_DATA_KEY", "6a7f0cc1d0594fe48481f70b3dc9cfe7")
BASE_URL = "https://api.football-data.org/v4"
HEADERS = {"X-Auth-Token": API_KEY}

# Ligues majeures prises en charge
MAJOR_LEAGUES = "PL,PD,SA,BL1,FL1,DED,PPL,CL"

# Caches en mémoire pour respecter les quotas d'API
STANDINGS_CACHE = {}
MATCHES_CACHE = {"timestamp": 0, "data": None}

# ==========================================
# FONCTIONS D'ACCÈS AUX DONNÉES (API + CACHE)
# ==========================================

def get_league_standings(competition_id):
    """Récupère et met en cache les classements pour éviter le Rate Limit (429)"""
    now = time.time()
    if competition_id in STANDINGS_CACHE:
        cached_data, timestamp = STANDINGS_CACHE[competition_id]
        if now - timestamp < 7200:  # Cache de 2 heures
            return cached_data

    try:
        url = f"{BASE_URL}/competitions/{competition_id}/standings"
        req = requests.get(url, headers=HEADERS, timeout=5)
        if req.status_code == 200:
            standings_data = req.json().get("standings", [])
            STANDINGS_CACHE[competition_id] = (standings_data, now)
            return standings_data
        elif req.status_code == 429:
            time.sleep(1)
    except Exception as e:
        print(f"Erreur extraction classement (Compétition {competition_id}): {e}")

    return []

def preload_all_standings(competitions_str):
    """Pré-charge les classements des ligues en parallèle pour éliminer le goulot d'étranglement"""
    comp_ids = [c.strip() for c in competitions_str.split(",") if c.strip()]
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(get_league_standings, comp_id): comp_id for comp_id in comp_ids}
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                print(f"Erreur lors du pré-chargement pour la compétition {futures[future]}: {e}")

# ==========================================
# SYSTÈME MULTI-AGENTS IA STRICT
# ==========================================

class PatternExtractionAgent:
    """
    AGENT IA 1 : Extraction des métriques réelles de performance
    Analyse l'efficacité offensive/défensive et la position au classement.
    """
    def extract_team_patterns(self, home_stats, away_stats):
        h_played = max(1, home_stats.get("playedGames", 1))
        a_played = max(1, away_stats.get("playedGames", 1))

        # Attaque et Défense réelles par match (Moyenne de la ligue estimée à 1.35)
        h_attack = home_stats.get("goalsFor", 0) / h_played
        h_defense = home_stats.get("goalsAgainst", 0) / h_played
        a_attack = away_stats.get("goalsFor", 0) / a_played
        a_defense = away_stats.get("goalsAgainst", 0) / a_played

        # Calcul xG (Expected Goals) pondéré selon la force de l'adversaire
        league_avg_goals = 1.35
        lambda_home = max(0.2, (h_attack * a_defense) / league_avg_goals)
        lambda_away = max(0.2, (a_attack * h_defense) / league_avg_goals)

        # Différence de classement au championnat
        pos_home = home_stats.get("position", 10)
        pos_away = away_stats.get("position", 10)
        pos_diff = pos_away - pos_home  # Positif = Domicile mieux classé

        # Forme récente (Points par match sur les derniers matchs)
        h_points = (home_stats.get("won", 0) * 3 + home_stats.get("draw", 0)) / h_played
        a_points = (away_stats.get("won", 0) * 3 + away_stats.get("draw", 0)) / a_played

        return {
            "lambda_home": lambda_home,
            "lambda_away": lambda_away,
            "pos_diff": pos_diff,
            "pos_home": pos_home,
            "pos_away": pos_away,
            "h_points": h_points,
            "a_points": a_points
        }


class PoissonProbabilityAgent:
    """
    AGENT IA 2 : Distribution probabiliste exacte (Loi de Poisson)
    Génère la matrice des scores probables, probabilités 1N2, Over/Under et BTTS.
    """
    def compute_probabilities(self, lambda_home, lambda_away):
        def poisson_pmf(k, lamb):
            return (math.pow(lamb, k) * math.exp(-lamb)) / math.factorial(k)

        prob_home = 0.0
        prob_draw = 0.0
        prob_away = 0.0
        btts_prob = 0.0
        over15_prob = 0.0
        over25_prob = 0.0

        max_p = 0.0
        best_score = (1, 0)

        # Matrice de score de 0x0 à 5x5
        for h in range(6):
            for a in range(6):
                p_h = poisson_pmf(h, lambda_home)
                p_a = poisson_pmf(a, lambda_away)
                p_joint = p_h * p_a

                if p_joint > max_p:
                    max_p = p_joint
                    best_score = (h, a)

                if h > a:
                    prob_home += p_joint
                elif h == a:
                    prob_draw += p_joint
                else:
                    prob_away += p_joint

                if h > 0 and a > 0:
                    btts_prob += p_joint

                if (h + a) > 1.5:
                    over15_prob += p_joint

                if (h + a) > 2.5:
                    over25_prob += p_joint

        total = prob_home + prob_draw + prob_away
        if total > 0:
            prob_home /= total
            prob_draw /= total
            prob_away /= total

        return {
            "p_home": prob_home * 100,
            "p_draw": prob_draw * 100,
            "p_away": prob_away * 100,
            "exact_score": f"{best_score[0]} - {best_score[1]}",
            "btts_prob": btts_prob * 100,
            "over15_prob": over15_prob * 100,
            "over25_prob": over25_prob * 100
        }


class MultiMarketDecisionAgent:
    """
    AGENT IA 3 : Décisionnaire et filtre de cohérence
    Synthétise la décision finale en vérifiant la cohérence entre favori, xG et classement.
    """
    def evaluate(self, patterns, poisson, home_name, away_name):
        p_h = poisson["p_home"]
        p_d = poisson["p_draw"]
        p_a = poisson["p_away"]
        pos_diff = patterns["pos_diff"]

        # Validation de la cohérence : Le favori désigné doit correspondre aux statistiques
        if p_h >= 52.0 and pos_diff >= -2:
            main_pick = f"Victoire {home_name}" if p_h >= 65.0 else f"1X ({home_name} ou Nul)"
            confidence = min(96.0, p_h + (p_d * 0.4))
        elif p_a >= 52.0 and pos_diff <= 2:
            main_pick = f"Victoire {away_name}" if p_a >= 65.0 else f"X2 (Nul ou {away_name})"
            confidence = min(96.0, p_a + (p_d * 0.4))
        elif (p_h + p_d) >= 72.0:
            main_pick = f"1X ({home_name} ou Nul)"
            confidence = round(p_h + p_d, 1)
        elif (p_a + p_d) >= 72.0:
            main_pick = f"X2 (Nul ou {away_name})"
            confidence = round(p_a + p_d, 1)
        elif poisson["over15_prob"] >= 75.0:
            main_pick = "Plus de 1.5 Buts dans le match"
            confidence = round(poisson["over15_prob"], 1)
        else:
            main_pick = "Moins de 3.5 Buts dans le match"
            confidence = 70.0

        goals_pick = "Plus de 2.5 Buts" if poisson["over25_prob"] >= 58.0 else "Plus de 1.5 Buts"
        btts_pick = "Oui" if poisson["btts_prob"] >= 52.0 else "Non"

        return {
            "main_prediction": main_pick,
            "confidence": round(confidence, 1),
            "exact_score": poisson["exact_score"],
            "btts": btts_pick,
            "goals_pick": goals_pick,
            "p_home": round(p_h, 1),
            "p_draw": round(p_d, 1),
            "p_away": round(p_a, 1)
        }


# Initialisation
pattern_agent = PatternExtractionAgent()
poisson_agent = PoissonProbabilityAgent()
decision_agent = MultiMarketDecisionAgent()


def run_prediction_pipeline(home_id, away_id, competition_id, home_name, away_name):
    standings = get_league_standings(competition_id)

    home_stats = None
    away_stats = None

    # Recherche des données exactes de chaque équipe dans le classement
    for table_group in standings:
        table = table_group.get("table", [])
        for entry in table:
            t_id = entry.get("team", {}).get("id")
            if t_id == home_id:
                home_stats = entry
            elif t_id == away_id:
                away_stats = entry

    # Si les statistiques de classement manquent, ne pas inventer
    if not home_stats or not away_stats:
        return None

    # Pipeline de traitement séquentiel
    patterns = pattern_agent.extract_team_patterns(home_stats, away_stats)
    poisson_res = poisson_agent.compute_probabilities(patterns["lambda_home"], patterns["lambda_away"])
    final_analysis = decision_agent.evaluate(patterns, poisson_res, home_name, away_name)

    # Filtre de rigueur : Exclusion des matchs à faible indice de confiance (< 70%)
    if final_analysis["confidence"] < 70.0:
        return None

    metrics = {
        "dom_domination": int(final_analysis["p_home"]),
        "ext_domination": int(final_analysis["p_away"]),
        "draw_prob": int(final_analysis["p_draw"]),
        "attack_pressure": int(min(98, (patterns["lambda_home"] + patterns["lambda_away"]) * 28)),
        "defense_stability": int(final_analysis["confidence"])
    }

    return {
        "xg_home": round(patterns["lambda_home"], 2),
        "xg_away": round(patterns["lambda_away"], 2),
        "selected_pick": final_analysis["main_prediction"],
        "exact_score": final_analysis["exact_score"],
        "btts": final_analysis["btts"],
        "goals_pick": final_analysis["goals_pick"],
        "confidence": final_analysis["confidence"],
        "reliability_score": final_analysis["confidence"],
        "is_priority": final_analysis["confidence"] >= 80.0,
        "metrics": metrics
    }

# ==========================================
# ROUTES FLASK
# ==========================================

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/scan')
def scan_matches():
    now_ts = time.time()

    # Utilisation du cache global (15 min) pour éviter les blocages API
    if MATCHES_CACHE["data"] and (now_ts - MATCHES_CACHE["timestamp"] < 900):
        return jsonify(MATCHES_CACHE["data"])

    try:
        # Pré-chargement des classements pour éviter les ralentissements pendant le scan
        preload_all_standings(MAJOR_LEAGUES)

        now_utc = datetime.now(timezone.utc)
        date_from = now_utc.strftime("%Y-%m-%d")
        date_to = (now_utc + timedelta(days=3)).strftime("%Y-%m-%d")

        url = f"{BASE_URL}/matches"
        params = {
            "competitions": MAJOR_LEAGUES,
            "dateFrom": date_from,
            "dateTo": date_to
        }

        req = requests.get(url, headers=HEADERS, params=params, timeout=10)
        if req.status_code != 200:
            return jsonify({
                "status": "error",
                "message": f"Erreur API ({req.status_code})",
                "countries": [],
                "matches": []
            }), 200

        raw_matches = req.json().get("matches", [])
        flat_matches = []
        grouped = {}

        for m in raw_matches:
            status = m.get("status", "")
            if status not in ["SCHEDULED", "TIMED"]:
                continue

            utc_str = m.get("utcDate", "")
            if not utc_str:
                continue

            try:
                match_dt = datetime.fromisoformat(utc_str.replace("Z", "+00:00"))
            except ValueError:
                continue

            home_team = m.get("homeTeam", {})
            away_team = m.get("awayTeam", {})
            home_id = home_team.get("id")
            away_id = away_team.get("id")

            # Récupération sécurisée du comp_id au niveau global ou dans la clé match
            comp_id = m.get("competition", {}).get("id") or m.get("competition", {}).get("code")

            if not home_id or not away_id or not comp_id:
                continue

            home_name = home_team.get("name", "Domicile")
            away_name = away_team.get("name", "Extérieur")

            analysis = run_prediction_pipeline(home_id, away_id, comp_id, home_name, away_name)
            if analysis is None:
                continue

            country = m.get("area", {}).get("name", "International")
            flag = m.get("area", {}).get("flag", "")
            league = m.get("competition", {}).get("name", "Championnat")

            match_data = {
                "id": m.get("id"),
                "home": home_name,
                "away": away_name,
                "home_team": home_name,
                "away_team": away_name,
                "league": league,
                "country": country,
                "flag": flag,
                "time": match_dt.strftime("%d/%m %H:%M"),
                "analysis": analysis,
                "prediction": analysis["selected_pick"],
                "exact_score": analysis["exact_score"],
                "btts": analysis["btts"],
                "goals_pick": analysis["goals_pick"],
                "confidence": analysis["confidence"],
                "is_priority": analysis["is_priority"],
                "metrics": analysis["metrics"]
            }

            flat_matches.append(match_data)

            if country not in grouped:
                grouped[country] = {"flag": flag, "leagues": {}, "max_confidence": 0}
            if league not in grouped[country]["leagues"]:
                grouped[country]["leagues"][league] = {"matches": [], "max_confidence": 0}

            conf = analysis["confidence"]
            grouped[country]["leagues"][league]["matches"].append(match_data)

            if conf > grouped[country]["leagues"][league]["max_confidence"]:
                grouped[country]["leagues"][league]["max_confidence"] = conf
            if conf > grouped[country]["max_confidence"]:
                grouped[country]["max_confidence"] = conf

        flat_matches.sort(key=lambda x: x["confidence"], reverse=True)

        sorted_countries = []
        for c_name, c_data in sorted(grouped.items(), key=lambda item: item[1]["max_confidence"], reverse=True):
            sorted_leagues = []
            for l_name, l_data in sorted(c_data["leagues"].items(), key=lambda item: item[1]["max_confidence"], reverse=True):
                l_data["matches"].sort(key=lambda x: x["confidence"], reverse=True)
                sorted_leagues.append({
                    "league_name": l_name,
                    "max_confidence": l_data["max_confidence"],
                    "matches": l_data["matches"]
                })

            sorted_countries.append({
                "country_name": c_name,
                "flag": c_data["flag"],
                "max_confidence": c_data["max_confidence"],
                "leagues": sorted_leagues
            })

        response = {
            "status": "success",
            "time_window": "Scan 72h (Analyse Réelle des Performances)",
            "count": len(flat_matches),
            "countries": sorted_countries,
            "matches": flat_matches
        }

        MATCHES_CACHE["timestamp"] = now_ts
        MATCHES_CACHE["data"] = response

        return jsonify(response)

    except Exception as e:
        print(f"Erreur globale dans /api/scan: {e}")
        return jsonify({
            "status": "error",
            "message": str(e),
            "countries": [],
            "matches": []
        }), 200


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
