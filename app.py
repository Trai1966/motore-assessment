"""
Motore di assessment manageriale con architettura estrattiva.
Legge framework.json, chiama Qwen su Groq per estrarre comportamenti,
calcola la fascia con punteggio pesato, applica anti-pattern.
"""

import os
import json
import time
import urllib.request
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MODELLO = "qwen/qwen3.8-27b"

# Carica il framework dal file JSON
FRAMEWORK_PATH = os.path.join(os.path.dirname(__file__), "framework.json")
with open(FRAMEWORK_PATH, "r", encoding="utf-8") as f:
    FRAMEWORK = json.load(f)

# Mappatura domande → aree
DOMANDE_AREA = {
    "Q1": "H1", "Q2": "H2", "Q3": "H3", "Q4": "H4",
    "Q5": "S1", "Q6": "S2", "Q7": "S3", "Q8": "S4",
    # Q9-Q12 saranno mappate dinamicamente in base alle aree deboli
}


def chiama_llm(prompt, max_tokens=1500):
    """Chiama l'API di Groq."""
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    }
    body = {
        "model": MODELLO,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_tokens": max_tokens
    }
    req = urllib.request.Request(
        GROQ_URL,
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST"
    )
    with urllib.request.urlopen(req) as response:
        risultato = json.loads(response.read().decode("utf-8"))
    return risultato["choices"][0]["message"]["content"].strip()


def estrai_comportamenti(area_id, risposte_area):
    """Estrae i comportamenti presenti nelle risposte di un'area."""
    area = FRAMEWORK["aree"][area_id]
    lista_comportamenti = []
    for codice, dati in area["comportamenti"].items():
        lista_comportamenti.append(f"{codice} — {dati['nome']}: {dati['descrizione']}")
    lista_ap = []
    for codice, dati in area["anti_pattern"].items():
        lista_ap.append(f"{codice} — {dati['nome']}: {dati['descrizione']}")

    risposte_testo = "\n\n".join([f"Risposta {i+1}: {r}" for i, r in enumerate(risposte_area)])
    comportamenti_testo = "\n".join(lista_comportamenti)
    ap_testo = "\n".join(lista_ap)

    prompt = f"""Sei un analista. Leggi le risposte di un manager e verifica la presenza di ciascun comportamento e anti-pattern.

RISPOSTE DEL MANAGER:
{risposte_testo}

COMPORTAMENTI DA VERIFICARE (area {area['nome']}):
{comportamenti_testo}

ANTI-PATTERN DA VERIFICARE:
{ap_testo}

ISTRUZIONI:
- Per ogni comportamento, decidi se è PRESENTE (true) o ASSENTE (false) nelle risposte.
- Per ogni anti-pattern, decidi se è PRESENTE (true) o ASSENTE (false).
- Considera anche i comportamenti desumibili, non solo quelli esplicitamente citati.
- Non inventare. Se non è chiaro, rispondi false.

Rispondi SOLO con un JSON valido con questa struttura esatta:
{{
  "comportamenti": {{
    "E1": true/false,
    "E2": true/false,
    ...
  }},
  "anti_pattern": {{
    "AP1": true/false,
    ...
  }}
}}

Nessun'altra parola. Solo il JSON."""

    risposta = chiama_llm(prompt)
    # Estrai il JSON dalla risposta (potrebbe avere testo attorno)
    inizio = risposta.find("{")
    fine = risposta.rfind("}") + 1
    if inizio == -1 or fine == 0:
        raise ValueError(f"Risposta LLM non contiene JSON: {risposta}")
    json_str = risposta[inizio:fine]
    return json.loads(json_str)


def calcola_punteggio(area_id, comportamenti):
    """Calcola il punteggio pesato di un'area."""
    area = FRAMEWORK["aree"][area_id]
    pesi = FRAMEWORK["meta"]["pesi"]
    
    punteggio = 0
    dettagli = []
    for codice, presente in comportamenti.items():
        if presente and codice in area["comportamenti"]:
            fascia = area["comportamenti"][codice]["fascia"]
            peso = pesi[fascia]
            punteggio += peso
            dettagli.append({
                "codice": codice,
                "nome": area["comportamenti"][codice]["nome"],
                "fascia": fascia,
                "peso": peso
            })
    return punteggio, dettagli


def punteggio_a_fascia(punteggio):
    """Converte un punteggio in fascia secondo le soglie."""
    for soglia in FRAMEWORK["meta"]["soglie"]:
        if soglia["min"] <= punteggio <= soglia["max"]:
            return soglia["fascia"]
    return "F"


