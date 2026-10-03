"""
Motore di assessment manageriale con architettura estrattiva.
Supporta Q1-Q8 (domande base) + POOL-X (approfondimento).
"""

import os
import json
import time
import urllib.request
import urllib.error
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()

GSHEET_WEBHOOK_URL = os.environ.get("GSHEET_WEBHOOK_URL", "")
USA_PROVVISORIA_VELOCE = os.environ.get("PROVVISORIA_VELOCE", "0") == "1"

app = Flask(__name__)
CORS(app)

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MODELLO = "qwen/qwen3.8-27b"

# Carica il framework
FRAMEWORK_PATH = os.path.join(os.path.dirname(__file__), "framework.json")
with open(FRAMEWORK_PATH, "r", encoding="utf-8") as f:
    FRAMEWORK = json.load(f)

# Mappatura Q1-Q8 → aree
DOMANDE_AREA = {
    "Q1": "H1", "Q2": "H2", "Q3": "H3", "Q4": "H4",
    "Q5": "S1", "Q6": "S2", "Q7": "S3", "Q8": "S4",
}

# Mappatura POOL-X → aree
POOL_AREA = {
    "POOL-H1": "H1", "POOL-H2": "H2", "POOL-H3": "H3", "POOL-H4": "H4",
    "POOL-S1": "S1", "POOL-S2": "S2", "POOL-S3": "S3", "POOL-S4": "S4",
}

# Testo delle domande del pool
TESTI_POOL = {
    "POOL-H1": "Durante la fase di test del nuovo servizio ti accorgi che il processo è più lento e costoso del previsto. Cosa fai per migliorare le performance?",
    "POOL-H2": "I dati di mercato sono contraddittori e oscillano: alcuni indicatori salgono, altri scendono. Non è chiaro cosa li muova. Come affronti l'incertezza dei dati?",
    "POOL-H3": "Alcuni membri chiave del team iniziano a manifestare scetticismo verso il progetto. Il loro atteggiamento sta influenzando anche altri. Come intervieni?",
    "POOL-H4": "Il direttore commerciale ti chiede di ridurre i costi del progetto di realizzazione del nuovo servizio del 15%, senza però ridurre la qualità del servizio erogato.",
    "POOL-S1": "Hai 10 interventi urgenti da fare questa settimana, ma il tempo e le risorse ti permettono di realizzarne solo due. Cosa fai?",
    "POOL-S2": "Siamo al terzo mese ed è ormai evidente che il progetto non raggiungerà gli obiettivi fissati. Come ti comporti con i diversi stakeholder?",
    "POOL-S3": "Un collaboratore ti chiede di crescere e avere maggiori deleghe nel progetto. In contemporanea una funzione ti chiede di spostare le scadenze in avanti su un task critico per il progetto. Come affronti le due situazioni?",
    "POOL-S4": "Alla fine del secondo mese, il direttore commerciale ti convoca: la direzione ha rivisto gli obiettivi del progetto. Il servizio deve essere lanciato entro la fine del terzo mese (non più il quarto), il target sale da 10 a 25 clienti, e il budget resta invariato. Il team è lo stesso. Come reagisci?",
}


def area_da_domanda(codice):
    """Restituisce l'area per una domanda (Q1-Q8 o POOL-X)."""
    if codice in DOMANDE_AREA:
        return DOMANDE_AREA[codice]
    if codice in POOL_AREA:
        return POOL_AREA[codice]
    return None


def chiama_llm(prompt, max_tokens=4000, max_retry=5):
    """Chiama l'API di Groq con retry automatico su 429 e 5xx."""
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    }
    body = {
        "model": MODELLO,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "max_tokens": max_tokens,
        "seed": 42
    }
    req = urllib.request.Request(
        GROQ_URL,
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST"
    )
    
    for tentativo in range(max_retry):
        try:
            with urllib.request.urlopen(req) as response:
                risultato = json.loads(response.read().decode("utf-8"))
            return risultato["choices"][0]["message"]["content"].strip()
        except urllib.error.HTTPError as e:
            if e.code == 429:
                attesa = 30 * (tentativo + 1)
                print(f"[RATE LIMIT 429] Tentativo {tentativo+1}/{max_retry}. Attendo {attesa}s...")
                time.sleep(attesa)
                continue
            elif e.code in [500, 502, 503, 504]:
                attesa = 10 * (tentativo + 1)
                print(f"[ERRORE {e.code}] Tentativo {tentativo+1}/{max_retry}. Attendo {attesa}s...")
                time.sleep(attesa)
                continue
            else:
                raise
        except Exception as e:
            print(f"[ERRORE] {e}. Tentativo {tentativo+1}/{max_retry}.")
            time.sleep(10)
            continue
    raise Exception("Errore persistente dopo tutti i tentativi")

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
    ...
  }},
  "anti_pattern": {{
    "AP1": true/false,
    ...
  }}
}}

