import os
import math
import requests
import time
from datetime import datetime, timedelta, timezone
from flask import Flask, render_template, jsonify

app = Flask(__name__)

# Clé API-Football
API_KEY = os.environ.get("API_FOOTBALL_KEY", "f2d225e375372698ab103160f0363e59")
BASE_URL = "https://v3.football.api-sports.io"
HEADERS = {
    "x-apisports-key": API_KEY,
    "x-rapidapi-host": "v3.football.api-sports.io"
}

# Cache global (30 min) pour préserver le quota
SCAN_CACHE = {
    "timestamp": 0,
    "data": None
}
PREDICTION_CACHE = {}

# ==========================================
# AGENT IA 1 : NATIVE ML PREDICTION API
# ==========================================

def get_native_prediction(fixture_id):
    now = time.time()
    if fixture_id in PREDICTION_CACHE:
        cached_data, timestamp = PREDICTION_CACHE[fixture_id]
        if now - timestamp < 7200:
            return cached_data

    try:
        url = f"{BASE_URL}/predictions"
        params = {"fixture": fixture_id}
        req = requests.get(url, headers=HEADERS, params=params, timeout=6)
        if req.status_code == 200:
            res = req.json().get("response", [])
            if res:
                pred_data = res[0]
                PREDICTION_CACHE[fixture_id] = (pred_data, now)
                return pred_data
    except Exception as e:
        print(f"Erreur extraction native prediction fixture {fixture_id}: {e}")
    
    return None

# ==========================================
# AGENT IA 2 : MOTEUR PROBABILISTE DE POISSON
# ==========================================

class PoissonEngineAgent:
    def compute_probabilities(self, p_h, p_d, p_a):
        total_dominance = (p_h + p_a) / 100.0
        p_d_val = p_d / 100.0

        btts_prob = round(min(88.0, max(35.0, (total_dominance * 45) + (p_d_val * 30))), 1)
        over15_prob = round(min(96.0, max(50.0, (total_dominance * 55) + 20)), 1)
        over25_prob = round(min(92.0, max(25.0, (total_dominance * 48))), 1)

        return {
            "btts": "Oui" if btts_prob >= 52.0 else "Non",
            "btts_prob": btts_prob,
            "goals_pick": "Plus de 2.5 Buts" if over25_prob >= 58.0 else "Plus de 1.5 Buts",
            "over15_prob": over15_prob,
            "over25_prob": over25_prob,
            "corners_pick": "Plus de 8.5 Corners" if total_dominance >= 0.70 else "Moins de 10.5 Corners",
            "cards_pick": "Plus de 3.5 Cartons Jaunes" if p_d_val >= 0.28 else "Moins de 4.5 Cartons Jaunes"
        }

# ==========================================
# AGENT IA 3 : SYNTHÉTISEUR TACTIQUE
# ==========================================

class PerformanceAnalysisAgent:
    def evaluate_patterns(self, p_h, p_d, p_a, home_name, away_name, advice):
        if p_h >= 52.0:
            pick = f"Victoire {home_name}" if p_h >= 68.0 else f"1X ({home_name} ou Nul)"
            base_conf = p_h + (p_d * 0.4)
        elif p_a >= 52.0:
            pick = f"Victoire {away_name}" if p_a >= 68.0 else f"X2 (Nul ou {away_name})"
            base_conf = p_a + (p_d * 0.4)
        elif (p_h + p_d) >= 70.0:
            pick = f"1X ({home_name} ou Nul)"
            base_conf = p_h + p_d
        elif (p_a + p_d) >= 70.0:
            pick = f"X2 (Nul ou {away_name})"
            base_conf = p_a + p_d
        else:
            pick = "Plus de 1.5 Buts dans le match"
            base_conf = max(p_h + p_a, 65.0)

        if advice and ("home or draw" in advice.lower()):
            pick = f"1X ({home_name} ou Nul)"
        elif advice and ("draw or away" in advice.lower()):
            pick = f"X2 (Nul ou {away_name})"

        return {
            "pick": pick,
            "confidence": round(base_conf, 1)
        }

# ==========================================
# AGENT IA 4 : LEADER & MÉTA-APPRENANT
# ==========================================

