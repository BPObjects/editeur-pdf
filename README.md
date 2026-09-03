# Éditeur PDF BPO

Remplaçant local d'Acrobat Pro pour les besoins courants : compresser, modifier
le texte, signer, supprimer / tourner / réordonner des pages, fusionner.

Tout tourne sur la machine (serveur Python local + interface dans le navigateur).
Aucun fichier ne quitte l'ordinateur.

## Lancer

Double-cliquer sur `Editeur PDF.bat`. Le premier lancement crée `.venv` et
installe PyMuPDF (~30 s). Le navigateur s'ouvre sur http://localhost:8790/.

En ligne de commande : `python serveur.py [--port 8790] [--sans-navigateur]`.

## Ce que ça fait

| Fonction | Comment |
|---|---|
| Compresser | Bouton **Compresser** : 4 niveaux. Les images sont rééchantillonnées (150 / 110 / 72 dpi) et réencodées en JPEG, les masques de transparence sont conservés, les polices réduites au sous-ensemble utilisé. Texte et vecteurs intacts. |
| Modifier le texte | Mode **Texte** : survoler une ligne, cliquer, retaper, Entrée. La ligne d'origine est effacée (redaction sans fond) et réécrite avec la police d'origine si elle est embarquée avec les glyphes nécessaires, sinon Helvetica / Times / Courier (gras, italique respectés). Vider la ligne la supprime. |
| Ajouter du texte | Mode **Ajouter texte** : cliquer, taper, Entrée. Taille, couleur, police dans le panneau. |
| Signer | Mode **Signer** : dessiner (souris, stylet, doigt), importer une image (fond blanc rendu transparent), ou taper son nom en écriture cursive. Poser, déplacer, redimensionner, valider. Les signatures sont mémorisées dans le navigateur. |
| Pages | Colonne de gauche : clic / Ctrl / Maj pour sélectionner, **Supprimer**, tourner, **Extraire** (nouveau PDF), glisser pour réordonner. |
| Fusionner | Bouton **Fusionner** ou déposer des fichiers sur la fenêtre. PDF et images (PNG, JPG…). Inséré après la page sélectionnée s'il y en a une, sinon à la fin. |
| Annuler | Ctrl+Z, 30 niveaux, toutes opérations comprises (compression incluse). |
| Imprimer | Bouton **Imprimer** ou Ctrl+P : le PDF modifié (pas la page web) part dans la boîte d'impression du navigateur. |
| Enregistrer | Télécharge `<nom>-modifie.pdf`. Le fichier d'origine n'est jamais modifié. |

Raccourcis : V / T / A / S changent de mode, Suppr efface les pages
sélectionnées, +/− zoom (Ctrl+molette aussi), flèches pour changer de page,
Ctrl+S enregistre, Ctrl+P imprime, Ctrl+O ouvre.

## Limites connues

- La signature est une **image apposée**, pas une signature électronique
  certifiée (certificat X.509). Pour du eIDAS qualifié il faut un prestataire.
- La modification de texte travaille **ligne par ligne** : une ligne aux styles
  mixtes (un mot en gras) prend le style de son premier mot. Le texte n'est pas
  reflué (pas de renvoi à la ligne automatique) : une ligne rallongée déborde.
- Pas de formulaires interactifs (champs AcroForm), pas d'OCR des scans, pas de
  mot de passe (les PDF chiffrés sont refusés à l'ouverture).
- Fichiers testés jusqu'à 190 pages / 52 Mo : compression forte en ~20 s.

## Fichiers

- `serveur.py` — API HTTP + toute la logique PDF (classe `Document`).
  Le texte ajouté ou réécrit avec une police standard passe par les polices
  URW embarquées dans MuPDF (Nimbus Sans / Roman / Mono, équivalents métriques
  d'Helvetica, Times, Courier) enregistrées en police CID : tout l'Unicode
  couvert (—, €, œ, →…) s'écrit, et l'export ne garde que les glyphes utilisés.
- `index.html` — interface, un seul fichier, sans dépendance.
- `requirements.txt` — PyMuPDF.
- `LICENSE`, `THIRD-PARTY.md` — licence et composants tiers.

## Licence

Logiciel libre sous **GNU Affero General Public License v3 ou ultérieure**
(décision du 03/09/2026). Il peut être utilisé, modifié, redistribué et vendu,
à condition que le code source correspondant reste disponible sous la même
licence pour toute personne qui l'utilise, y compris à travers un réseau.
L'application remplit cette obligation elle-même : le lien **Source** de
l'interface (route `/source.zip`) livre l'intégralité du code, et la licence
est servie sur `/LICENSE`.

Le moteur PDF (PyMuPDF / MuPDF, Artifex) est lui-même sous AGPL v3, ce qui a
dicté ce choix ; voir `THIRD-PARTY.md`.