Nessun'altra parola. Solo il JSON."""

    risposta = chiama_llm(prompt)
    inizio = risposta.find("{")
    fine = risposta.rfind("}") + 1
    if inizio == -1 or fine == 0:
        raise ValueError(f"Risposta LLM non contiene JSON: {risposta}")
    json_str = risposta[inizio:fine]
    return json.loads(json_str)



def rileva_anti_pattern_python(area_id, risposte_area):
    """S3: cerca pattern letterali degli anti-pattern nelle risposte."""
    area = FRAMEWORK["aree"][area_id]
    testo = " ".join(risposte_area).lower()
    rilevati = []
    for codice, dati in area["anti_pattern"].items():
        pattern = dati.get("pattern_letterali", [])
        for frase in pattern:
            if frase.lower() in testo:
                rilevati.append(codice)
                break
    return rilevati


def rileva_anti_pattern_llm(risposte_complete):
    """S2: una chiamata globale per rilevare gli anti-pattern inferiti."""
    risposte_testo = "\n\n".join([f"{k}: {v}" for k, v in risposte_complete.items()])
    
    lista_ap = []
    codici_llm = FRAMEWORK["meta"].get("anti_pattern_llm", [])
    for codice_completo in codici_llm:
        area_id, codice_ap = codice_completo.split(".")
        area = FRAMEWORK["aree"].get(area_id)
        if not area:
            continue
        ap = area["anti_pattern"].get(codice_ap)
        if not ap:
            continue
        lista_ap.append(f"[{area_id}.{codice_ap}] — {ap['nome']}: {ap['descrizione']}")
    lista_ap_testo = "\n".join(lista_ap)
    
    prompt = f"""Sei un valutatore severo. Il tuo UNICO compito è rilevare comportamenti controproducenti (anti-pattern) nelle risposte di un manager.

RISPOSTE DEL MANAGER:
{risposte_testo}

ANTI-PATTERN DA RILEVARE:
{lista_ap_testo}

ISTRUZIONI:
- Cerca SOLO comportamenti negativi. Ignora quelli positivi.
- Anche UNA SOLA frase negativa attiva l'anti-pattern.
- Il fatto che altre risposte siano positive NON è una scusa per non segnalare.
- Sii severo.
- Esempio: "non ti preoccupare e lavora" attiva S1.AP1 (non dà direzione) e S1.AP4 (deresponsabilizza).

Rispondi SOLO con un JSON valido che elenca i codici degli anti-pattern rilevati:
{{
  "anti_pattern": ["S1.AP1", "H3.AP3"]
}}

Se non rilevi nessun anti-pattern, restituisci: {{"anti_pattern": []}}
Nessun'altra parola. Solo il JSON."""

    risposta = chiama_llm(prompt, max_tokens=800)
    inizio = risposta.find("{")
    fine = risposta.rfind("}") + 1
    if inizio == -1 or fine == 0:
        return []
    try:
        dati = json.loads(risposta[inizio:fine])
        return dati.get("anti_pattern", [])
    except Exception:
        return []

def max_punteggio_area(area_id):
    """Calcola il punteggio massimo teorico per un'area."""
    area = FRAMEWORK["aree"][area_id]
    pesi = FRAMEWORK["meta"]["pesi"]
    max_p = 0
    for codice, dati in area["comportamenti"].items():
        max_p += pesi[dati["fascia"]]
    return max_p

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
    for soglia in FRAMEWORK["meta"]["soglie"]:
        if soglia["min"] <= punteggio <= soglia["max"]:
            return soglia["fascia"]
    return "F"


