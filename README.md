# mac-headless

# MacBook Headless — Home Server

Configuration d'un **MacBook Pro utilisé comme serveur domestique headless**, accessible à distance via SSH et WireGuard, avec exposition des applications uniquement à travers le VPN.

## 🧹 Nettoyage et préparation du Mac

* Nettoyage des applications, daemons et agents inutiles.
* Suppression/désactivation des services non nécessaires au fonctionnement du serveur.
* Référence utile : [Awesome Mac Mini Home Server](https://github.com/momenbasel/awesome-mac-mini-homeserver)
* Configuration du Mac en mode **toujours allumé / sans mise en veille**.

## 🔐 SSH

### Keychain

Après un redémarrage, le déverrouillage du Keychain peut empêcher certains services SSH de fonctionner correctement.

Mise en place d'un script exécuté dans `.bashrc` afin de déverrouiller l'agent SSH au démarrage.

> ⚠️ Le mot de passe étant stocké en dur dans le script, cette méthode est à revoir pour une configuration de production.

### Hardening SSH

Durcissement de la configuration SSH :

* `PermitRootLogin no`
* `PasswordAuthentication no`
* `AllowUsers meuh_yogo`

### Accès depuis le PC Yoga

Création d'un alias SSH dans `~/.ssh/config` :

```ssh
Host mac
    HostName <adresse>
    User <utilisateur>
    Port <port>
```

Connexion :

```bash
ssh mac
```

### Accès graphique

Installation de **Remmina** sur le PC Yoga afin de pouvoir accéder graphiquement au Mac à distance.

---

## 🌐 Réseau et accès distant

### WireGuard

Installation et configuration de WireGuard sur le Mac.

Réseau VPN :

```text
10.13.13.0/24
```

| Machine     | Adresse         | Allowed IPs                      |
| ----------- | --------------- | -------------------------------- |
| Mac serveur | `10.13.13.1/24` | `10.13.13.2/32`, `10.13.13.3/32` |
| Téléphone   | `10.13.13.2/24` | `10.13.13.1/32`                  |
| PC Yoga     | `10.13.13.3/24` | `10.13.13.1/32`                  |

Les clés publiques WireGuard sont échangées entre les différents peers.

Le téléphone et le PC Yoga utilisent le **DDNS comme endpoint** du serveur.

### DDNS

Création d'un hostname DDNS avec **No-IP**, associé au service DDNS de la Livebox Orange.

Objectif : disposer d'un nom stable malgré le changement éventuel d'adresse IP publique.

### Redirection de port Orange

Sur la Livebox :

```text
UDP 51820
        ↓
192.168.1.13:51820
```

Seul le port WireGuard est exposé depuis Internet.

---

# 🐳 Docker

Installation de Docker Desktop.

Création du réseau Docker partagé utilisé par le reverse proxy :

```bash
docker network create proxy
```

Ce réseau permet à Traefik de communiquer avec les différentes applications.

---

# 🔀 Traefik

Installation de Traefik via Docker Compose.

Traefik est connecté au réseau :

```text
proxy
```

Il joue le rôle de **reverse proxy HTTP** et distribue les requêtes vers les applications Docker.

---

# 🧭 Pi-hole

Vérification préalable qu'aucun service local n'utilise déjà le port DNS `53`.

Installation de Pi-hole avec :

```text
8081:80
53:53/tcp
53:53/udp
```

Le port `8081` permet l'accès direct au dashboard Pi-hole :

```text
http://10.13.13.1:8081
```

### DNS local

Création des entrées DNS locales :

```text
traefik.home   → 10.13.13.1
immich.home    → 10.13.13.1
paperless.home → 10.13.13.1
pihole.home    → 10.13.13.1
```

### Principe

**Pi-hole = annuaire téléphonique**

Il traduit :

```text
immich.home → 10.13.13.1
```

**Traefik = standardiste**

Il reçoit ensuite la requête HTTP et la redirige vers le bon conteneur.

---

# 📦 Applications

Applications actuellement déployées :

* **Immich** — `immich.home`
* **Paperless-ngx** — `paperless.home`
* **Pi-hole** — `pihole.home`
* **Traefik** — `traefik.home`

Les applications HTTP ne sont pas directement exposées sur Internet. Elles sont accessibles via le réseau WireGuard.

---

# 🗺️ Architecture

```text
                         INTERNET
                            │
                            │ UDP 51820
                            ▼
                     ┌──────────────┐
                     │    Livebox   │
                     │    Orange    │
                     └──────┬───────┘
                            │
                            ▼
                  ┌────────────────────┐
                  │ MacBook Headless    │
                  │ 192.168.1.13       │
                  │                    │
                  │ WireGuard           │
                  │ 10.13.13.1         │
                  └─────────┬──────────┘
                            │
                  ┌─────────┴──────────┐
                  │                    │
                  ▼                    ▼
              Pi-hole               Traefik
                 │                    │
                 │ DNS                │ HTTP
                 │                    │
                 ▼                    ├── traefik.home
          10.13.13.1                 ├── immich.home
                                     └── paperless.home
                                          │
                                          ▼
                                    Docker / proxy
```

### Flux DNS

```text
Téléphone / PC Yoga
        │
        │ DNS
        ▼
   Pi-hole
        │
        │ immich.home
        ▼
   10.13.13.1
```

### Flux HTTP

```text
Téléphone / PC Yoga
        │
        │ HTTP
        ▼
   Traefik
        │
        ├── traefik.home  → Dashboard
        ├── immich.home   → Immich
        └── paperless.home → Paperless
```

## 🎯 Principe de sécurité

```text
Internet
   │
   └── UDP 51820 uniquement
             │
             ▼
         WireGuard
             │
             ▼
        Réseau privé
             │
        ┌────┴────┐
        ▼         ▼
     Pi-hole   Traefik
                 │
          ┌──────┴──────┐
          ▼             ▼
       Immich       Paperless
```

Les applications ne sont donc **pas publiées directement sur Internet**. L'accès aux services passe par le VPN WireGuard.