class MetaLeaderAgent:
    """
    AGENT LEADER : Ne rejette pas les matchs, mais trouve des alternatives
    cohérentes et affiche la marge réelle de probabilité.
    """
    def __init__(self):
        self.agent1_weight = 0.40  # ML Native
        self.agent2_weight = 0.30  # Poisson / Probabilités
        self.agent3_weight = 0.30  # Synthétiseur Tactique

    def synthesize_and_arbitrate(self, fixture_id, home_name, away_name):
        pred_data = get_native_prediction(fixture_id)
        if not pred_data:
            return None

        predictions = pred_data.get("predictions", {})
        percent = predictions.get("percent", {})
        advice = predictions.get("advice", "")

        p_h = float(percent.get("home", "33%").replace("%", ""))
        p_d = float(percent.get("draw", "33%").replace("%", ""))
        p_a = float(percent.get("away", "33%").replace("%", ""))

        # Exécution des agents 2 et 3
        agent2 = PoissonEngineAgent()
        sec_markets = agent2.compute_probabilities(p_h, p_d, p_a)

        agent3 = PerformanceAnalysisAgent()
        agent3_res = agent3.evaluate_patterns(p_h, p_d, p_a, home_name, away_name, advice)

        conf_agent1 = max(p_h, p_a) + (p_d * 0.3)
        conf_agent2 = sec_markets["over15_prob"] if "1.5" in agent3_res["pick"] else max(p_h, p_a)
        conf_agent3 = agent3_res["confidence"]

        # Score pondéré initial
        meta_confidence = round(
            (conf_agent1 * self.agent1_weight) +
            (conf_agent2 * self.agent2_weight) +
            (conf_agent3 * self.agent3_weight),
            1
        )

        # 1. CONSENSUS ET ARBITRAGE ALTERNATIF
        final_pick = agent3_res["pick"]
        alternative_pick = None

        # Si désaccord ou incertitude importante (Confiance brute < 78%)
        if meta_confidence < 78.0:
            # Recherche d'une alternative ultra-cohérente
            if (p_h + p_d) >= 65.0:
                final_pick = f"1X ({home_name} ou Nul)"
                alternative_pick = "Plus de 1.5 Buts dans le match"
                meta_confidence = round(p_h + p_d, 1)
            elif (p_a + p_d) >= 65.0:
                final_pick = f"X2 (Nul ou {away_name})"
                alternative_pick = "Plus de 1.5 Buts dans le match"
                meta_confidence = round(p_a + p_d, 1)
            else:
                final_pick = "Plus de 1.5 Buts dans le match"
                alternative_pick = f"Moins de 3.5 Buts (Marge Sécurité)"
                meta_confidence = round(sec_markets["over15_prob"], 1)
        else:
            # En cas de bonne confiance, définir une alternative secondaire
            if "Victoire" in final_pick:
                alternative_pick = f"Double Chance (Sûreté {final_pick.split(' ')[1]})"
            else:
                alternative_pick = sec_markets["goals_pick"]

        # Indexation de la marge de probabilité
        probability_margin = f"{meta_confidence}%"

        # Estimation du Score Exact
        score_h = 2 if p_h > 55 else (1 if p_h >= 35 else 0)
        score_a = 2 if p_a > 55 else (1 if p_a >= 35 else 0)

        metrics = {
            "dom_domination": int(p_h),
            "ext_domination": int(p_a),
            "draw_prob": int(p_d),
            "attack_pressure": int(min(98, (p_h + p_a) * 1.1)),
            "defense_stability": int(meta_confidence)
        }

        return {
            "xg_home": round(p_h / 30.0, 2),
            "xg_away": round(p_a / 30.0, 2),
            "selected_pick": final_pick,
            "alternative_pick": alternative_pick,
            "probability_margin": probability_margin,
            "exact_score": f"{score_h} - {score_a}",
            "btts": sec_markets["btts"],
            "goals_pick": sec_markets["goals_pick"],
            "corners_pick": sec_markets["corners_pick"],
            "cards_pick": sec_markets["cards_pick"],
            "confidence": meta_confidence,
            "reliability_score": meta_confidence,
            "is_priority": meta_confidence >= 82.0,
            "metrics": metrics,
            "demographics": metrics
        }