def calcola_valore_modulato(punteggio, fascia, max_area):
    """Calcola il valore modulato dentro la fascia."""
    if fascia == "F":
        return 1.5
    
    for soglia in FRAMEWORK["meta"]["soglie"]:
        if soglia["fascia"] == fascia:
            p_min = soglia["min"]
            v_min = soglia["valore_min"]
            v_max = soglia["valore_max"]
            
            if fascia == "A":
                p_max = max_area
            else:
                p_max = soglia["max"]
            
            if p_max == p_min:
                return round(v_min, 1)
            
            perc = (punteggio - p_min) / (p_max - p_min)
            perc = max(0.0, min(1.0, perc))
            
            valore = v_min + perc * (v_max - v_min)
            return round(valore, 1)
    
    return 3.5

def valuta_area(area_id, risposte_area, ap_rilevati):
    """Valuta un'area. Gli anti-pattern arrivano già rilevati come lista di codici."""
    try:
        estrazione = estrai_comportamenti(area_id, risposte_area)
        comportamenti = estrazione.get("comportamenti", {})
    except Exception as e:
        return {
            "fascia": "F", "valore": 1.5, "errore": str(e),
            "punteggio_grezzo": 0,
            "comportamenti_rilevati": [], "anti_pattern_rilevati": []
        }
    
    punteggio_positivo, dettagli = calcola_punteggio(area_id, comportamenti)
    
    area = FRAMEWORK["aree"][area_id]
    peso_ap = FRAMEWORK["meta"].get("peso_anti_pattern", -8)
    penalita = peso_ap * len(ap_rilevati)
    
    punteggio_finale = max(0, punteggio_positivo + penalita)
    fascia = punteggio_a_fascia(punteggio_finale)
    
    max_area = max_punteggio_area(area_id)
    valore = calcola_valore_modulato(punteggio_finale, fascia, max_area)
    
    return {
        "fascia": fascia,
        "valore": valore,
        "punteggio_grezzo": punteggio_finale,
        "punteggio_positivo": punteggio_positivo,
        "penalita_ap": penalita,
        "punteggio_max": max_area,
        "comportamenti_rilevati": dettagli,
        "anti_pattern_rilevati": ap_rilevati
    }

def estrai_comportamenti_tutte_aree(risposte):
    """Una sola chiamata LLM: estrae comportamenti e anti-pattern per tutte le 8 aree."""
    sezioni = []
    for area_id, area in FRAMEWORK["aree"].items():
        comps = []
        for cod, dati in area["comportamenti"].items():
            comps.append(f"  {cod}: {dati['nome']} - {dati['descrizione']}")
        aps = []
        for cod, dati in area["anti_pattern"].items():
            if f"{area_id}.{cod}" in FRAMEWORK["meta"].get("anti_pattern_llm", []):
                aps.append(f"  {cod}: {dati['nome']} - {dati['descrizione']}")
        blocco = (
            f"AREA {area_id} ({area['nome']}):\n"
            f"Comportamenti:\n" + "\n".join(comps) + "\n"
            f"Anti-pattern:\n" + ("\n".join(aps) if aps else "  (nessuno)")
        )
        sezioni.append(blocco)

    risposte_testo = "\n\n".join([f"{k}: {v}" for k, v in risposte.items()])
    sezioni_testo = "\n\n".join(sezioni)

    prompt = f"""Sei un analista. Leggi le risposte di un manager e, per ciascuna delle 8 aree, indica quali comportamenti sono PRESENTI e quali anti-pattern sono PRESENTI.

RISPOSTE DEL MANAGER:
{risposte_testo}

COMPORTAMENTI E ANTI-PATTERN DA VERIFICARE:

{sezioni_testo}

ISTRUZIONI:
- Per ogni area, elenca SOLO i codici dei comportamenti PRESENTI (true) e degli anti-pattern PRESENTI.
- Considera anche i comportamenti desumibili, non solo quelli esplicitamente citati.
- Non inventare. Se non e chiaro, non includere il codice.
- Sii severo sugli anti-pattern: anche una sola frase negativa li attiva.

Rispondi SOLO con un JSON valido in questo formato esatto:
{{
  "H1": {{"comportamenti": ["E1", "D2"], "anti_pattern": ["AP1"]}},
  "H2": {{"comportamenti": [], "anti_pattern": []}},
  "H3": {{"comportamenti": [], "anti_pattern": []}},
  "H4": {{"comportamenti": [], "anti_pattern": []}},
  "S1": {{"comportamenti": [], "anti_pattern": []}},
  "S2": {{"comportamenti": [], "anti_pattern": []}},
  "S3": {{"comportamenti": [], "anti_pattern": []}},
  "S4": {{"comportamenti": [], "anti_pattern": []}}
}}

Nessun'altra parola. Solo il JSON."""

    risposta = chiama_llm(prompt, max_tokens=4000)
    inizio = risposta.find("{")
    fine = risposta.rfind("}") + 1
    if inizio == -1 or fine == 0:
        raise ValueError(f"Risposta LLM non contiene JSON: {risposta[:200]}")
    dati = json.loads(risposta[inizio:fine])
    for area_id in FRAMEWORK["aree"]:
        if area_id not in dati:
            dati[area_id] = {"comportamenti": [], "anti_pattern": []}
        dati[area_id].setdefault("comportamenti", [])
        dati[area_id].setdefault("anti_pattern", [])
    return dati


