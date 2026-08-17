import pandas as pd
import streamlit as st
import google.generativeai as genai
import fitz  # PyMuPDF
from PIL import Image
import io
import json

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(
    page_title="quoting.ai - Vision Engine",
    page_icon="📐",
    layout="wide"
)

# --- PROMPT DEFINITIONS ---
SYSTEM_PROMPT = """
Sei l'intelligenza visiva di quoting.ai, un ingegnere preventivista e disegnatore CAD senior, specializzato in meccanica di precisione e lavorazioni CNC.

Il tuo compito è analizzare IMMAGINI di tavole meccaniche, disegni costruttivi e capitolati complessi per estrarre i parametri di produzione.

REGOLE VISIVE E DI ESTRAZIONE FERREE:
1. ANCORAGGIO SPAZIALE (CARTIGLIO): Per i dati generali, focalizza subito la tua attenzione sull'angolo in BASSO A DESTRA del disegno (il cartiglio). È lì che si trovano Codice Disegno, Revisione e Cliente.
2. LETTURA A GRIGLIA: Nei cartigli, il nome del campo (es. "Materiale", "Mat.", "Trattamento") è spesso scritto in piccolo, mentre il valore (es. "C45", "S355JR", "AISI 304") è scritto più in grande nella stessa cella o in quella adiacente. Associa correttamente chiave e valore.
3. NORMATIVE E TOLLERANZE: Cerca attivamente diciture come "ISO 2768-mK", "UNI EN", o quote specifiche con tolleranze (es. "Ø 50 H7", "+0.05/-0.01").
4. RUGOSITÀ: Cerca i simboli del triangolo (Ra) o le diciture sulla finitura superficiale (es. "Ra 1.6", "Ra 3.2").
5. INTOLLERANZA ALLE ALLUCINAZIONI: I disegni tecnici non ammettono errori. Se un testo è sfocato, illeggibile o troncato, DEVI scrivere esplicitamente "Illeggibile". Non indovinare MAI un numero, una tolleranza o un materiale.
"""

USER_PROMPT = """
Analizza le immagini di questo disegno tecnico / capitolato in allegato.
Agisci come un esperto preventivista meccanico.

Estrai le informazioni visive e testuali e restituiscile ESATTAMENTE in questo formato JSON valido:

{
  "dati_generali": {
    "nome_cliente": "Nome cliente, committente o proprietario del disegno",
    "numero_disegno": "Codice identificativo esatto del disegno (spesso nel cartiglio, es. DWG-10293)",
    "revisione": "Indice di revisione (es. A, B, 01, 02)",
    "titolo_componente": "Nome del pezzo (es. Albero di trasmissione, Flangia)"
  },
  "specifiche_tecniche": {
    "materiali_richiesti": [
      {
        "tipo_materiale": "es. Acciaio C45, Alluminio 6082. Se vedi sigle come 'Mat: EN AW 7075', riporta l'intero valore.",
        "trattamenti_termici_o_superficiali": "es. Zincatura, Tempra, Anodizzazione (se indicati nel cartiglio o note)",
        "quantita": "Numero di pezzi se specificato (altrimenti null)"
      }
    ],
    "tolleranze_generali": "Normativa di tolleranza generale indicata nel cartiglio (es. ISO 2768-m)",
    "tolleranze_geometriche_specifiche": ["Elenca eventuali tolleranze critiche lette sulle quote, es. Ø20 H7, parallelismo 0.01"],
    "rugosita_generale": "Valore base di Ra letto nel cartiglio o sul simbolo generale (es. Ra 3.2)"
  },
  "compliance_e_rischi": {
    "note_di_produzione": ["Eventuali note testuali scritte nel foglio relative a sbavatura, smussi o indicazioni di montaggio"],
    "note_rischio_ai": "Segnala se alcune quote sono tagliate, se il cartiglio è sfocato, o se mancano informazioni critiche per la produzione."
  }
}
"""

# --- FUNZIONE PER CONVERTIRE PDF IN IMMAGINI ---
def converti_pdf_in_immagini(file_pdf, dpi=150):
    """Converte ogni pagina del PDF in un oggetto Immagine PIL."""
    immagini = []
    # Legge i byte del file caricato da Streamlit
    doc = fitz.open(stream=file_pdf.read(), filetype="pdf")
    
    for pagina in doc:
        # Trasforma la pagina in una matrice di pixel (bitmap)
        pix = pagina.get_pixmap(dpi=dpi)
        img_bytes = pix.tobytes("png")
        img = Image.open(io.BytesIO(img_bytes))
        immagini.append(img)
        
    return immagini

# --- CHIAMATA VISION A GEMINI ---
def analizza_documento_vision(immagini, api_key):
    genai.configure(api_key=api_key)
    
    modelli_candidati = [
        'gemini-3.6-flash',
        'gemini-1.5-flash',
        'gemini-1.5-pro'
    ]
    
    # Prepariamo l'input per Gemini: il prompt testuale seguito dalle immagini
    contenuti = [USER_PROMPT] + immagini
    
    ultimo_errore = None
    for nome_modello in modelli_candidati:
        try:
            model = genai.GenerativeModel(
                model_name=nome_modello,
                system_instruction=SYSTEM_PROMPT,
                generation_config={"response_mime_type": "application/json"}
            )
            
            # Gemini riceve sia il testo che le immagini contemporaneamente
            response = model.generate_content(contenuti)
            return json.loads(response.text)
        except Exception as e:
            ultimo_errore = e
            continue
            
    raise ultimo_errore
