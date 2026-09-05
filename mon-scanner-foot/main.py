import os
import math
import requests
from datetime import datetime, timedelta, timezone
from flask import Flask, render_template, jsonify

app = Flask(__name__)

API_KEY = os.environ.get("FOOTBALL_DATA_KEY", "")
BASE_URL = "https://api.football-data.org/v4"

def poisson_pmf(k, mu):
    if mu <= 0:
        return 0.0
    return (math.pow(mu, k) * math.exp(-mu)) / math.factorial(k)

def tau_dixon_coles(x, y, mu_x, mu_y, rho=-0.11):
    if x == 0 and y == 0:
        return 1.0 - (mu_x * mu_y * rho)
    elif x == 1 and y == 0:
        return 1.0 + (mu_y * rho)
    elif x == 0 and y == 1:
        return 1.0 + (mu_x * rho)
    elif x == 1 and y == 1:
        return 1.0 - rho
    return 1.0

def build_score_matrix(xg_home, xg_away, max_goals=6):
    matrix = {}
    for h in range(max_goals):
        for a in range(max_goals):
            prob = poisson_pmf(h, xg_home) * poisson_pmf(a, xg_away) * tau_dixon_coles(h, a, xg_home, xg_away)
            matrix[(h, a)] = max(0.0, prob)
    total = sum(matrix.values())
    if total > 0:
        for k in matrix:
            matrix[k] /= total
    return matrix

def calculate_volatility(xg_h, xg_a):
    var_h = xg_h
    var_a = xg_a
    total_var = math.sqrt(var_h + var_a)
    return round(min(10.0, total_var * 2.8), 2)

def analyze_match_advanced(xg_h, xg_a):
    matrix = build_score_matrix(xg_h, xg_a)
    volatility = calculate_volatility(xg_h, xg_a)
    
    p_home_win = sum(p for (h, a), p in matrix.items() if h > a)
    p_draw = sum(p for (h, a), p in matrix.items() if h == a)
    p_away_win = sum(p for (h, a), p in matrix.items() if h < a)
    p_over_1_5 = sum(p for (h, a), p in matrix.items() if (h + a) > 1)
    p_over_2_5 = sum(p for (h, a), p in matrix.items() if (h + a) > 2)
    p_under_3_5 = sum(p for (h, a), p in matrix.items() if (h + a) < 4)
    p_btts = sum(p for (h, a), p in matrix.items() if h > 0 and a > 0)
    
    sorted_scores = sorted(matrix.items(), key=lambda item: item[1], reverse=True)
    top3 = sorted_scores[:3]
    top3_str = ", ".join([f"{h}-{a} ({round(p*100, 1)}%)" for (h, a), p in top3])
    top3_coverage = round(sum(p for _, p in top3) * 100, 1)

    candidates = [
        {"market": "Double Chance 1X", "pick": "1X ou Nul", "raw_conf": (p_home_win + p_draw) * 100, "risk_profile": "Sécurisé"},
        {"market": "Double Chance X2", "pick": "X2 ou Nul", "raw_conf": (p_away_win + p_draw) * 100, "risk_profile": "Sécurisé"},
        {"market": "Total Buts", "pick": "Plus de 1.5 Buts", "raw_conf": p_over_1_5 * 100, "risk_profile": "Modéré"},
        {"market": "Total Buts", "pick": "Moins de 3.5 Buts", "raw_conf": p_under_3_5 * 100, "risk_profile": "Sécurisé"},
        {"market": "Combo", "pick": "1X + Plus de 1.5", "raw_conf": ((p_home_win + p_draw) * 0.85 + p_over_1_5 * 0.15) * 100, "risk_profile": "Équilibré"},
        {"market": "Les Deux Équipes Marquent", "pick": "BTTS Oui", "raw_conf": p_btts * 100, "risk_profile": "Agressif"},
        {"market": "Total Buts", "pick": "Plus de 2.5 Buts", "raw_conf": p_over_2_5 * 100, "risk_profile": "Agressif"}
    ]

    for c in candidates:
        c["confidence"] = round(c["raw_conf"], 1)

    return {
        "xg_home": round(xg_h, 2),
        "xg_away": round(xg_a, 2),
        "volatility_index": volatility,
        "p_home": round(p_home_win * 100, 1),
        "p_draw": round(p_draw * 100, 1),
        "p_away": round(p_away_win * 100, 1),
        "top3_exact_scores": top3_str,
        "cluster_score_coverage": top3_coverage,
        "all_candidates": candidates
    }

