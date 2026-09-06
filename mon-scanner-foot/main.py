import os
import math
import requests
import time
from datetime import datetime, timedelta, timezone
from flask import Flask, render_template, jsonify

app = Flask(__name__)

API_KEY = os.environ.get("FOOTBALL_DATA_KEY", "6a7f0cc1d0594fe48481f70b3dc9cfe7")
BASE_URL = "https://api.football-data.org/v4"
HEADERS = {"X-Auth-Token": API_KEY}

STANDINGS_CACHE = {}

# ==========================================
# FONCTIONS REQUÊTES
# ==========================================

def fetch_matches_from_api(date_from, date_to):
    params = {
        "dateFrom": date_from.strftime("%Y-%m-%d"),
        "dateTo": date_to.strftime("%Y-%m-%d")
    }
    try:
        req = requests.get(f"{BASE_URL}/matches", headers=HEADERS, params=params, timeout=10)
        if req.status_code == 200:
            return req.json().get("matches", [])
    except Exception as e:
        print(f"Erreur API /matches: {e}")
    return []

def get_league_standings(competition_id):
    now = time.time()
    if competition_id in STANDINGS_CACHE:
        cached_data, timestamp = STANDINGS_CACHE[competition_id]
        if now - timestamp < 3600:
            return cached_data

    try:
        url = f"{BASE_URL}/competitions/{competition_id}/standings"
        req = requests.get(url, headers=HEADERS, timeout=6)
        if req.status_code == 200:
            standings_data = req.json().get("standings", [])
            STANDINGS_CACHE[competition_id] = (standings_data, now)
            return standings_data
    except Exception as e:
        print(f"Erreur extraction classement (Compétition {competition_id}): {e}")
    
    return []

# ==========================================
# SYSTÈME MULTI-AGENTS IA POUR L'ANALYSE
# ==========================================

class PatternExtractionAgent:
    """AGENT IA 1 : Détection des motifs de performance et de dynamique d'équipe"""
    def extract_team_patterns(self, home_stats, away_stats):
        h_played = max(1, home_stats.get("playedGames", 1))
        a_played = max(1, away_stats.get("playedGames", 1))

        # Attaque et Défense par match
        h_attack = home_stats.get("goalsFor", 0) / h_played
        h_defense = home_stats.get("goalsAgainst", 0) / h_played
        a_attack = away_stats.get("goalsFor", 0) / a_played
        a_defense = away_stats.get("goalsAgainst", 0) / a_played

        # Calcul xG projeté
        lambda_home = max(0.4, h_attack * (a_defense / 1.1 if a_defense > 0 else 1.0))
        lambda_away = max(0.4, a_attack * (h_defense / 1.1 if h_defense > 0 else 1.0))

        pos_diff = away_stats.get("position", 10) - home_stats.get("position", 10)

        return {
            "lambda_home": lambda_home,
            "lambda_away": lambda_away,
            "pos_diff": pos_diff,
            "h_attack": h_attack,
            "a_attack": a_attack
        }

class PoissonProbabilityAgent:
    """AGENT IA 2 : Moteur probabiliste (Loi de Poisson pour Score Exact & BTTS)"""
    def compute_poisson_matrix(self, lambda_home, lambda_away):
        def poisson_pmf(k, lamb):
            return (math.pow(lamb, k) * math.exp(-lamb)) / math.factorial(k)

        matrix = {}
        max_prob = 0.0
        best_score = (1, 0)

        btts_prob = 0.0
        over15_prob = 0.0
        over25_prob = 0.0

        for h_goals in range(6):
            for a_goals in range(6):
                p_h = poisson_pmf(h_goals, lambda_home)
                p_a = poisson_pmf(a_goals, lambda_away)
                p_joint = p_h * p_a

                if p_joint > max_prob:
                    max_prob = p_joint
                    best_score = (h_goals, a_goals)

                if h_goals > 0 and a_goals > 0:
                    btts_prob += p_joint

                if (h_goals + a_goals) > 1.5:
                    over15_prob += p_joint

                if (h_goals + a_goals) > 2.5:
                    over25_prob += p_joint

        return {
            "exact_score": f"{best_score[0]} - {best_score[1]}",
            "btts_prediction": "Oui" if btts_prob >= 0.52 else "Non",
            "btts_prob": round(btts_prob * 100, 1),
            "over15_prob": round(over15_prob * 100, 1),
            "over25_prob": round(over25_prob * 100, 1)
        }

