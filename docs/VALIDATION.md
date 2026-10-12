# Verifica iniziale — 12 ottobre 2026

Ambiente locale: Linux, Python 3.12.14, CadQuery 2.7.0, VTK 9.3.1,
PySide6 6.8.3. Esecuzione GUI con piattaforma Qt offscreen.

**14 test automatici superati** sul motore geometrico reale e sull'interfaccia.
Controllata visivamente la finestra renderizzata. Il test STEP include eliminazione
del file importato originale e riapertura del progetto per verificare l'indipendenza.

Non verificati in questa sessione:

- esecuzione interattiva sul PC Windows dell'utente;
- pacchetto EXE prodotto da PyInstaller;
- affidabilità per uso produttivo, assiemi e modelli grandi;
- selezione grafica prolungata e comportamento di tutti i dialoghi su Windows.

Il workflow CAD tests ripete i test su Linux e Windows. Il workflow del binario
è separato e manuale. Il loro risultato va letto in GitHub Actions; non è implicito
nell'esistenza dei file workflow.
