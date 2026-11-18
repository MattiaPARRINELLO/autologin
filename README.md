<div align="center">
  <img src="icons/icon128.png" alt="CheckMate logo" width="96" />
  <h1>♟️ CheckMate</h1>
  <p><strong>Extension Chrome qui automatise le pointage de présence sur CESAR Emineo.</strong></p>

![Version](https://img.shields.io/badge/version-2.0.0-blue)
![Chrome](https://img.shields.io/badge/Chrome-compatible-brightgreen?logo=googlechrome)
![Licence](https://img.shields.io/badge/licence-MIT-green)
</div>

---

## 📋 Sommaire
- [Présentation](#présentation)
- [Fonctionnalités](#fonctionnalités)
- [Installation](#installation)
- [Configuration](#configuration)
- [Confidentialité](#confidentialité)
- [Technologies](#technologies)
- [Auteur](#auteur)

---

## 🎯 Présentation
CheckMate est une extension Chrome conçue pour les apprenants et formateurs utilisant la plateforme CESAR Emineo. Elle automatise entièrement le processus de pointage : ouverture de la session, connexion, recherche du bouton de signature, reproduction fidèle de votre signature manuscrite et validation. Une fois configurée, un seul clic suffit pour pointer sa présence.

---

## ✨ Fonctionnalités
- ✅ Connexion automatique (détecte si déjà connecté)
- ✅ Signature manuscrite reproduite à lidentique
- ✅ Journal dexécution horodaté
- ✅ Vérification automatique des mises à jour
- ✅ Stockage local sécurisé (aucune donnée externe)

---

## 🔔 Veille automatique (optionnel)
Un script Python autonome dans [`watcher/`](watcher/) surveille CESAR en continu, rafraîchit la page et propose de signer dès que l'émargement s'ouvre, sans garder d'onglet ouvert. Voir [`watcher/README.md`](watcher/README.md).

Un émulateur local indépendant dans [`emulator/`](emulator/) reproduit CESAR (connexion, bouton, canvas, confirmation) pour tester le watcher de bout en bout sans attendre un cours. Voir [`emulator/README.md`](emulator/README.md).

---

## 🚀 Installation
Téléchargez le ZIP depuis la [page des releases](https://github.com/MattiaPARRINELLO/CheckMate/releases/latest), décompressez-le, puis chargez-le dans chrome://extensions/ en mode développeur.

---

## 🛠️ Technologies
| Technologie | Rôle |
|-------------|------|
| JavaScript | Logique de lextension |
| Chrome API | Manifest V3 |
| HTML/CSS | Interface popup |

---

<div align="center">
  <sub>Fait avec ♟️ par <a href="https://github.com/MattiaPARRINELLO">MattiaPARRINELLO</a></sub>
</div>