class MultiMarketDecisionAgent:
    """AGENT IA 3 : Décisionnaire principal et synthétiseur de confiance multi-marchés"""
    def evaluate(self, patterns, poisson_data):
        l_h = patterns["lambda_home"]
        l_a = patterns["lambda_away"]
        pos_diff = patterns["pos_diff"]

        # 1. Sélection du pronostic principal (Double Chance ou Over/Under)
        if pos_diff >= 3 or l_h >= l_a + 0.6:
            main_pick = "1X (Double Chance Domicile)"
            confidence = min(98.0, 81.0 + (pos_diff * 1.4) + (l_h * 3.5))
        elif pos_diff <= -3 or l_a >= l_h + 0.6:
            main_pick = "X2 (Double Chance Extérieur)"
            confidence = min(98.0, 81.0 + (abs(pos_diff) * 1.4) + (l_a * 3.5))
        elif (l_h + l_a) >= 2.3:
            main_pick = "Plus de 1.5 Buts dans le match"
            confidence = min(96.0, 78.0 + ((l_h + l_a) * 4.5))
        else:
            main_pick = "Moins de 3.5 Buts dans le match"
            confidence = 74.0

        # 2. Pronostic Buts alternatif (Over 1.5 / Over 2.5)
        if poisson_data["over25_prob"] >= 58.0:
            goals_pick = "Plus de 2.5 Buts"
        else:
            goals_pick = "Plus de 1.5 Buts"

        return {
            "main_prediction": main_pick,
            "confidence": round(confidence, 1),
            "exact_score": poisson_data["exact_score"],
            "btts": poisson_data["btts_prediction"],
            "goals_pick": goals_pick,
            "over15_prob": poisson_data["over15_prob"],
            "over25_prob": poisson_data["over25_prob"]
        }

# Initialisation des Agents IA
pattern_agent = PatternExtractionAgent()
poisson_agent = PoissonProbabilityAgent()
decision_agent = MultiMarketDecisionAgent()

def run_prediction_pipeline(home_id, away_id, competition_id):
    standings = get_league_standings(competition_id)
    
    home_stats = None
    away_stats = None

    for table_group in standings:
        table = table_group.get("table", [])
        for entry in table:
            team_id = entry.get("team", {}).get("id")
            if team_id == home_id:
                home_stats = entry
            elif team_id == away_id:
                away_stats = entry

    if not home_stats or not away_stats:
        # Repli sécurisé si l'équipe n'est pas encore enregistrée
        home_stats = {"playedGames": 10, "goalsFor": 12, "goalsAgainst": 10, "position": 8}
        away_stats = {"playedGames": 10, "goalsFor": 10, "goalsAgainst": 12, "position": 10}

    # Pipeline d'analyse séquentielle par les agents IA
    patterns = pattern_agent.extract_team_patterns(home_stats, away_stats)
    poisson_res = poisson_agent.compute_poisson_matrix(patterns["lambda_home"], patterns["lambda_away"])
    final_analysis = decision_agent.evaluate(patterns, poisson_res)

    conf = final_analysis["confidence"]
    if conf < 69.0:
        return None

    xg_h = round(patterns["lambda_home"], 2)
    xg_a = round(patterns["lambda_away"], 2)

    metrics = {
        "dom_domination": int(min(90, (xg_h / (xg_h + xg_a + 0.1)) * 100)),
        "ext_domination": int(min(90, (xg_a / (xg_h + xg_a + 0.1)) * 100)),
        "draw_prob": int(max(10, 100 - ((xg_h + xg_a) * 20))),
        "attack_pressure": int(min(98, (xg_h + xg_a) * 26)),
        "defense_stability": int(min(98, conf))
    }

    return {
        "xg_home": xg_h,
        "xg_away": xg_a,
        "selected_pick": final_analysis["main_prediction"],
        "exact_score": final_analysis["exact_score"],
        "btts": final_analysis["btts"],
        "goals_pick": final_analysis["goals_pick"],
        "confidence": conf,
        "reliability_score": conf,
        "is_priority": conf >= 80.0,
        "metrics": metrics,
        "demographics": metrics
    }

# ==========================================
# ROUTES FLASK
# ==========================================

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/scan')
def scan_matches():
    try:
        now_utc = datetime.now(timezone.utc)
        
        target_date = now_utc + timedelta(hours=12)
        raw_matches = fetch_matches_from_api(now_utc, target_date)
        time_window_label = "Prochaines 12h"

        if not raw_matches:
            target_date = now_utc + timedelta(hours=48)
            raw_matches = fetch_matches_from_api(now_utc, target_date)
            time_window_label = "Prochaines 48h (Analyse IA Étendue)"

        flat_matches = []
        grouped = {}

        for m in raw_matches:
            status = m.get("status", "")
            if status in ["FINISHED", "IN_PLAY", "PAUSED", "CANCELLED", "POSTPONED"]:
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
            comp_id = m.get("competition", {}).get("id")

            if not home_id or not away_id or not comp_id:
                continue

            analysis = run_prediction_pipeline(home_id, away_id, comp_id)
            if analysis is None:
                continue

            home_name = home_team.get("name", "Domicile")
            away_name = away_team.get("name", "Extérieur")
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
                "time": match_dt.strftime("%H:%M"),
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

        return jsonify({
            "status": "success",
            "time_window": time_window_label,
            "count": len(flat_matches),
            "countries": sorted_countries,
            "matches": flat_matches
        })

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
