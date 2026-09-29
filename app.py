"""
Server web per il motore di assessment manageriale.
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
MODELLO = "openai/gpt-oss-120b"

FRAMEWORK = {
    "H1": {
        "nome": "Efficientamento",
        "fasce": {
            "E": "Rileva problemi o rallentamenti e li porta all'attenzione del team. Produce una rappresentazione visiva del processo (diagramma di flusso, mappa) e identifica le fasi che rallentano.",
            "D": "Raccoglie dati elementari su tempi, volumi, carichi o qualità di alcune fasi. Distingue tempi di lavorazione da tempi di attesa. Confronta capacità disponibile e domanda. Riconosce le criticità operative principali e propone interventi plausibili.",
            "C": "Legge il processo per fasi e identifica le cause di inefficienza. Distingue problemi di capacità, flusso, organizzazione e competenza. Quantifica il fabbisogno di risorse (FTE) per fase. Confronta alternative e sceglie le leve con criteri espliciti coerenti con le cause. Usa i dati per orientare la scelta.",
            "B": "Definisce un intervento coerente con cause e contesto, considerando priorità e vincoli. Rialloca le risorse in funzione dei carichi e dei fabbisogni. Prevede modalità di verifica del risultato e sperimenta in modo controllato prima di estendere. Coinvolge chi opera nel processo, definisce ruoli, responsabilità e tempi, presidia l'esecuzione, affronta ostacoli, verifica l'efficacia e corregge sulla base dei risultati. Si assume la responsabilità del risultato.",
            "A": "Legge il processo end-to-end in coerenza con altri processi aziendali, utilizzando mappatura del flusso del valore, analisi valore/non valore, segmentazione per famiglie, analisi del flusso informativo. Considera interdipendenze tra fasi e funzioni e impatto sul cliente o utente finale. Integra il dimensionamento organico con la pianificazione delle risorse e con il modello di servizio. Confronta alternative con criteri espliciti, sperimenta in modo controllato, verifica gli effetti, corregge quando necessario. Rende stabile il miglioramento con standard operativi, indicatori e alert, ownership chiara, revisione periodica, integrazione nel ciclo di miglioramento continuo."
        }
    },
    "H2": {
        "nome": "Capire i fenomeni",
        "fasce": {
            "E": "Definisce il fenomeno da comprendere e legge i dati disponibili. Distingue sintomi ed effetti. Riconosce la presenza di variabilità e di possibili spiegazioni alternative.",
            "D": "Analizza il fenomeno utilizzando dati o informazioni pertinenti. Definisce metriche elementari. Distingue variabilità fisiologica da variazioni anomale. Confronta con baseline o riferimenti precedenti. Individua spiegazioni plausibili.",
            "C": "Analizza dati rilevanti e individua le principali cause del fenomeno. Formula più ipotesi plausibili quando il fenomeno è ambiguo e le prioritizza con criteri espliciti. Definisce cosa osservare per verificare.",
            "B": "Raccoglie e analizza dati pertinenti, distingue le principali cause dai sintomi. Verifica effettivamente le ipotesi e utilizza i risultati per confermare o modificare l'interpretazione. Aggiorna le conclusioni sulla base dei dati.",
            "A": "Definisce con precisione il fenomeno, integra dati quantitativi e qualitativi, distingue sintomi e cause, considera il contesto e le possibili interrelazioni. Formula e prioritizza ipotesi alternative, verifica sul campo con criteri espliciti. Mantiene aggiornata e verificata la comprensione nel tempo, monitorando la persistenza delle cause e l'evoluzione dei dati."
        }
    },
    "H3": {
        "nome": "Guidare il nuovo e il cambiamento",
        "fasce": {
            "E": "Identifica l'opportunità di innovare o cambiare. Comunica il cambiamento alle persone interessate. Riconosce la necessità di un percorso e ne parla con gli stakeholder principali.",
            "D": "Riconosce la necessità di innovare o cambiare e prende contatto con le parti rilevanti. Identifica opportunità e alcuni vincoli. Avvia azioni plausibili. Definisce un primo percorso di cambiamento.",
            "C": "Identifica l'opportunità, coinvolge le persone interessate, sperimenta o modifica il percorso e affronta le principali resistenze. Mappa stakeholder e interessi. Definisce un percorso di cambiamento coerente con il contesto.",
            "B": "Analizza opportunità, stakeholder e vincoli. Definisce un percorso iterativo, gestisce le resistenze con metodo e adatta comunicazione e azioni sulla base degli apprendimenti. Stima potenziale, rischio e gap. Definisce criteri di verifica della sperimentazione. Raccoglie feedback strutturati e decide se continuare, correggere o interrompere in base alle evidenze.",
            "A": "Legge opportunità e contesto in modo sistemico, esplicita assunzioni e rischi, coinvolge gli stakeholder, sperimenta con criteri chiari, usa feedback e dati per iterare, gestisce le resistenze e porta il cambiamento a regime con trasferimento di competenze. Definisce condizioni e criteri per scalare, integra la soluzione nei processi ordinari, aggiorna ruoli e responsabilità, monitora risultati e regressioni dopo l'introduzione."
        }
    },
    "H4": {
        "nome": "Gestione economica e finanziaria",
        "fasce": {
            "E": "Considera i costi nelle decisioni. Distingue costi fissi e variabili, diretti e indiretti. Collega i costi alle attività che li generano.",
            "D": "Misura costi elementari per prodotto, servizio o fase. Quantifica FTE e costo orario. Individua le voci che incidono maggiormente sul risultato. Propone interventi plausibili sui costi.",
            "C": "Legge il conto economico o il costo del servizio. Identifica le principali voci e propone interventi. Misura costo per prodotto/servizio e per fase. Confronta consuntivo, budget e forecast.",
            "B": "Analizza costi e driver, costruisce stime coerenti, considera alternative e rischi economici, collega budget e obiettivi. Valuta investimenti considerando ritorni, rischi e tempi. Definisce work package con costi associati. Presidia costi effettivi e avanzamento. Verifica che il saving o l'effetto economico atteso si realizzi.",
            "A": "Comprende i driver economici del servizio o della funzione, misura costi e scostamenti con criteri coerenti, confronta alternative e investimenti, collega decisioni operative a impatti economici, presidia l'esecuzione e aggiorna costantemente il quadro economico. Integra indicatori finanziari e operativi. Aggiorna cost driver quando cambia il modello operativo. Rende stabile la responsabilità sul controllo economico. Usa gli scostamenti per migliorare decisioni e pianificazione futura."
        }
    },
    "S1": {
        "nome": "Guidare e decidere",
        "fasce": {
            "E": "Dà obiettivi e istruzioni al team. Chiarisce direzione e priorità di base. Prende decisioni sulle attività operative. Assegna compiti.",
            "D": "Dà obiettivi e direzione e mantiene il coordinamento. Chiarisce alcuni ruoli e aspettative. Prende decisioni plausibili sulle attività e sulla gestione del team. Delega alcune attività con indicazioni.",
            "C": "Definisce obiettivi chiari e coinvolge il team nella loro realizzazione. Definisce criteri espliciti per le decisioni e valuta alcune alternative. Distribuisce alcune responsabilità.",
            "B": "Definisce direzione e priorità, chiarisce ruoli e responsabilità. Decide con criteri e alternative, comunicando motivazioni e assumendosi la responsabilità della scelta. Delega con checkpoint e verifica, fornendo risorse senza microgestire.",
            "A": "Crea una direzione chiara e coinvolgente, collegando direzione, priorità e significato. Coinvolge il team senza rinunciare alla responsabilità della decisione. Confronta alternative con criteri espliciti, gestendo trade-off e rischi. Delega con autonomia proporzionata, utilizzando verifica e apprendimento per aumentare progressivamente la responsabilità degli altri."
        }
    },
    "S2": {
        "nome": "Comunicare e influenzare",
        "fasce": {
            "E": "Informa gli interlocutori con messaggi chiari. Comunica le informazioni rilevanti. Mantiene un tono professionale.",
            "D": "Comunica in modo comprensibile e contestualizzato. Adatta il messaggio ai pubblici in modo elementare. Gestisce le obiezioni in modo reattivo.",
            "C": "Adatta il messaggio ai pubblici e gestisce in modo efficace le principali reazioni. Struttura il messaggio in modo chiaro. Anticipa alcune obiezioni. Costruisce relazioni professionali funzionali.",
            "B": "Adatta il messaggio ai diversi pubblici, considera obiezioni e reazioni, comunica con struttura e utilizza la rete relazionale in modo intenzionale. Anticipa obiezioni e prepara risposte. Costruisce relazioni prima del bisogno, attivandole quando serve.",
            "A": "Mappa interlocutori e interessi, adatta contenuto e linguaggio, anticipa obiezioni, gestisce il dissenso, comunica con chiarezza anche sotto pressione. Costruisce relazioni prima del bisogno, attivandole in modo appropriato. Mantiene una logica di scambio e non di sola richiesta."
        }
    },
    "S3": {
        "nome": "Sostenere e cooperare",
        "fasce": {
            "E": "Entra in contatto con le parti interessate. Ascolta le loro posizioni. Riconosce la presenza di resistenze o conflitti.",
            "D": "Entra in contatto con le parti interessate, ascolta e cerca di trovare una soluzione. Dà feedback con alcuni elementi di struttura (fatti, impatto). Usa leve motivazionali diversificate.",
            "C": "Affronta resistenze e relazioni difficili attraverso confronto e ricerca di soluzioni. Dà feedback strutturati. Ascolta attivamente. Usa leve motivazionali coerenti con le persone.",
            "B": "Gestisce resistenze con metodo, esplorando interessi e cercando soluzioni integrative. Dà feedback strutturati, basati su fatti e orientati allo sviluppo. Ascolta attivamente e motiva in modo coerente con le persone e il contesto.",
            "A": "Esplora interessi e bisogni, gestisce resistenze con ascolto e soluzioni integrative, dà feedback basati su fatti e orientati allo sviluppo, motiva con leve coerenti e costruisce accordi verificabili."
        }
    },
    "S4": {
        "nome": "Efficacia personale",
        "fasce": {
            "E": "Riconosce di essere sotto pressione. Mantiene la calma di fronte alle difficoltà. Prosegue il lavoro nelle situazioni complesse.",
            "D": "Riconosce la pressione e ne tiene conto. Mantiene il focus sulle attività in corso. Usa alcune strategie per gestire lo stress.",
            "C": "Riconosce la pressione, accetta il rischio, mantiene il focus sulle priorità e mostra una buona capacità di adattamento. Usa strategie concrete per gestire lo stress.",
            "B": "Usa strategie concrete per gestire stress e priorità, modifica il piano quando necessario e mantiene un comportamento stabile. Riconosce i propri trigger e regola le reazioni.",
            "A": "Riconosce i propri stati emotivi e trigger, mantiene lucidità sotto pressione, protegge l'energia, adatta piani e comportamento alle condizioni e mantiene la direzione anche in situazioni ambigue."
        }
    }
}

DOMANDE_AREA = {
    "Q1": "H1", "Q2": "H2", "Q3": "H3", "Q4": "H4",
    "Q5": "S1", "Q6": "S2", "Q7": "S3", "Q8": "S4"
}

def chiama_llm(prompt):
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    }
    body = {
        "model": MODELLO,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_tokens": 2000
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

def valuta_area_con_llm(area_id, evidenze):
    area = FRAMEWORK[area_id]
    fasce_testo = "\n".join([f"- Fascia {k}: {v}" for k, v in area["fasce"].items()])
    evidenze_testo = "\n".join([f"- {e}" for e in evidenze])
    prompt = f"""Sei un valutatore esperto. Devi valutare l'area "{area['nome']}" sulla base delle risposte di un manager.

