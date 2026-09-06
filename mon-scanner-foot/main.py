import numpy as np

class PatternExtractionAgent:
    def __init__(self, min_sample_size=10):
        self.min_sample_size = min_sample_size

    def extract_team_signature(self, match_history, is_home=True):
        """
        Génère la matrice d'empreinte digitale d'une équipe à partir de son historique.
        """
        if len(match_history) < self.min_sample_size:
            return None  # Échantillon insuffisant = rejet automatique

        xg_for = []
        xg_against = []
        conversion_rates = []
        resilience_scores = []

        for m in match_history:
            # Extraction des données d'un match de l'historique
            gf = m['goals_for']
            ga = m['goals_against']
            xg_f = m['xg_for']
            xg_a = m['xg_against']

            xg_for.append(xg_f)
            xg_against.append(xg_a)

            # Taux de conversion de la pression
            conv = (gf / xg_f) if xg_f > 0 else 1.0
            conversion_rates.append(conv)

            # Capacité à encaisser sous pression
            res = (1.0 / (ga + 1.0)) * (xg_a + 0.5)
            resilience_scores.append(res)

        # Calcul des moyennes et de la stabilité (Écart-type inverse)
        mean_xg_f = np.mean(xg_for)
        std_xg_f = np.std(xg_for)
        mean_xg_a = np.mean(xg_against)
        std_xg_a = np.std(xg_against)

        # Indice de régularité (Plus l'écart-type est bas, plus le pattern est stable)
        stability_score = 1.0 / (1.0 + std_xg_f + std_xg_a)

        signature = {
            "expected_xg_f": round(float(mean_xg_f), 2),
            "expected_xg_a": round(float(mean_xg_a), 2),
            "conversion_factor": round(float(np.mean(conversion_rates)), 2),
            "resilience_factor": round(float(np.mean(resilience_scores)), 2),
            "stability_index": round(float(stability_score), 3)
        }

        return signature

    def evaluate_match_pattern(self, home_history, away_history):
        """
        Croise les signatures des deux équipes pour déterminer si un motif
        reducteur d'incertitude est détecté.
        """
        sig_home = self.extract_team_signature(home_history, is_home=True)
        sig_away = self.extract_team_signature(away_history, is_home=False)

        if not sig_home or not sig_away:
            return {"pattern_found": False, "confidence": 0.0, "reason": "Historique insuffisant"}

        # Stabilité combinée du match
        combined_stability = (sig_home["stability_index"] + sig_away["stability_index"]) / 2.0

        # Simulation du match croisé
        projected_home_xg = sig_home["expected_xg_f"] * (sig_away["expected_xg_a"] / 1.2)
        projected_away_xg = sig_away["expected_xg_f"] * (sig_home["expected_xg_a"] / 1.2)

        # Vérification des conditions d'un pattern "Sécurité Maximale"
        pattern_match = False
        selected_pick = None
        pattern_confidence = 0.0

        # Pattern A : Dominance ultra-stable à domicile
        if projected_home_xg >= (projected_away_xg + 1.2) and combined_stability >= 0.55:
            pattern_match = True
            selected_pick = "1X (Double Chance)"
            pattern_confidence = min(98.5, 85.0 + (combined_stability * 20))

        # Pattern B : Verrou défensif (Faible total de buts prévisible)
        elif (projected_home_xg + projected_away_xg) < 1.6 and combined_stability >= 0.60:
            pattern_match = True
            selected_pick = "Under 3.5 Goals"
            pattern_confidence = min(99.0, 88.0 + (combined_stability * 18))

        # Pattern C : Volume d'attaque constant des deux côtés
        elif projected_home_xg >= 1.4 and projected_away_xg >= 1.2 and combined_stability >= 0.50:
            pattern_match = True
            selected_pick = "Over 1.5 Goals"
            pattern_confidence = min(97.5, 84.0 + (combined_stability * 22))

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
