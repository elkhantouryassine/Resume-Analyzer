# Architeo Recruit

Application Python native avec interface HTML/CSS/JavaScript pour analyser un CV, générer un rapport et interroger plusieurs CV avec un chatbot RAG local.

## Installation

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

Pour une installation locale avec les moteurs IA lourds optionnels :

```powershell
pip install -r requirements-ai.txt
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

Le chatbot RAG utilise `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` quand `sentence-transformers` est installé via `requirements-ai.txt`. En deploiement, `requirements.txt` reste volontairement leger pour eviter de depasser la limite de taille des fonctions serverless. Si le modele n'est pas disponible, l'application bascule automatiquement sur un fallback local par hashing pour rester utilisable.

## Deploiement

Le fichier `.vercelignore` exclut l'environnement virtuel, les caches et les donnees locales afin de garder le bundle sous la limite de taille. Sur Vercel, les fichiers generes sont stockes temporairement dans `/tmp/architeo_recruit`. Pour forcer un autre dossier runtime, definir `ARCHITEO_DATA_DIR`.

L'assistant RH peut aussi générer une shortlist, comparer les meilleurs candidats, résumer les profils et vérifier les compétences manquantes dans les CV indexés.
