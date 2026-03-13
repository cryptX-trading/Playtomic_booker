# Playtomic Padel Watcher

Surveille automatiquement les disponibilités de terrains de padel sur Playtomic et t'envoie une notification Telegram dès qu'un créneau apparaît.

Tourne sur **GitHub Actions** (gratuit, fonctionne même Mac éteint) toutes les 5 minutes.

---

## Structure du projet

```
playtomic-watcher/
├── .github/workflows/check_availability.yml  # Scheduler GitHub Actions
├── playtomic_client.py                        # Client API Playtomic
├── booking_manager.py                         # Logique principale
├── config.yaml                                # Tes clubs et créneaux
└── requirements.txt
```

---

## Setup (20 minutes, une seule fois)

### 1. Créer un bot Telegram

1. Ouvre Telegram et cherche **@BotFather**
2. Envoie `/newbot`
3. Choisis un nom et un identifiant (ex: `mon_padel_bot`)
4. BotFather te donne un **token** — note-le précieusement
   Exemple : `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`

### 2. Obtenir ton Chat ID

1. Envoie n'importe quel message à ton bot (ex: "hello")
2. Ouvre cette URL dans ton navigateur en remplaçant `<TOKEN>` :
   `https://api.telegram.org/bot<TOKEN>/getUpdates`
3. Dans la réponse JSON, cherche `"chat": {"id": 123456789}` — c'est ton **Chat ID**

### 3. Trouver le `tenant_id` de ton club Playtomic

1. Va sur [playtomic.io](https://playtomic.io) et recherche ton club
2. Ouvre les **DevTools** du navigateur (F12 ou Cmd+Option+I sur Mac)
3. Va dans l'onglet **Réseau** (Network)
4. Recharge la page ou clique sur "Réserver"
5. Cherche une requête vers `api.playtomic.io/v1/availability`
6. Dans les paramètres de la requête, copie la valeur de `tenant_id`
   Exemple : `2ab75436-9bb0-4e9c-9a6f-b12931a9ca4a`

### 4. Configurer `config.yaml`

Ouvre [config.yaml](config.yaml) et remplis :
- `tenant_id` de tes clubs
- Les `desired_slots` avec tes jours et horaires préférés

### 5. Créer un repo GitHub

1. Crée un **repo public** sur GitHub (public = minutes illimitées)
2. Clone-le et copie les fichiers du projet dedans
3. Fais un `git push`

> **Repo privé** : les minutes sont limitées à 2000/mois sur le plan gratuit. Dans ce cas, change le cron en `*/10 * * * *` dans le workflow.

### 6. Ajouter les secrets GitHub

1. Dans ton repo GitHub, va dans **Settings → Secrets and variables → Actions**
2. Clique **New repository secret** et ajoute :
   - `TELEGRAM_BOT_TOKEN` → le token de ton bot
   - `TELEGRAM_CHAT_ID` → ton chat ID

### 7. Activer GitHub Actions

1. Va dans l'onglet **Actions** de ton repo
2. Si Actions n'est pas activé, clique sur le bouton pour l'activer
3. Clique sur le workflow **Check Playtomic Availability**
4. Clique **Run workflow** pour tester immédiatement

---

## Tester manuellement

```bash
# Installe les dépendances
pip install -r requirements.txt

# Exporte les variables d'environnement
export TELEGRAM_BOT_TOKEN="ton_token"
export TELEGRAM_CHAT_ID="ton_chat_id"

# Lance le script
python booking_manager.py
```

---

## Comment ça marche

1. GitHub Actions exécute `booking_manager.py` toutes les 5 minutes
2. Le script appelle l'API Playtomic pour chaque club configuré sur les `days_ahead` prochains jours
3. Il filtre les créneaux selon tes `desired_slots`
4. Pour les **nouveaux créneaux** (pas encore notifiés), il envoie un message Telegram
5. L'état est sauvegardé dans `state.json` (via le cache GitHub Actions) pour éviter les doublons

### Exemple de notification

```
🎾 Terrain disponible !
📍 Mon Club de Padel
📅 Jeudi 19 mars à 19:00 (90 min)
💶 24.0 EUR
🔗 https://app.playtomic.io
```

---

## Dépannage

| Problème | Solution |
|----------|----------|
| Pas de notification reçue | Vérifie les logs dans l'onglet Actions → vois si des créneaux ont été trouvés |
| Erreur `TELEGRAM_BOT_TOKEN` manquant | Vérifie que les secrets sont bien ajoutés dans Settings |
| Aucun créneau détecté | Vérifie le `tenant_id` et les `desired_slots` dans config.yaml |
| Le workflow ne se lance pas | Sur les repos inactifs, GitHub peut désactiver les scheduled workflows — déclenche-le manuellement une fois |
| Doublons de notifications | Vide le cache GitHub Actions (Settings → Caches) |