def applica_anti_pattern(fascia_base, punteggio, ap_presenti, n_comportamenti):
    """
    Applica la regola anti-pattern.
    Se sono presenti anti-pattern, abbassa la fascia secondo la regola:
    - Anti-pattern unico, poche evidenze → E o F
    - Anti-pattern + evidenze adeguate → D
    - Anti-pattern + evidenze forti → C
    """
    n_ap = sum(1 for v in ap_presenti.values() if v)
    if n_ap == 0:
        return fascia_base, "Nessun anti-pattern rilevato."
    
    # Regola di abbassamento
    ordine_fasce = ["F", "E", "D", "C", "B", "A"]
    idx_base = ordine_fasce.index(fascia_base) if fascia_base in ordine_fasce else 0
    
    if n_comportamenti <= 2:
        # Solo anti-pattern, poche evidenze positive
        nuova = "F" if n_ap > 1 else "E"
        idx_nuova = ordine_fasce.index(nuova)
    elif fascia_base in ["A", "B"]:
        # Evidenze positive forti → C
        idx_nuova = ordine_fasce.index("C")
    else:
        # Evidenze positive adeguate → D
        idx_nuova = ordine_fasce.index("D")
    
    idx_finale = min(idx_base, idx_nuova)
    fascia_finale = ordine_fasce[idx_finale]
    
    motivazione = f"Anti-pattern rilevati: {n_ap}. Fascia base {fascia_base} → ridotta a {fascia_finale}."
    return fascia_finale, motivazione


def fascia_a_valore(fascia):
    """Converte la fascia in valore numerico."""
    valori = {"A": 4.7, "B": 4.2, "C": 3.7, "D": 3.2, "E": 2.5, "F": 1.5}
    return valori.get(fascia, 1.5)


def valuta_area(area_id, risposte_area):
    """Valuta un'area completa: estrazione + calcolo + anti-pattern."""
    try:
        estrazione = estrai_comportamenti(area_id, risposte_area)
        comportamenti = estrazione.get("comportamenti", {})
        anti_pattern = estrazione.get("anti_pattern", {})
    except Exception as e:
        return {
            "fascia": "F",
            "valore": 1.5,
            "errore": str(e),
            "punteggio_grezzo": 0,
            "dettagli": []
        }
    
    punteggio, dettagli = calcola_punteggio(area_id, comportamenti)
    fascia_base = punteggio_a_fascia(punteggio)
    n_comportamenti = len(dettagli)
    
    fascia_finale, motivazione = applica_anti_pattern(
        fascia_base, punteggio, anti_pattern, n_comportamenti
    )
    
    return {
        "fascia": fascia_finale,
        "valore": fascia_a_valore(fascia_finale),
        "punteggio_grezzo": punteggio,
        "fascia_base": fascia_base,
        "motivazione_ap": motivazione,
        "comportamenti_rilevati": dettagli,
        "anti_pattern_rilevati": [k for k, v in anti_pattern.items() if v]
    }


def valuta_assessment(risposte):
    """Valuta tutte le 8 aree."""
    evidenze_per_area = {area_id: [] for area_id in FRAMEWORK["aree"]}
    for domanda, risposta in risposte.items():
        area_id = DOMANDE_AREA.get(domanda)
        if area_id:
            evidenze_per_area[area_id].append(risposta)
    
    risultati = {}
    for area_id in FRAMEWORK["aree"]:
        evidenze = evidenze_per_area[area_id]
        if not evidenze:
            risultati[area_id] = {
                "fascia": "F",
                "valore": 1.5,
                "punteggio_grezzo": 0,
                "dettagli": []
            }
        else:
            risultati[area_id] = valuta_area(area_id, evidenze)
        time.sleep(8)  # pausa per rispettare il rate limit
    
    return risultati


@app.route('/health')
def health():
    return jsonify({"status": "ok"}), 200


@app.route('/valuta', methods=['POST'])
def valuta():
    dati = request.get_json()
    risposte = dati.get("risposte", {})
    if not risposte:
        return jsonify({"error": "Nessuna risposta fornita"}), 400
    try:
        risultati = valuta_assessment(risposte)
        
        # Calcola medie hard e soft
        medie = {
            "hard": round(sum(risultati[a]["valore"] for a in ["H1","H2","H3","H4"]) / 4, 1),
            "soft": round(sum(risultati[a]["valore"] for a in ["S1","S2","S3","S4"]) / 4, 1)
        }
        
        return jsonify({
            "success": True,
            "risultati": risultati,
            "medie": medie
        }), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port)
