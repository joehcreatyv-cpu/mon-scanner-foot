import math
import requests
from datetime import datetime, timezone
from flask import Flask, jsonify, render_template_string

app = Flask(__name__)

@app.route('/')
def home():
    with open('templates/index.html', 'r', encoding='utf-8') as f:
        return render_template_string(f.read())

# --- 1. FONCTIONS MATHÉMATIQUES AVANCÉES ---

def poisson_pmf(lmbda, k):
    """Calcule la probabilité exacte pour k événements avec la loi de Poisson"""
    if lmbda <= 0 and k == 0:
        return 1.0
    elif lmbda <= 0:
        return 0.0
    return (math.pow(lmbda, k) * math.exp(-lmbda)) / math.factorial(k)

def dixon_coles_adjustment(h, a, exp_h, exp_a, rho=-0.13):
    """
    Ajustement de Dixon-Coles pour corriger la sous-estimation de Poisson 
    sur les scores bas (0-0, 1-0, 0-1, 1-1).
    """
    if h == 0 and a == 0:
        return 1.0 - (exp_h * exp_a * rho)
    elif h == 0 and a == 1:
        return 1.0 + (exp_h * rho)
    elif h == 1 and a == 0:
        return 1.0 + (exp_a * rho)
    elif h == 1 and a == 1:
        return 1.0 - rho
    return 1.0

# --- 2. MOTEUR PRÉDICTIF HAUTE FINESSE ---

def analyze_match_advanced(home_team, away_team, home_att=1.5, home_def=0.6, away_att=0.9, away_def=1.3):
    league_avg_home = 1.35
    league_avg_away = 1.10

    exp_home_goals = home_att * away_def * league_avg_home
    exp_away_goals = away_att * home_def * league_avg_away

    # Matrice de Dixon-Coles 6x6
    prob_matrix = []
    total_prob = 0.0
    
    for h in range(6):
        row = []
        for a in range(6):
            base_p = poisson_pmf(exp_home_goals, h) * poisson_pmf(exp_away_goals, a)
            adj = dixon_coles_adjustment(h, a, exp_home_goals, exp_away_goals)
            final_p = base_p * adj
            row.append(final_p)
            total_prob += final_p
        prob_matrix.append(row)

    # Normalisation de la matrice
    for h in range(6):
        for a in range(6):
            prob_matrix[h][a] /= total_prob

    # Calcul des probabilités de marché
    prob_home_win = sum(prob_matrix[h][a] for h in range(6) for a in range(6) if h > a)
    prob_draw = sum(prob_matrix[h][a] for h in range(6) for a in range(6) if h == a)
    prob_away_win = sum(prob_matrix[h][a] for h in range(6) for a in range(6) if a > h)

    prob_1x = prob_home_win + prob_draw
    prob_x2 = prob_away_win + prob_draw

    prob_over_1_5 = sum(prob_matrix[h][a] for h in range(6) for a in range(6) if h + a > 1)
    prob_over_2_5 = sum(prob_matrix[h][a] for h in range(6) for a in range(6) if h + a > 2)
    prob_under_3_5 = sum(prob_matrix[h][a] for h in range(6) for a in range(6) if h + a < 4)

    prob_btts = sum(prob_matrix[h][a] for h in range(1, 6) for a in range(1, 6))

    # Combos Intelligents
    prob_1x_and_over15 = sum(prob_matrix[h][a] for h in range(6) for a in range(6) if h >= a and (h + a) > 1)
    prob_btts_and_over25 = sum(prob_matrix[h][a] for h in range(1, 6) for a in range(1, 6) if (h + a) > 2)

    # Recherche des 3 scores exacts les plus probables (Cluster)
    scores_list = []
    for h in range(6):
        for a in range(6):
            scores_list.append(((h, a), prob_matrix[h][a]))
    scores_list.sort(key=lambda x: x[1], reverse=True)
    top3_scores = scores_list[:3]
    cluster_prob = sum(s[1] for s in top3_scores)
    top3_formatted = ", ".join([f"{s[0][0]}-{s[0][1]} ({round(s[1]*100, 1)}%)" for s in top3_scores])

    # Évaluation du Niveau de Risque & Finesse
    variance = math.sqrt(exp_home_goals + exp_away_goals)
    if variance < 1.4 and (prob_1x >= 0.82 or prob_x2 >= 0.82):
        risk_level = "SÉCURISÉ (Faible Volatilité)"
    elif variance >= 1.4 and prob_btts >= 0.70:
        risk_level = "RISQUE CALCULÉ AGRESSIF (Match Ouvert)"
    else:
        risk_level = "MODÉRÉ"

    predictions = []

    # FILTRAGE DE HAUTE PRÉCISION (Seuils d'élite)
    if prob_1x_and_over15 >= 0.78:
        predictions.append({
            "market": "COMBO SÛR",
            "pick": f"{home_team} ou Nul ET Plus de 1.5 Buts",
            "confidence": round(prob_1x_and_over15 * 100, 1),
            "risk_profile": risk_level
        })

    if prob_btts_and_over25 >= 0.68:
        predictions.append({
            "market": "VALEUR AGRESSIVE",
            "pick": "Les 2 équipes marquent ET Plus de 2.5 Buts",
            "confidence": round(prob_btts_and_over25 * 100, 1),
            "risk_profile": "RISQUE CALCULÉ"
        })

    if prob_under_3_5 >= 0.85:
        predictions.append({
            "market": "GESTION DE RISQUE",
            "pick": "Moins de 3.5 Buts Dans le Match",
            "confidence": round(prob_under_3_5 * 100, 1),
            "risk_profile": "SÉCURISÉ"
        })

    if prob_1x >= 0.84:
        predictions.append({
            "market": "DOUBLE CHANCE BLINDÉE",
            "pick": f"{home_team} ou Nul (1X)",
            "confidence": round(prob_1x * 100, 1),
            "risk_profile": "SÉCURISÉ"
        })
    elif prob_x2 >= 0.84:
        predictions.append({
            "market": "DOUBLE CHANCE BLINDÉE",
            "pick": f"{away_team} ou Nul (X2)",
            "confidence": round(prob_x2 * 100, 1),
            "risk_profile": "SÉCURISÉ"
        })

    return {
        "xg_home": round(exp_home_goals, 2),
        "xg_away": round(exp_away_goals, 2),
        "volatility_index": round(variance, 2),
        "top3_exact_scores": top3_formatted,
        "cluster_score_coverage": round(cluster_prob * 100, 1),
        "predictions": predictions
    }

