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
# FONCTION DE REQUÊTE SÉCURISÉE VERS L'API
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

# ==========================================
# AGENT IA 1 : EXTRACTION DU CLASSEMENT OFFICIEL
# ==========================================

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
# AGENT IA 2 : ANALYSTE DE PERFORMANCE
# ==========================================

class IntelligenceScanAgent:
    def evaluate_match_from_standings(self, home_id, away_id, standings):
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

        if home_stats and away_stats:
            h_played = max(1, home_stats.get("playedGames", 1))
            a_played = max(1, away_stats.get("playedGames", 1))

            h_gf_avg = home_stats.get("goalsFor", 0) / h_played
            h_ga_avg = home_stats.get("goalsAgainst", 0) / h_played
            a_gf_avg = away_stats.get("goalsFor", 0) / a_played
            a_ga_avg = away_stats.get("goalsAgainst", 0) / a_played

            projected_h_xg = round(h_gf_avg * (a_ga_avg / 1.1 if a_ga_avg > 0 else 1.0), 2)
            projected_a_xg = round(a_gf_avg * (h_ga_avg / 1.1 if h_ga_avg > 0 else 1.0), 2)

            h_pos = home_stats.get("position", 10)
            a_pos = away_stats.get("position", 10)
            pos_diff = a_pos - h_pos

            confidence = 72.0
            pick = "Plus de 1.5 Buts dans le match"

            if pos_diff >= 4 or projected_h_xg >= projected_a_xg + 0.6:
                pick = "1X (Double Chance Domicile)"
                confidence = min(98.0, 80.0 + (pos_diff * 1.5) + (projected_h_xg * 3))
            elif pos_diff <= -4 or projected_a_xg >= projected_h_xg + 0.6:
                pick = "X2 (Double Chance Extérieur)"
                confidence = min(98.0, 80.0 + (abs(pos_diff) * 1.5) + (projected_a_xg * 3))
            elif (projected_h_xg + projected_a_xg) >= 2.2:
                pick = "Plus de 1.5 Buts dans le match"
                confidence = min(96.0, 78.0 + ((projected_h_xg + projected_a_xg) * 4))

            return {
                "selected_pick": pick,
                "confidence": round(confidence, 1),
                "xg_home": max(0.5, projected_h_xg),
                "xg_away": max(0.5, projected_a_xg)
            }

        return {
            "selected_pick": "Plus de 1.5 Buts dans le match",
            "confidence": 71.0,
            "xg_home": 1.3,
            "xg_away": 1.0
        }

ia_agent = IntelligenceScanAgent()

def run_prediction_pipeline(home_id, away_id, competition_id):
    standings = get_league_standings(competition_id)
    analysis = ia_agent.evaluate_match_from_standings(home_id, away_id, standings)

    conf = analysis["confidence"]

    if conf < 69.0:
        return None

    xg_h = analysis["xg_home"]
    xg_a = analysis["xg_away"]

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
        "selected_pick": analysis["selected_pick"],
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
        
        # 1. Fenêtre initiale de 12h
        target_date = now_utc + timedelta(hours=12)
        raw_matches = fetch_matches_from_api(now_utc, target_date)
        time_window_label = "Prochaines 12h"

        # 2. Extension automatique si aucun match n'est disponible
        if not raw_matches:
            target_date = now_utc + timedelta(hours=48)
            raw_matches = fetch_matches_from_api(now_utc, target_date)
            time_window_label = "Prochaines 48h (Garantie de résultats)"

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
        # En cas d'exception non gérée, renvoyer une structure valide pour éviter la pop-up JS
        return jsonify({
            "status": "error",
            "message": str(e),
            "countries": [],
            "matches": []
        }), 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
