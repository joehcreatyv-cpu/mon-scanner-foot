import os
import math
import requests
from datetime import datetime, timedelta, timezone
from flask import Flask, render_template, jsonify

app = Flask(__name__)

API_KEY = os.environ.get("FOOTBALL_DATA_KEY", "6a7f0cc1d0594fe48481f70b3dc9cfe7")
BASE_URL = "https://api.football-data.org/v4"

def poisson_pmf(k, mu):
    if mu <= 0:
        return 0.0
    return (math.pow(mu, k) * math.exp(-mu)) / math.factorial(k)

def analyze_match_advanced(xg_h, xg_a):
    p_home = round(min(85.0, max(15.0, (xg_h / (xg_h + xg_a)) * 100)), 1)
    p_away = round(min(85.0, max(15.0, (xg_a / (xg_h + xg_a)) * 100)), 1)
    p_draw = round(max(5.0, 100.0 - p_home - p_away), 1)

    candidates = [
        {"pick": "1X ou Nul", "confidence": round(p_home + p_draw * 0.5, 1)},
        {"pick": "Plus de 1.5 Buts", "confidence": round(min(92.0, (xg_h + xg_a) * 30), 1)},
        {"pick": "BTTS Oui", "confidence": round(min(88.0, (xg_h * xg_a) * 35), 1)}
    ]
    best = max(candidates, key=lambda x: x["confidence"])

    # Données démographiques & tactiques (Inspirées du modèle 2)
    demographics = {
        "dom_domination": int(p_home),
        "ext_domination": int(p_away),
        "zones": {"attaque": 35, "milieu": 45, "defense": 20},
        "age_intensity": {"1-15m": 72, "16-30m": 84, "31-45m": 65, "46-60m": 78, "61-90m": 88}
    }

    return {
        "xg_home": xg_h,
        "xg_away": xg_a,
        "p_home": p_home,
        "p_draw": p_draw,
        "p_away": p_away,
        "selected_pick": best["pick"],
        "confidence": best["confidence"],
        "demographics": demographics
    }

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/scan')
def scan_matches():
    now_utc = datetime.now(timezone.utc)
    eight_hours = now_utc + timedelta(hours=12)
    
    headers = {"X-Auth-Token": API_KEY}
    params = {"dateFrom": now_utc.strftime("%Y-%m-%d"), "dateTo": eight_hours.strftime("%Y-%m-%d")}

    raw_matches = []
    try:
        req = requests.get(f"{BASE_URL}/matches", headers=headers, params=params, timeout=6)
        if req.status_code == 200:
            raw_matches = req.json().get("matches", [])
    except Exception:
        pass

    # Regroupement strict par Pays / Ligue
    grouped_by_country = {}

    for m in raw_matches:
        utc_str = m.get("utcDate", "")
        if not utc_str:
            continue
        try:
            match_dt = datetime.fromisoformat(utc_str.replace("Z", "+00:00"))
        except ValueError:
            continue

        country = m.get("area", {}).get("name", "International")
        flag = m.get("area", {}).get("flag", "")
        league = m.get("competition", {}).get("name", "Championnat")
        
        analysis = analyze_match_advanced(1.8, 1.2)

        match_data = {
            "id": m.get("id"),
            "home": m.get("homeTeam", {}).get("name"),
            "away": m.get("awayTeam", {}).get("name"),
            "league": league,
            "time": match_dt.strftime("%H:%M"),
            "analysis": analysis
        }

        if country not in grouped_by_country:
            grouped_by_country[country] = {"flag": flag, "matches": []}
        grouped_by_country[country]["matches"].append(match_data)

    return jsonify({
        "status": "success",
        "time_window": f"{now_utc.strftime('%H:%M')} - {eight_hours.strftime('%H:%M')} UTC",
        "countries": grouped_by_country
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