def valuta_assessment_veloce(risposte):
    """Versione veloce della provvisoria: una sola chiamata LLM per tutte le 8 aree."""
    evidenze_per_area = {area_id: [] for area_id in FRAMEWORK["aree"]}
    for domanda, risposta in risposte.items():
        area_id = area_da_domanda(domanda)
        if area_id:
            evidenze_per_area[area_id].append(risposta)

    print("[VELOCE] Estrazione unica con LLM...")
    estrazione = estrai_comportamenti_tutte_aree(risposte)

    risultati = {}
    for area_id, area in FRAMEWORK["aree"].items():
        comps_estratti = set(estrazione[area_id]["comportamenti"])
        comps_bool = {cod: (cod in comps_estratti) for cod in area["comportamenti"]}

        ap_da_llm = set(estrazione[area_id]["anti_pattern"])
        ap_da_python = set(rileva_anti_pattern_python(area_id, evidenze_per_area[area_id]))
        ap_per_area = list(ap_da_llm | ap_da_python)

        punteggio_positivo, dettagli = calcola_punteggio(area_id, comps_bool)
        peso_ap = FRAMEWORK["meta"].get("peso_anti_pattern", -8)
        penalita = peso_ap * len(ap_per_area)
        punteggio_finale = max(0, punteggio_positivo + penalita)
        fascia = punteggio_a_fascia(punteggio_finale)
        max_area = max_punteggio_area(area_id)
        valore = calcola_valore_modulato(punteggio_finale, fascia, max_area)

        risultati[area_id] = {
            "fascia": fascia,
            "valore": valore,
            "punteggio_grezzo": punteggio_finale,
            "punteggio_positivo": punteggio_positivo,
            "penalita_ap": penalita,
            "punteggio_max": max_area,
            "comportamenti_rilevati": dettagli,
            "anti_pattern_rilevati": ap_per_area
        }

    return risultati


def valuta_assessment(risposte):
    """Valuta tutte le 8 aree con S2+S3."""
    evidenze_per_area = {area_id: [] for area_id in FRAMEWORK["aree"]}
    for domanda, risposta in risposte.items():
        area_id = area_da_domanda(domanda)
        if area_id:
            evidenze_per_area[area_id].append(risposta)

    # S3: pattern matching Python
    ap_python = {}
    for area_id in FRAMEWORK["aree"]:
        ap_python[area_id] = rileva_anti_pattern_python(area_id, evidenze_per_area[area_id])
    print("[S3] Anti-pattern rilevati da Python:", ap_python)

    # S2: chiamata LLM globale
    print("[S2] Rilevamento anti-pattern con LLM...")
    ap_llm_globali = rileva_anti_pattern_llm(risposte)
    print("[S2] Anti-pattern rilevati da LLM:", ap_llm_globali)

    # Combina S2 + S3 per area
    ap_per_area = {}
    for area_id in FRAMEWORK["aree"]:
        ap_da_python = set(ap_python[area_id])
        ap_da_llm = set()
        for codice_completo in ap_llm_globali:
            if codice_completo.startswith(f"{area_id}."):
                ap_da_llm.add(codice_completo.split(".")[1])
        ap_per_area[area_id] = list(ap_da_python | ap_da_llm)

    time.sleep(15)

    risultati = {}
    for area_id in FRAMEWORK["aree"]:
        evidenze = evidenze_per_area[area_id]
        if not evidenze:
            risultati[area_id] = {
                "fascia": "F", "valore": 1.5, "punteggio_grezzo": 0,
                "comportamenti_rilevati": [], "anti_pattern_rilevati": []
            }
        else:
            risultati[area_id] = valuta_area(area_id, evidenze, ap_per_area[area_id])
        time.sleep(8)

    return risultati