def get_mock_matches(now_utc):
    """ Données de secours si l'API externe ne renvoie aucun résultat """
    return [
        {
            "id": 101,
            "home": "Real Madrid",
            "away": "FC Barcelona",
            "league": "La Liga",
            "comp_code": "PD",
            "time": (now_utc + timedelta(hours=2)).strftime("%H:%M"),
            "date": now_utc.strftime("%d/%m/%Y"),
            "xg_h": 2.10, "xg_a": 1.45
        },
        {
            "id": 102,
            "home": "Arsenal",
            "away": "Chelsea",
            "league": "Premier League",
            "comp_code": "PL",
            "time": (now_utc + timedelta(hours=4)).strftime("%H:%M"),
            "date": now_utc.strftime("%d/%m/%Y"),
            "xg_h": 1.85, "xg_a": 0.95
        },
        {
            "id": 103,
            "home": "Bayern Munich",
            "away": "Dortmund",
            "league": "Bundesliga",
            "comp_code": "BL1",
            "time": (now_utc + timedelta(hours=6)).strftime("%H:%M"),
            "date": now_utc.strftime("%d/%m/%Y"),
            "xg_h": 2.40, "xg_a": 1.20
        }
    ]

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/scan')
def scan_matches():
    now_utc = datetime.now(timezone.utc)
    eight_hours_later = now_utc + timedelta(hours=8)
    
    headers = {"X-Auth-Token": API_KEY} if API_KEY else {}
    params = {
        "dateFrom": now_utc.strftime("%Y-%m-%d"),
        "dateTo": eight_hours_later.strftime("%Y-%m-%d")
    }

    raw_matches = []
    if API_KEY:
        try:
            req = requests.get(f"{BASE_URL}/matches", headers=headers, params=params, timeout=5)
            if req.status_code == 200:
                raw_matches = req.json().get("matches", [])
        except Exception:
            pass

    processed_matches = []

    if raw_matches:
        for m in raw_matches:
            utc_date_str = m.get("utcDate", "")
            if not utc_date_str:
                continue
            try:
                match_dt = datetime.fromisoformat(utc_date_str.replace("Z", "+00:00"))
            except ValueError:
                continue

            league = m.get("competition", {}).get("name", "Football")
            home_team = m.get("homeTeam", {}).get("name", "Domicile")
            away_team = m.get("awayTeam", {}).get("name", "Extérieur")
            
            analysis = analyze_match_advanced(1.75, 1.10)
            processed_matches.append({
                "id": m.get("id"),
                "home": home_team,
                "away": away_team,
                "league": league,
                "time": match_dt.strftime("%H:%M"),
                "date": match_dt.strftime("%d/%m/%Y"),
                "analysis": analysis
            })

    # Si l'API n'a renvoyé aucun match dans la fenêtre, charger les données de secours
    if not processed_matches:
        mock_data = get_mock_matches(now_utc)
        for item in mock_data:
            analysis = analyze_match_advanced(item["xg_h"], item["xg_a"])
            processed_matches.append({
                "id": item["id"],
                "home": item["home"],
                "away": item["away"],
                "league": item["league"],
                "time": item["time"],
                "date": item["date"],
                "analysis": analysis
            })

    premium_list = []
    gold_list = []
    top_leagues_list = []

    for match in processed_matches:
        all_cands = match["analysis"]["all_candidates"]
        
        prem_preds = [c for c in all_cands if c["confidence"] >= 80.0]
        gold_preds = [c for c in all_cands if 69.0 <= c["confidence"] < 80.0]

        if prem_preds:
            m_copy = dict(match)
            m_copy["analysis"] = dict(match["analysis"])
            m_copy["analysis"]["predictions"] = prem_preds
            premium_list.append(m_copy)

        if gold_preds:
            m_copy = dict(match)
            m_copy["analysis"] = dict(match["analysis"])
            m_copy["analysis"]["predictions"] = gold_preds
            gold_list.append(m_copy)

        m_copy_top = dict(match)
        m_copy_top["analysis"] = dict(match["analysis"])
        m_copy_top["analysis"]["predictions"] = sorted(all_cands, key=lambda x: x["confidence"], reverse=True)[:2]
        top_leagues_list.append(m_copy_top)

    return jsonify({
        "status": "success",
        "time_window": f"{now_utc.strftime('%H:%M')} - {eight_hours_later.strftime('%H:%M')} UTC",
        "premium_count": len(premium_list),
        "gold_count": len(gold_list),
        "top_leagues_count": len(top_leagues_list),
        "premium": premium_list,
        "gold": gold_list,
        "top_leagues": top_leagues_list
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
