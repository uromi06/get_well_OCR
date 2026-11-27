# Baseline comparison: case01 (fictional)

Same OCR text (mistral) for both. Baseline = Mistral Large 3, temperature 0, one call with all pages.

| | OCR-Text → LLM (Mistral Large 3) | Get Well OCR |
|---|---|---|
| **Kritische Fakten gefunden** | **13/13** | **13/13** |
| **Fallen vermieden** | **9/11** | **11/11** |
| Apixaban als aktuelles Antikoagulans gelistet | ✅ | ✅ |
| Phenprocoumon (alt) NICHT als aktuell gelistet | ✅ | ✅ |
| Glimepirid (laut Fax abgesetzt) NICHT als aktuell | ✅ | ✅ |
| Sitagliptin (2021) NICHT als aktuell | ✅ | ✅ |
| Torasemid mit aktueller Dosis 20 mg | ✅ | ✅ |
| Metformin mit aktueller Dosis 500 mg (nicht 1000) | ✅ | ✅ |
| Penicillin-Allergie genannt | ✅ | ✅ |
| 'Keine Allergien' NICHT ungeprüft übernommen | ✅ | ✅ |
| Allergie-Widerspruch benannt | ❌ | ✅ |
| Krankenkassenbrief ignoriert | ✅ | ✅ |
| Unscharfe Seite 20 erkannt | ❌ | ✅ |
| Quellseite pro Angabe | 0% der Zeilen | 79% der Zeilen |
| Zahlen, die in keinem Dokument stehen | 0 | 0 |

Nicht gefunden (Baseline): –

Nicht gefunden (Get Well OCR): –
