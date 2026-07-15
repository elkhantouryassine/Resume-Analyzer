# Architeo Recruit

Application Python native avec interface HTML/CSS/JavaScript pour analyser un CV, générer un rapport et interroger plusieurs CV avec un chatbot RAG local.

## Installation

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

Si `python` n'est pas reconnu sous Windows, essayez :

```powershell
py -3 -m venv .venv
```

## Exécution

```powershell
cd C:\Users\Lenovo\Desktop\resume_analyser
.\.venv\Scripts\python.exe app.py
```

Puis ouvrir `http://127.0.0.1:8502/`.

- Page d'accueil : `http://127.0.0.1:8502/`
- Application principale : `http://127.0.0.1:8502/app.html`

Les fichiers uploadés, rapports générés et index vectoriels sont créés localement au lancement et ne sont pas versionnés.

## RAG et embeddings

Le chatbot RAG utilise `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` quand `sentence-transformers` est installé. Si le modèle n'est pas disponible, l'application bascule automatiquement sur un fallback local par hashing pour rester utilisable.

L'assistant RH peut aussi générer une shortlist, comparer les meilleurs candidats, résumer les profils et vérifier les compétences manquantes dans les CV indexés.