# --- FUNZIONE PER GENERARE EXCEL ---
def genera_excel(risultato_json):
    output = io.BytesIO()
    
    # Estrazione dati
    dati_gen = risultato_json.get("dati_generali", {})
    spec = risultato_json.get("specifiche_tecniche", {})
    comp = risultato_json.get("compliance_e_rischi", {})
    
    # Foglio 1: Overview
    overview_data = {
        "Parametro": [
            "Cliente / Committente", 
            "Numero RFQ / Disegno", 
            "Scadenza / Revisione",
            "Tolleranze e Rugosità", 
            "Lavorazioni Richieste", 
            "Certificazioni", 
            "Penali e Note Critiche", 
            "Rischi Rilevati dall'AI"
        ],
        "Valore": [
            dati_gen.get("nome_cliente", "N/A"),
            dati_gen.get("numero_rfq_o_disegno", "N/A"),
            dati_gen.get("scadenza_o_revisione", "N/A"),
            spec.get("tolleranze_e_rugosita", "N/A"),
            ", ".join(spec.get("lavorazioni_principali", [])),
            ", ".join(comp.get("certificazioni_richieste", [])),
            comp.get("penali_o_note_critiche", "Nessuna"),
            comp.get("note_rischio_ai", "Nessuno")
        ]
    }
    df_overview = pd.DataFrame(overview_data)
    
    # Foglio 2: Materiali
    materiali = spec.get("materiali_richiesti", [])
    if materiali:
        df_materiali = pd.DataFrame(materiali)
        # Rinominiamo le colonne per renderle più professionali
        df_materiali.rename(columns={
            "tipo_materiale": "Tipo Materiale",
            "quantita": "Quantità",
            "dettaglio_visivo": "Riferimento nel Documento"
        }, inplace=True)
    else:
        df_materiali = pd.DataFrame([{"Materiale": "Nessun materiale rilevato", "Quantità": "-", "Riferimento": "-"}])
        
    # Creazione del file Excel a più fogli
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_overview.to_excel(writer, sheet_name="Scheda Preventivazione", index=False)
        df_materiali.to_excel(writer, sheet_name="Distinta Materiali", index=False)
        
    return output.getvalue()

# --- INTERFACCIA STREAMLIT ---
st.title("📐 quoting.ai - Vision Engine")
st.subheader("Estrazione da Scansioni, PDF e Disegni Tecnici")

with st.sidebar:
    st.header("Impostazioni")
    api_key_input = st.text_input("Inserisci la Google API Key", type="password")
    st.markdown("---")
    st.info("👁️ **Modalità Vision Attiva:** Il sistema converte i documenti in immagini e li analizza visivamente.")

uploaded_file = st.file_uploader("Carica Capitolato o Disegno Tecnico (PDF)", type=["pdf"])

if uploaded_file is not None:
    if not api_key_input:
        st.warning("⚠️ Inserisci la tua API Key nella barra laterale.")
    else:
        if st.button("🚀 Analizza Visivamente il Documento"):
            with st.spinner("Conversione pagine in corso e analisi visiva Gemini..."):
                try:
                    # 1. Converti PDF in immagini PIL
                    immagini_pagine = converti_pdf_in_immagini(uploaded_file)
                    
                    st.write(f"📸 **Pagine/Disegni rilevati:** {len(immagini_pagine)}")
                    
                    # 2. Mostra un'anteprima visiva della prima pagina/disegno
                    with st.expander("Mostra Anteprima Visiva del Documento", expanded=False):
                        st.image(immagini_pagine[0], caption="Pagina 1 / Disegno principale", use_container_width=True)
                    
                    # 3. Analisi multimodale
                    risultato = analizza_documento_vision(immagini_pagine, api_key_input)
                    
                    st.success("Analisi visiva completata!")
                    st.markdown("---")
                    
                    # 4. Rendering Risultati
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.write("### 📋 Dati Generali & Cartiglio")
                        dati_gen = risultato.get("dati_generali", {})
                        st.metric(label="Cliente / Committente", value=dati_gen.get("nome_cliente", "N/A"))
                        st.metric(label="N. RFQ / Codice Disegno", value=dati_gen.get("numero_rfq_o_disegno", "N/A"))
                        st.metric(label="Scadenza / Revisione", value=dati_gen.get("scadenza_o_revisione", "N/A"))
                        
                        st.write("### ⚠️ Rischi & Note Visive")
                        comp = risultato.get("compliance_e_rischi", {})
                        st.error(f"**Anomalie / Note dell'AI:** {comp.get('note_rischio_ai', 'Nessuna')}")
                        st.warning(f"**Penali / Note critiche:** {comp.get('penali_o_note_critiche', 'N/A')}")
                        
                    with col2:
                        st.write("### 🛠️ Specifiche Tecniche ed Estratte")
                        spec = risultato.get("specifiche_tecniche", {})
                        
                        st.write("**Tolleranze e Rugosità:**", spec.get("tolleranze_e_rugosita", "N/A"))
                        
                        st.write("**Lavorazioni Rilevate:**")
                        for lav in spec.get("lavorazioni_principali", []):
                            st.write(f"- {lav}")
                            
                        st.write("**Materiali Rilevati:**")
                        materiali = spec.get("materiali_richiesti", [])
                        if materiali:
                            st.dataframe(materiali)
                        else:
                            st.write("Nessun materiale rilevato esplicitamente.")
                            st.markdown("---")
                    # Generazione Excel e Pulsante
                    excel_data = genera_excel(risultato)
                    
                    # Usa il numero disegno per il nome del file (o 'Bozza' se manca)
                    nome_file = f"Preventivo_{dati_gen.get('numero_rfq_o_disegno', 'Bozza')}.xlsx"
                    
                    st.download_button(
                        label="📥 Scarica Scheda in Excel",
                        data=excel_data,
                        file_name=nome_file,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        type="primary"
                    )
                            
                except Exception as e:
                    st.error(f"Errore durante l'elaborazione visiva: {e}")