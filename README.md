# Billetterie - Application de Réservation de Billets

## Description

Cette application est un système de réservation de billets pour les Jeux Olympiques de Paris 2024. Les utilisateurs peuvent s'inscrire, se connecter, acheter des billets et les télécharger sous forme de QR codes. L'application utilise Flask comme framework web, MySQL pour la base de données et Mailgun pour l'envoi d'emails de validation.

## Fonctionnalités

- **Inscription et connexion des utilisateurs**
- **Validation par email** avec un lien de confirmation
- **Visualisation et achat de billets**
- **Panier d'achat** pour gérer les billets sélectionnés
- **Génération de QR codes** pour les achats réussis
- **Historique des achats**

## Prérequis

Avant de commencer, assurez-vous d'avoir les éléments suivants installés sur votre machine :

- Python 3.x
- Pip (gestionnaire de paquets Python)
- MySQL

## Installation

1. **Clonez le dépôt :**

   ```bash
   git clone https://github.com/votre-utilisateur/billetterie.git
   cd billetterie