FASCE_ORDINE = ["E", "D", "C", "B", "A"]

SOGLIA_PF = 1
SOGLIA_NE = 1
COMMENTO_PF_NEUTRO = "Non sono emersi elementi sufficienti per descrivere punti di forza in modo strutturato."
COMMENTO_NE_NEUTRO = "Non sono emersi elementi sufficienti per descrivere aree di miglioramento in modo strutturato."


def fascia_precedente(fascia):
    """Restituisce la fascia immediatamente precedente (E→None, D→E, C→D, B→C, A→B)."""
    if fascia == "F" or fascia not in FASCE_ORDINE:
        return None
    idx = FASCE_ORDINE.index(fascia)
    if idx == 0:
        return None
    return FASCE_ORDINE[idx - 1]


def fasce_rilevanti(fascia_raggiunta):
    """Fasce per i PF: raggiunta + precedente.
    Fascia E -> E + D (non ha precedente).
    Fascia F -> solo E (fallback)."""
    if fascia_raggiunta == "F":
        return ["E"]
    if fascia_raggiunta == "E":
        return ["E", "D"]
    prec = fascia_precedente(fascia_raggiunta)
    if prec is None:
        return [fascia_raggiunta]
    return [prec, fascia_raggiunta]


def fascia_successiva(fascia):
    """Restituisce la fascia immediatamente successiva (A->None, B->A, C->B, D->C, E->D)."""
    if fascia == "F" or fascia not in FASCE_ORDINE:
        return None
    idx = FASCE_ORDINE.index(fascia)
    if idx == len(FASCE_ORDINE) - 1:
        return None
    return FASCE_ORDINE[idx + 1]


def fasce_rilevanti_ne(fascia_raggiunta):
    """Fasce per i NE: raggiunta + 2 successive (mai tutte).
    E -> E,D,C | D -> D,C,B | C -> C,B,A | B -> B,A | A -> A."""
    if fascia_raggiunta == "F" or fascia_raggiunta not in FASCE_ORDINE:
        return ["E"]
    idx = FASCE_ORDINE.index(fascia_raggiunta)
    return FASCE_ORDINE[idx:idx + 3]


def conta_elementi_per_commenti(risultati):
    """Conta i comportamenti filtrati disponibili per i due paragrafi."""
    tot_pf = 0
    tot_ne = 0
    for area_id, r in risultati.items():
        fascia = r.get("fascia", "F")
        if fascia == "F":
            continue
        area = FRAMEWORK["aree"][area_id]
        fasce = fasce_rilevanti(fascia)
        fasce_ne = fasce_rilevanti_ne(fascia)
        true_codici = set(c["codice"] for c in r.get("comportamenti_rilevati", []))
        for cod, dati in area["comportamenti"].items():
            if dati["fascia"] in fasce and cod in true_codici:
                tot_pf += 1
            if dati["fascia"] in fasce_ne and cod not in true_codici:
                tot_ne += 1
    return tot_pf, tot_ne


def costruisci_blocchi_commenti(risultati):
    """Costruisce i blocchi testuali per area da inviare all'LLM."""
    blocchi = []
    for area_id, r in risultati.items():
        fascia = r.get("fascia", "F")
        if fascia == "F":
            continue
        area = FRAMEWORK["aree"][area_id]
        fasce = fasce_rilevanti(fascia)
        fasce_ne = fasce_rilevanti_ne(fascia)
        true_codici = set(c["codice"] for c in r.get("comportamenti_rilevati", []))

        true_filtrati = []
        for cod, dati in area["comportamenti"].items():
            if cod in true_codici and dati["fascia"] in fasce:
                true_filtrati.append(f"{dati['nome']} ({dati['fascia']})")

        # Eccezione: se true filtrati vuoti, includi tutti i true rilevati
        if not true_filtrati:
            for cod, dati in area["comportamenti"].items():
                if cod in true_codici:
                    true_filtrati.append(f"{dati['nome']} ({dati['fascia']})")

        false_filtrati = []
        for cod, dati in area["comportamenti"].items():
            if cod not in true_codici and dati["fascia"] in fasce_ne:
                false_filtrati.append(f"{dati['nome']} ({dati['fascia']})")

        blocco = (
            f"AREA: {area['nome']} ({area_id})\n"
            f"Fascia raggiunta: {fascia}\n"
            f"Punti di forza rilevati ({len(true_filtrati)} elementi): {', '.join(true_filtrati) if true_filtrati else 'nessuno'}\n"
            f"Elementi non emersi ({len(false_filtrati)} elementi): {', '.join(false_filtrati) if false_filtrati else 'nessuno'}"
        )
        blocchi.append(blocco)
    return "\n\n".join(blocchi)


