import math
import requests
from datetime import datetime, timezone
from flask import Flask, jsonify, render_template_string

app = Flask(__name__)

# --- PAGE D'ACCUEIL ---
@app.route('/')
def home():
    with open('templates/index.html', 'r', encoding='utf-8') as f:
        return render_template_string(f.read())

# --- ALGORITHME DE POISSON ---
def poisson_probability(lmbda, k):
    return (math.pow(lmbda, k) * math.exp(-lmbda)) / math.factorial(k)

def analyze_match(home_team, away_team, home_att, home_def, away_att, away_def, league_avg_home=1.35, league_avg_away=1.10):
    expected_home_goals = home_att * away_def * league_avg_home
    expected_away_goals = away_att * home_def * league_avg_away

    prob_matrix = []
    for h in range(6):
        row = []
        for a in range(6):
            p = poisson_probability(expected_home_goals, h) * poisson_probability(expected_away_goals, a)
            row.append(p)
        prob_matrix.append(row)

    prob_over_0_5 = 1 - (prob_matrix[0][0])
    prob_over_1_5 = prob_over_0_5 - sum(prob_matrix[h][a] for h in range(6) for a in range(6) if h + a == 1)
    
    prob_home_or_draw = sum(prob_matrix[h][a] for h in range(6) for a in range(6) if h >= a)
    prob_away_or_draw = sum(prob_matrix[h][a] for h in range(6) for a in range(6) if a >= h)

    predictions = []

    if prob_over_0_5 >= 0.85:
        predictions.append({"type": "Plus de 0.5 Buts", "confidence": round(prob_over_0_5 * 100, 1)})
    
    if prob_over_1_5 >= 0.80:
        predictions.append({"type": "Plus de 1.5 Buts", "confidence": round(prob_over_1_5 * 100, 1)})
        
    if prob_home_or_draw >= 0.82:
        predictions.append({"type": f"Double Chance: {home_team} ou Nul", "confidence": round(prob_home_or_draw * 100, 1)})
    elif prob_away_or_draw >= 0.82:
        predictions.append({"type": f"Double Chance: {away_team} ou Nul", "confidence": round(prob_away_or_draw * 100, 1)})

    return {
        "home_xg": round(expected_home_goals, 2),
        "away_xg": round(expected_away_goals, 2),
        "predictions": predictions
    }

# --- RÉCUPÉRATION DES MATCHS EN DIRECT VIA FOOTBALL-DATA.ORG ---
def get_live_matches_from_api():
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    url = f"https://api.football-data.org/v4/matches?dateFrom={today_str}&dateTo={today_str}"
    
    # Votre clé API personnalisée
    headers = {'X-Auth-Token': '6a7f0cc1d0594fe48481f70b3dc9cfe7'}
    
    try:
        response = requests.get(url, headers=headers, timeout=8)
        if response.status_code == 200:
            data = response.json()
            matches = data.get('matches', [])
            parsed = []
            for m in matches:
                utc_date = datetime.fromisoformat(m['utcDate'].replace('Z', '+00:00'))
                parsed.append({
                    "id": m.get('id'),
                    "time": utc_date.strftime("%H:%M"),
                    "datetime_utc": utc_date,
                    "home": m['homeTeam']['shortName'] or m['homeTeam']['name'],
                    "away": m['awayTeam']['shortName'] or m['awayTeam']['name'],
                    "home_att": 1.4, "home_def": 0.7,
                    "away_att": 0.8, "away_def": 1.2
                })
            return parsed
    except Exception as e:
        print("Erreur API :", e)
    return []

@app.route('/api/scan')
def scan():
    raw_matches = get_live_matches_from_api()
    
    filtered_matches = []
    for match in raw_matches:
        analysis = analyze_match(
            match["home"], match["away"],
            match["home_att"], match["home_def"],
            match["away_att"], match["away_def"]
        )
        
        if analysis["predictions"]:
            match["analysis"] = analysis
            filtered_matches.append(match)

    return jsonify({"status": "success", "count": len(filtered_matches), "data": filtered_matches})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
