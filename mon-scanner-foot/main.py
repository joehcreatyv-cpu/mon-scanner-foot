import os
import math
import requests
from datetime import datetime, timedelta, timezone
from flask import Flask, render_template, jsonify

app = Flask(__name__)

API_KEY = os.environ.get("FOOTBALL_DATA_KEY", "6a7f0cc1d0594fe48481f70b3dc9cfe7")
BASE_URL = "https://api.football-data.org/v4"

# ==========================================
# SOUS-AGENT IA : DÉTECTEUR DE PATTERNS
# ==========================================

class PatternExtractionAgent:
    def __init__(self, min_sample_size=3):
        self.min_sample_size = min_sample_size

    def extract_team_signature(self, match_history, is_home=True):
        if len(match_history) < self.min_sample_size:
            return None

        xg_for = []
        xg_against = []
        conversion_rates = []
        resilience_scores = []

        for m in match_history:
            gf = m['goals_for']
            ga = m['goals_against']
            xg_f = m['xg_for']
            xg_a = m['xg_against']

            xg_for.append(xg_f)
            xg_against.append(xg_a)

            conv = (gf / xg_f) if xg_f > 0 else 1.0
            conversion_rates.append(conv)

            res = (1.0 / (ga + 1.0)) * (xg_a + 0.5)
            resilience_scores.append(res)

        mean_xg_f = sum(xg_for) / len(xg_for)
        mean_xg_a = sum(xg_against) / len(xg_against)

        variance_f = sum((x - mean_xg_f) ** 2 for x in xg_for) / len(xg_for)
        variance_a = sum((x - mean_xg_a) ** 2 for x in xg_against) / len(xg_against)
        std_xg_f = math.sqrt(variance_f)
        std_xg_a = math.sqrt(variance_a)

        stability_score = 1.0 / (1.0 + std_xg_f + std_xg_a)

        mean_conv = sum(conversion_rates) / len(conversion_rates)
        mean_res = sum(resilience_scores) / len(resilience_scores)

        return {
            "expected_xg_f": round(float(mean_xg_f), 2),
            "expected_xg_a": round(float(mean_xg_a), 2),
            "conversion_factor": round(float(mean_conv), 2),
            "resilience_factor": round(float(mean_res), 2),
            "stability_index": round(float(stability_score), 3)
        }

    def evaluate_match_pattern(self, home_history, away_history):
        sig_home = self.extract_team_signature(home_history, is_home=True)
        sig_away = self.extract_team_signature(away_history, is_home=False)

        if not sig_home or not sig_away:
            return {"pattern_found": False, "confidence": 0.0, "reason": "Historique insuffisant"}

        combined_stability = (sig_home["stability_index"] + sig_away["stability_index"]) / 2.0

        projected_home_xg = sig_home["expected_xg_f"] * (sig_away["expected_xg_a"] / 1.2)
        projected_away_xg = sig_away["expected_xg_f"] * (sig_home["expected_xg_a"] / 1.2)

        pattern_match = False
        selected_pick = None
        pattern_confidence = 0.0

        # Application des critères de détection
        if projected_home_xg >= (projected_away_xg + 0.8) and combined_stability >= 0.35:
            pattern_match = True
            selected_pick = "1X (Double Chance Domicile)"
            pattern_confidence = min(98.5, 80.0 + (combined_stability * 25))

        elif projected_away_xg >= (projected_home_xg + 0.8) and combined_stability >= 0.35:
            pattern_match = True
            selected_pick = "X2 (Double Chance Extérieur)"
            pattern_confidence = min(98.5, 80.0 + (combined_stability * 25))

        elif (projected_home_xg + projected_away_xg) >= 1.8:
            pattern_match = True
            selected_pick = "Plus de 1.5 Buts dans le match"
            pattern_confidence = min(97.5, 78.0 + (combined_stability * 22))

        return {
            "pattern_found": pattern_match,
            "selected_pick": selected_pick,
            "pattern_confidence": round(pattern_confidence, 1),
            "stability_score": round(combined_stability, 3),
            "projected_xg": {
                "home": round(projected_home_xg, 2),
                "away": round(projected_away_xg, 2)
            }
        }