def genera_commenti(risultati):
    """Genera i due paragrafi di commento (punti di forza, elementi non emersi)."""
    blocchi = costruisci_blocchi_commenti(risultati)
    if not blocchi:
        return {"punti_forza": COMMENTO_PF_NEUTRO, "elementi_non_emersi": COMMENTO_NE_NEUTRO}

    tot_pf, tot_ne = conta_elementi_per_commenti(risultati)
    print(f"[COMMENTI] Materiale disponibile: PF={tot_pf}, NE={tot_ne}")

    pf_predefinito = COMMENTO_PF_NEUTRO if tot_pf < SOGLIA_PF else None
    ne_predefinito = COMMENTO_NE_NEUTRO if tot_ne < SOGLIA_NE else None

    if pf_predefinito and ne_predefinito:
        print("[COMMENTI] Materiale insufficiente: nessuna chiamata LLM")
        return {"punti_forza": pf_predefinito, "elementi_non_emersi": ne_predefinito}

    punteggi_hard = ", ".join([
        f"{FRAMEWORK['aree'][a]['nome']} {risultati[a]['valore']:.1f}"
        for a in ["H1", "H2", "H3", "H4"] if a in risultati
    ])
    punteggi_soft = ", ".join([
        f"{FRAMEWORK['aree'][a]['nome']} {risultati[a]['valore']:.1f}"
        for a in ["S1", "S2", "S3", "S4"] if a in risultati
    ])

    prompt = f"""Sei un analista. Ricevi i risultati di un assessment manageriale strutturato in 8 aree.

Punteggi hard: {punteggi_hard}
Punteggi soft: {punteggi_soft}

Dettaglio per area:

{blocchi}

Il tuo compito è produrre due paragrafi di commento: uno sui punti di forza, uno sugli elementi non emersi.
REGOLE PUNTI DI FORZA:
- Terza persona ("il manager ha mostrato", "sono emersi", "il profilo evidenzia"). Mai "tu" o "hai".
- Descrivi comportamenti osservati in modo concreto.
- Non citare testualmente le risposte del manager.
- Non elencare i punteggi numerici.
- Dai priorità agli elementi che ricorrono in più aree.
- Sii coerente con la fascia raggiunta: non descrivere come fragile un'area in fascia A o B.

REGOLE ELEMENTI NON EMERSI:
- Terza persona.
- Formule: "non è emerso che...", "non sono emersi elementi su...".
- Non prescrittivo: descrivi cosa manca, non cosa il manager dovrebbe fare.
- Vietato riformulare o citare indirettamente le domande del questionario.
- Descrivi cosa manca tra gli elementi elencati. Non inventare comportamenti non presenti nella lista.

REGOLE SUL NUMERO DI RIGHE:
- Il numero di righe di ciascun paragrafo deve essere proporzionale al materiale disponibile, non fisso.
- Se hai ricevuto 0-2 elementi complessivi per un paragrafo: scrivi 1-2 righe, oppure una sola frase.
- Se hai ricevuto 3-6 elementi: scrivi 3-4 righe.
- Se hai ricevuto 7 o più elementi: scrivi 5-8 righe.
- Se un paragrafo non ha elementi (0), scrivi una frase breve e neutra, ad esempio: "Non sono emersi elementi sufficienti per descrivere punti di forza in modo strutturato."
- Ogni frase deve essere ancorata a uno degli elementi elencati. NON inventare comportamenti, situazioni o esempi che non compaiono nella lista.

FORMATTAZIONE:
- Plain text. No Markdown, no cancelletti, no grassetto, no elenchi puntati, no virgolette.
- Usa trattini e virgole normali.
- Non mostrare criteri interni, fasce, punteggi.

Rispondi SOLO con un JSON valido:
{{
  "punti_forza": "...",
  "elementi_non_emersi": "..."
}}
Nessun'altra parola. Solo il JSON."""

    try:
        risposta = chiama_llm(prompt, max_tokens=1500)
        inizio = risposta.find("{")
        fine = risposta.rfind("}") + 1
        if inizio == -1 or fine == 0:
            return {
                "punti_forza": pf_predefinito or "",
                "elementi_non_emersi": ne_predefinito or ""
            }
        dati = json.loads(risposta[inizio:fine])
        return {
            "punti_forza": pf_predefinito or dati.get("punti_forza", ""),
            "elementi_non_emersi": ne_predefinito or dati.get("elementi_non_emersi", "")
        }
    except Exception as e:
        print(f"[ERRORE COMMENTI] {e}")
        return {
            "punti_forza": pf_predefinito or "",
            "elementi_non_emersi": ne_predefinito or ""
        }