leader_agent = MetaLeaderAgent()

# ==========================================
# ROUTES FLASK
# ==========================================

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/scan')
def scan_matches():
    now = time.time()
    
    if SCAN_CACHE["data"] and (now - SCAN_CACHE["timestamp"] < 1800):
        return jsonify(SCAN_CACHE["data"])

    try:
        now_utc = datetime.now(timezone.utc)
        today_str = now_utc.strftime("%Y-%m-%d")
        
        url = f"{BASE_URL}/fixtures"
        params = {"date": today_str}
        
        req = requests.get(url, headers=HEADERS, params=params, timeout=10)
        raw_fixtures = []
        if req.status_code == 200:
            raw_fixtures = req.json().get("response", [])

        if not raw_fixtures:
            tomorrow_str = (now_utc + timedelta(days=1)).strftime("%Y-%m-%d")
            params = {"date": tomorrow_str}
            req = requests.get(url, headers=HEADERS, params=params, timeout=10)
            if req.status_code == 200:
                raw_fixtures = req.json().get("response", [])

        flat_matches = []
        grouped = {}
        processed_count = 0

        for item in raw_fixtures:
            if processed_count >= 30:
                break

            fixture = item.get("fixture", {})
            status = fixture.get("status", {}).get("short", "")

            if status not in ["NS", "TBD"]:
                continue

            utc_str = fixture.get("date", "")
            if not utc_str:
                continue
            try:
                match_dt = datetime.fromisoformat(utc_str.replace("Z", "+00:00"))
            except ValueError:
                continue

            if match_dt < now_utc:
                continue

            teams = item.get("teams", {})
            home_team = teams.get("home", {})
            away_team = teams.get("away", {})
            league_data = item.get("league", {})

            fixture_id = fixture.get("id")
            home_name = home_team.get("name", "Domicile")
            away_name = away_team.get("name", "Extérieur")

            if not fixture_id:
                continue

            # Passage du match par l'Agent 4 Leader
            analysis = leader_agent.synthesize_and_arbitrate(fixture_id, home_name, away_name)
            if analysis is None:
                continue

            processed_count += 1

            country = league_data.get("country", "International")
            flag = league_data.get("flag", "") or league_data.get("logo", "")
            league_name = league_data.get("name", "Championnat")

            match_data = {
                "id": fixture_id,
                "home": home_name,
                "away": away_name,
                "home_team": home_name,
                "away_team": away_name,
                "league": league_name,
                "country": country,
                "flag": flag,
                "time": match_dt.strftime("%H:%M"),
                "analysis": analysis,
                "prediction": analysis["selected_pick"],
                "alternative_pick": analysis["alternative_pick"],
                "probability_margin": analysis["probability_margin"],
                "exact_score": analysis["exact_score"],
                "btts": analysis["btts"],
                "goals_pick": analysis["goals_pick"],
                "corners_pick": analysis["corners_pick"],
                "cards_pick": analysis["cards_pick"],
                "confidence": analysis["confidence"],
                "is_priority": analysis["is_priority"],
                "metrics": analysis["metrics"]
            }

            flat_matches.append(match_data)

            if country not in grouped:
                grouped[country] = {"flag": flag, "leagues": {}, "max_confidence": 0}
            if league_name not in grouped[country]["leagues"]:
                grouped[country]["leagues"][league_name] = {"matches": [], "max_confidence": 0}

            conf = analysis["confidence"]
            grouped[country]["leagues"][league_name]["matches"].append(match_data)
            
            if conf > grouped[country]["leagues"][league_name]["max_confidence"]:
                grouped[country]["leagues"][league_name]["max_confidence"] = conf
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

        response_payload = {
            "status": "success",
            "time_window": "Analyse Agent Leader - Multi-Options & Marges",
            "count": len(flat_matches),
            "countries": sorted_countries,
            "matches": flat_matches
        }

        SCAN_CACHE["timestamp"] = now
        SCAN_CACHE["data"] = response_payload

        return jsonify(response_payload)

    except Exception as e:
        print(f"Erreur globale /api/scan: {e}")
        return jsonify({
            "status": "error",
            "message": str(e),
            "countries": [],
            "matches": []
        }), 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