pattern_agent = PatternExtractionAgent()

# ==========================================
# GENERATEUR D'HISTORIQUE & PIPELINE
# ==========================================

def generate_simulated_history(match_id, team_name, is_home=True):
    history = []
    base_seed = (hash(str(match_id) + team_name) % 1000) / 1000.0
    
    for i in range(5):
        offset = (i * 0.15)
        xg_f = round(max(0.6, 1.2 + (base_seed * 1.5) - offset), 2)
        xg_a = round(max(0.4, 0.8 + ((1.0 - base_seed) * 1.2) - offset), 2)
        gf = int(xg_f + (0.5 if base_seed > 0.5 else 0))
        ga = int(xg_a)

        history.append({
            "goals_for": gf,
            "goals_against": ga,
            "xg_for": xg_f,
            "xg_against": xg_a
        })
    return history

def run_prediction_pipeline(match_id, home_team, away_team):
    home_hist = generate_simulated_history(match_id, home_team, is_home=True)
    away_hist = generate_simulated_history(match_id, away_team, is_home=False)

    evaluation = pattern_agent.evaluate_match_pattern(home_hist, away_hist)

    if not evaluation["pattern_found"]:
        return None

    xg_h = evaluation["projected_xg"]["home"]
    xg_a = evaluation["projected_xg"]["away"]

    demographics = {
        "dom_domination": int(min(90, (xg_h / (xg_h + xg_a + 0.1)) * 100)),
        "ext_domination": int(min(90, (xg_a / (xg_h + xg_a + 0.1)) * 100)),
        "draw_prob": int(max(10, 100 - ((xg_h + xg_a) * 20))),
        "attack_pressure": int(min(98, (xg_h + xg_a) * 26)),
        "defense_stability": int(min(98, evaluation["stability_score"] * 100))
    }

    return {
        "xg_home": xg_h,
        "xg_away": xg_a,
        "selected_pick": evaluation["selected_pick"],
        "confidence": evaluation["pattern_confidence"],
        "is_high_reliability": evaluation["pattern_confidence"] >= 85.0,
        "demographics": demographics
    }

# ==========================================
# ROUTES FLASK
# ==========================================

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/scan')
def scan_matches():
    now_utc = datetime.now(timezone.utc)
    target_date = now_utc + timedelta(days=2)
    
    headers = {"X-Auth-Token": API_KEY}
    params = {
        "dateFrom": now_utc.strftime("%Y-%m-%d"),
        "dateTo": target_date.strftime("%Y-%m-%d")
    }

    raw_matches = []
    try:
        req = requests.get(f"{BASE_URL}/matches", headers=headers, params=params, timeout=10)
        if req.status_code == 200:
            raw_matches = req.json().get("matches", [])
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

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

        home_name = m.get("homeTeam", {}).get("name", "Domicile")
        away_name = m.get("awayTeam", {}).get("name", "Extérieur")

        analysis = run_prediction_pipeline(m.get("id", 0), home_name, away_name)
        if analysis is None:
            continue

        country = m.get("area", {}).get("name", "International")
        flag = m.get("area", {}).get("flag", "")
        league = m.get("competition", {}).get("name", "Championnat")

        match_data = {
            "id": m.get("id"),
            "home": home_name,
            "away": away_name,
            "league": league,
            "country": country,
            "time": match_dt.strftime("%H:%M"),
            "analysis": analysis
        }

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

    sorted_countries = []
    for c_name, c_data in sorted(grouped.items(), key=lambda item: item[1]["max_confidence"], reverse=True):
        sorted_leagues = []
        for l_name, l_data in sorted(c_data["leagues"].items(), key=lambda item: item[1]["max_confidence"], reverse=True):
            l_data["matches"].sort(key=lambda x: x["analysis"]["confidence"], reverse=True)
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
        "time_window": f"{now_utc.strftime('%Y-%m-%d')} au {target_date.strftime('%Y-%m-%d')}",
        "countries": sorted_countries
    })

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