def salva_sessione(sessione_id, risposte, risultati, medie, commenti, durata_sec, utente=""):
    """Salva la sessione su Google Sheets. Non blocca il flusso se fallisce."""
    if not GSHEET_WEBHOOK_URL:
        return
    try:
        punteggi = {a: {"fascia": r.get("fascia"), "valore": r.get("valore"),
                        "netto": r.get("punteggio_grezzo"),
                        "positivo": r.get("punteggio_positivo"),
                        "penalita": r.get("penalita_ap"),
                        "ap": r.get("anti_pattern_rilevati", [])}
                    for a, r in risultati.items()}
        payload = {
            "sessione_id": sessione_id,
            "utente": utente,
            "durata_sec": durata_sec,
            "n_risposte": len(risposte),
            "risposte": risposte,
            "punteggi": punteggi,
            "medie": medie,
            "commenti": commenti
        }
        req = urllib.request.Request(
            GSHEET_WEBHOOK_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            print(f"[GSHEET] salvato: {resp.status}")
    except Exception as e:
        print(f"[GSHEET] errore (non bloccante): {e}")

@app.route('/health')
def health():
    return jsonify({"status": "ok"}), 200


@app.route('/valuta-provvisoria', methods=['POST'])
def valuta_provvisoria():
    """Valuta Q1-Q8 e restituisce le 4 aree deboli + domande pool."""
    dati = request.get_json()
    risposte = dati.get("risposte", {})
    risposte_q1q8 = {k: v for k, v in risposte.items() if k.startswith("Q")}
    if not risposte_q1q8:
        return jsonify({"error": "Nessuna risposta Q1-Q8 fornita"}), 400
    try:
        if USA_PROVVISORIA_VELOCE:
            risultati = valuta_assessment_veloce(risposte_q1q8)
        else:
            risultati = valuta_assessment(risposte_q1q8)
        
        copertura = {}
        for area_id, r in risultati.items():
            max_p = max_punteggio_area(area_id)
            perc = r["punteggio_grezzo"] / max_p if max_p > 0 else 0
            copertura[area_id] = perc
        
        aree_ordinate = sorted(copertura.items(), key=lambda x: x[1])
        aree_deboli = [area_id for area_id, _ in aree_ordinate[:4]]
        
        mappa_pool = {
            "H1": "POOL-H1", "H2": "POOL-H2", "H3": "POOL-H3", "H4": "POOL-H4",
            "S1": "POOL-S1", "S2": "POOL-S2", "S3": "POOL-S3", "S4": "POOL-S4",
        }
        domande_selezionate = [mappa_pool[a] for a in aree_deboli]
        return jsonify({
            "success": True,
            "aree_deboli": aree_deboli,
            "domande_selezionate": [
                {"codice": c, "testo": TESTI_POOL[c], "area": POOL_AREA[c]}
                for c in domande_selezionate
            ],
            "risultati_provvisori": risultati
        }), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/valuta', methods=['POST'])
def valuta():
    dati = request.get_json()
    risposte = dati.get("risposte", {})
    if not risposte:
        return jsonify({"error": "Nessuna risposta fornita"}), 400
    try:
        risultati = valuta_assessment(risposte)
        medie = {
            "hard": round(sum(risultati[a]["valore"] for a in ["H1","H2","H3","H4"]) / 4, 1),
            "soft": round(sum(risultati[a]["valore"] for a in ["S1","S2","S3","S4"]) / 4, 1)
        }
        commenti = genera_commenti(risultati)
        sessione_id = dati.get("sessione_id", "no-id")
        durata_sec = dati.get("durata_sec", 0)
        utente = dati.get("utente", "")
        salva_sessione(sessione_id, risposte, risultati, medie, commenti, durata_sec, utente)
        return jsonify({
            "success": True,
            "risultati": risultati,
            "medie": medie,
            "commenti": commenti
        }), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port)
