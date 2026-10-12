# Architettura

Applicazione autonoma Python/PySide6. Nessuna dipendenza da FreeCAD o Fusion.

- `model.py`: grafo ordinato delle operazioni e motore CadQuery/Open CASCADE.
- `app.py`: finestra desktop, browser, cronologia, azioni e gestione progetti.
- `viewport.py`: visualizzatore CPU Qt della triangolazione dei BRep.
- `dialogs.py`: editor numerico dei parametri.
- `settings.py`: preferenze persistenti locali e stima materiale.

Ogni nodo ha ID stabile, tipo, nome, parametri, riferimenti agli input e visibilità.
Una modifica ricostruisce il grafo in un nuovo dizionario di forme; solo se tutte
le operazioni riescono sostituisce lo stato corrente. Un fallimento conserva il
progetto precedente. Annulla/ripeti conserva fino a 50 stati delle operazioni.
La topologia dei sottoelementi non ha ancora identificazione stabile: non promettere
che lo spigolo numero 3 resti lo stesso dopo modifiche a monte.

Il progetto `.foscad` è JSON, versione 1, unità mm. Non contiene script eseguibili.
I STEP importati diventano BRep incorporati in Base64: il progetto non dipende da
percorsi esterni dopo l'import. Il caricamento ricostruisce e valida il grafo.
Il salvataggio usa un file temporaneo adiacente e sostituzione atomica.

In questa versione la precisione geometrica viene dal kernel. L'impostazione di
qualità cambia solo la triangolazione di visualizzazione. Il visualizzatore CPU
è transitorio: una futura versione dovrà adottare un viewport GPU con depth buffer,
selezione di facce/spigoli e identificazione dei sottoelementi.

Il backup è una copia .foscad locale. Non sincronizza dati e non esegue rete.
Le impostazioni sono gestite da QSettings; i backup usano AppLocalDataLocation.
Nessuna chiave API o account è necessario per usare il programma.

La pipeline Windows crea una distribuzione PyInstaller onedir sperimentale.
I test offscreen non sostituiscono una prova del pacchetto in Windows pulito.