Le fasce di maturità sono:
{fasce_testo}

Le risposte del manager sono:
{evidenze_testo}

ISTRUZIONI DI VALUTAZIONE:
1. Scegli la fascia più alta raggiunta dall'insieme delle evidenze. La scala è cumulativa: A include B, B include C, C include D, D include E.
2. Se la risposta cita ALMENO 2 comportamenti specifici di una fascia, assegna quella fascia. Non richiedere che tutti i comportamenti siano presenti.
3. Se la risposta cita anche solo un comportamento di una fascia superiore, sali di fascia.
4. Non essere prudente: se la risposta mostra competenza, riconoscila.

Rispondi immediatamente con UNA SOLA LETTERA tra E, D, C, B, A. Non scrivere altro. Non spiegare. Non ragionare. Solo la lettera."""

    risposta = chiama_llm(prompt)
    for lettera in risposta:
        if lettera in "EDCBA":
            return lettera
    return "E"

def fascia_a_valore(fascia):
    range_fasce = {
        "A": 4.7, "B": 4.2, "C": 3.7,
        "D": 3.2, "E": 2.5, "F": 1.5
    }
    return range_fasce.get(fascia, 2.5)

def valuta_assessment(risposte):
    evidenze_per_area = {area_id: [] for area_id in FRAMEWORK}
    for domanda, risposta in risposte.items():
        area_id = DOMANDE_AREA.get(domanda)
        if area_id:
            evidenze_per_area[area_id].append(risposta)

    risultati = {}
    for area_id in FRAMEWORK:
        evidenze = evidenze_per_area[area_id]
        if not evidenze:
            risultati[area_id] = {"fascia": "F", "valore": 1.5}
        else:
            fascia = valuta_area_con_llm(area_id, evidenze)
            valore = fascia_a_valore(fascia)
            risultati[area_id] = {"fascia": fascia, "valore": valore}
        time.sleep(3)
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
        return jsonify({"success": True, "risultati": risultati}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port)
