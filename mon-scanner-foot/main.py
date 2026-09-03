import math
from datetime import datetime
from flask import Flask, jsonify, render_template_string

app = Flask(__name__)

# --- ALGORITHME DE POISSON ---
def poisson_probability(lmbda, k):
    """Calcule la probabilité P(X = k) selon la loi de Poisson."""
    return (math.pow(lmbda, k) * math.exp(-lmbda)) / math.factorial(k)

def analyze_match(home_team, away_team, home_att, home_def, away_att, away_def, league_avg_home, league_avg_away):
    """
    Calcule les probabilités de résultat et d'objectifs de buts.
    """
    # Attente de buts (xG estimé)
    expected_home_goals = home_att * away_def * league_avg_home
    expected_away_goals = away_att * home_def * league_avg_away

    # Matrice de probabilités de scores (de 0 à 5 buts)
    prob_matrix = []
    for h in range(6):
        row = []
        for a in range(6):
            p = poisson_probability(expected_home_goals, h) * poisson_probability(expected_away_goals, a)
            row.append(p)
        prob_matrix.append(row)

    # Probabilités agrégées
    prob_over_0_5 = 1 - (prob_matrix[0][0])
    prob_over_1_5 = prob_over_0_5 - sum(prob_matrix[h][a] for h in range(6) for a in range(6) if h + a == 1)
    
    prob_home_or_draw = sum(prob_matrix[h][a] for h in range(6) for a in range(6) if h >= a)
    prob_away_or_draw = sum(prob_matrix[h][a] for h in range(6) for a in range(6) if a >= h)

    # Sélection des meilleures prédictions (Seuil de haute confiance >= 80%)
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

# --- DONNÉES SIMULÉES / API DUMMY ---
def get_daily_matches():
    """
    Exemple de flux provenant de l'API.
    Filtre automatiquement les matchs entre 06:00 et 18:00.
    """
    raw_matches = [
        {"id": 1, "time": "08:30", "home": "Arsenal", "away": "Everton", "home_att": 1.4, "home_def": 0.6, "away_att": 0.7, "away_def": 1.3},
        {"id": 2, "time": "11:00", "home": "Real Madrid", "away": "Getafe", "home_att": 1.6, "home_def": 0.5, "away_att": 0.6, "away_def": 1.2},
        {"id": 3, "time": "15:15", "home": "Bayern Munich", "away": "Bochum", "home_att": 1.8, "home_def": 0.4, "away_att": 0.5, "away_def": 1.5},
        {"id": 4, "time": "20:45", "home": "PSG", "away": "Marseille", "home_att": 1.5, "home_def": 0.7, "away_att": 1.1, "away_def": 0.9} # Sera filtré (hors 06h-18h)
    ]

    filtered_matches = []
    for match in raw_matches:
        match_time = datetime.strptime(match["time"], "%H:%M").time()
        start_window = datetime.strptime("06:00", "%H:%M").time()
        end_window = datetime.strptime("18:00", "%H:%M").time()

        # Filtrage strict de la fenêtre horaire (06:00 à 18:00)
        if start_window <= match_time <= end_window:
            analysis = analyze_match(
                match["home"], match["away"],
                match["home_att"], match["home_def"],
                match["away_att"], match["away_def"],
                league_avg_home=1.35, league_avg_away=1.10
            )
            
            # Ne garder que si au moins un pronostic dépasse le seuil de haute confiance
            if analysis["predictions"]:
                match["analysis"] = analysis
                filtered_matches.append(match)

    return filtered_matches

@app.route('/api/scan')
def scan():
    results = get_daily_matches()
    return jsonify({"status": "success", "count": len(results), "data": results})

if __name__ == '__main__':
    app.run(debug=True, port=5000)