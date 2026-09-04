import math
from datetime import datetime, timedelta
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

def analyze_match(home_team, away_team, home_att, home_def, away_att, away_def, league_avg_home, league_avg_away):
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

def get_daily_matches():
    # 1. Obtention de l'instant précis du clic
    now = datetime.now()
    eight_hours_later = now + timedelta(hours=8)

    # Simulation de matchs générés dynamiquement POUR AUJOURD'HUI dans la fenêtre des 8h à venir
    # NOTE : Dans la version finale avec API, ces données proviennent directement du flux API-Football
    raw_matches = [
        {
            "id": 1, 
            "datetime": (now + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M"), 
            "home": "Arsenal", "away": "Everton", 
            "home_att": 1.4, "home_def": 0.6, "away_att": 0.7, "away_def": 1.3
        },
        {
            "id": 2, 
            "datetime": (now + timedelta(hours=4)).strftime("%Y-%m-%d %H:%M"), 
            "home": "Real Madrid", "away": "Getafe", 
            "home_att": 1.6, "home_def": 0.5, "away_att": 0.6, "away_def": 1.2
        },
        {
            "id": 3, 
            "datetime": (now + timedelta(hours=12)).strftime("%Y-%m-%d %H:%M"), # Hors fenêtre de 8h (sera rejeté)
            "home": "PSG", "away": "Marseille", 
            "home_att": 1.5, "home_def": 0.7, "away_att": 1.1, "away_def": 0.9
        }
    ]

    filtered_matches = []
    for match in raw_matches:
        match_dt = datetime.strptime(match["datetime"], "%Y-%m-%d %H:%M")

        # FILTRAGE STRICT : Le match doit avoir lieu AUJOURD'HUI, ENTRE maintenant et dans 8 heures
        if now <= match_dt <= eight_hours_later:
            analysis = analyze_match(
                match["home"], match["away"],
                match["home_att"], match["home_def"],
                match["away_att"], match["away_def"],
                league_avg_home=1.35, league_avg_away=1.10
            )
            
            if analysis["predictions"]:
                match["time"] = match_dt.strftime("%H:%M")
                match["analysis"] = analysis
                filtered_matches.append(match)

    return filtered_matches

@app.route('/api/scan')
def scan():
    results = get_daily_matches()
    return jsonify({"status": "success", "count": len(results), "data": results})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