# --- 3. REQUÊTE API OPTIMISÉE POUR PLAN GRATUIT ---

def get_live_matches_from_api():
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    url = f"https://api.football-data.org/v4/matches?dateFrom={today_str}&dateTo={today_str}"
    headers = {'X-Auth-Token': '6a7f0cc1d0594fe48481f70b3dc9cfe7'}
    
    try:
        response = requests.get(url, headers=headers, timeout=6)
        if response.status_code == 429:
            print("Quota atteint (10 requêtes/min max).")
            return []
            
        if response.status_code == 200:
            data = response.json()
            matches = data.get('matches', [])
            parsed = []
            for m in matches:
                utc_date = datetime.fromisoformat(m['utcDate'].replace('Z', '+00:00'))
                parsed.append({
                    "id": m.get('id'),
                    "league": m.get('competition', {}).get('name', 'Ligue'),
                    "time": utc_date.strftime("%H:%M"),
                    "home": m['homeTeam']['shortName'] or m['homeTeam']['name'],
                    "away": m['awayTeam']['shortName'] or m['awayTeam']['name'],
                })
            return parsed
    except Exception as e:
        print("Erreur de connexion API :", e)
    
    return []

@app.route('/api/scan')
def scan():
    raw_matches = get_live_matches_from_api()
    
    filtered_matches = []
    for match in raw_matches:
        analysis = analyze_match_advanced(match["home"], match["away"])
        
        # Conserver uniquement les matchs avec une prédiction à valeur stratégique
        if analysis["predictions"]:
            match["analysis"] = analysis
            filtered_matches.append(match)

    return jsonify({"status": "success", "count": len(filtered_matches), "data": filtered_matches})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
