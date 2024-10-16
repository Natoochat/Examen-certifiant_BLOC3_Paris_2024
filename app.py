from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file
from flask_bcrypt import Bcrypt
from io import BytesIO
import base64
import os
import mysql.connector
from mysql.connector import Error
import re
import validators
import requests
import uuid
import qrcode
import logging
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__, static_url_path='/static')
app.secret_key = os.environ.get('SECRET_KEY', 'votre_clé_secrète_par_défaut')  # Utilisation d'une variable d'environnement pour la clé secrète
app.logger.setLevel(logging.INFO)
bcrypt = Bcrypt(app)

# Fonction de connexion à la base de données
def get_db_connection():
    try:
        # Vérification des variables d'environnement
        required_env_vars = ['DB_USER', 'DB_PASSWORD', 'DB_HOST', 'DB_PORT', 'DB_DATABASE', 'DB_SSL_CA']
        for var in required_env_vars:
            if os.getenv(var) is None:
                app.logger.error(f"La variable d'environnement {var} n'est pas définie.")
                return None
        
        config = {
            'user': os.getenv('DB_USER'),
            'password': os.getenv('DB_PASSWORD'),
            'host': os.getenv('DB_HOST'),
            'port': os.getenv('DB_PORT'),
            'database': os.getenv('DB_DATABASE'),
            'ssl_ca': os.getenv('DB_SSL_CA')
        }
        
        app.logger.info("Tentative de connexion à la base de données avec SSL...")
        return mysql.connector.connect(**config)
    
    except mysql.connector.Error as err:
        app.logger.error(f"Erreur de connexion à la base de données: {err}")
        return None

def send_email_via_api(to_email, subject, message):
    API_KEY = os.environ.get('MAILGUN_API_KEY')  # Utilise les variables d'environnement pour sécuriser les clés d'API
    DOMAIN_NAME = os.environ.get('MAILGUN_DOMAIN_NAME')
    
    if not API_KEY or not DOMAIN_NAME:
        return False, "Clé d'API ou nom de domaine manquant."

    return requests.post(
        f"https://api.mailgun.net/v3/{DOMAIN_NAME}/messages",
        auth=("api", API_KEY),
        data={"from": f"Excited User <mailgun@{DOMAIN_NAME}>",
            "to": [to_email],
            "subject": subject,
            "text": message})

@app.route('/')
def index():
    app.logger.info('Page d\'accueil visitée')
    return render_template('index.html',
                        titre_hero="Ouvrez grand les Jeux !",
                        texte_hero="Réservez dès maintenant vos billets pour les Jeux Olympiques de Paris 2024.")

@app.route('/billets')
def billets():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 100, type=int)  # Ajout d'un paramètre pour le nombre d'éléments par page
    offset = (page - 1) * per_page

    billets = []  # Initialiser une liste vide pour les billets

    cnx = get_db_connection()
    if cnx is None:
        app.logger.error("Erreur de connexion à la base de données")
        return render_template('error.html'), 500

    try:
        with cnx.cursor() as cur:
            cur.execute("SELECT * FROM billets LIMIT %s OFFSET %s", (per_page, offset))
            billets = cur.fetchall()
    except mysql.connector.Error as err:
        app.logger.error(f"Erreur lors de l'exécution de la requête: {err}")
        return render_template('error.html'), 500
    finally:
        cnx.close()

    return render_template('billets.html', billets=billets, page=page, per_page=per_page)


@app.route('/ajouter_au_panier/<int:id>', methods=['POST'])
def ajouter_au_panier(id):
    if 'user_id' not in session:
        flash('Veuillez vous connecter pour ajouter au panier.', 'error')
        return redirect(url_for('login'))
    
    quantite = int(request.form['quantite'])
    if quantite <= 0:
        flash('La quantité doit être supérieure à zéro.', 'error')
        return redirect(url_for('billets'))
    
    try:
        cnx = get_db_connection()
        cur = cnx.cursor()
        cur.execute("SELECT id, nom, prix FROM billets WHERE id = %s", (id,))
        billet = cur.fetchone()
        if not billet:
            flash('Billet introuvable.', 'error')
            return redirect(url_for('billets'))
        
        if 'panier' not in session:
            session['panier'] = []
        
        panier = session['panier']
        item = next((item for item in panier if item['id'] == id), None)
        if item:
            item['quantite'] += quantite
        else:
            panier.append({'id': billet[0], 'nom': billet[1], 'prix': billet[2], 'quantite': quantite})
        
        session['panier'] = panier
        flash('Billet ajouté au panier!', 'success')
        cnx.close()
    except Exception as e:
        flash('Une erreur est survenue lors de l\'ajout au panier.', 'error')
        app.logger.error(f"Erreur : {e}")
    
    return redirect(url_for('billets'))

@app.route('/panier')
def panier():
    if 'user_id' not in session:
        flash('Veuillez vous connecter pour accéder au panier.', 'error')
        return redirect(url_for('login'))
    
    panier = session.get('panier', [])
    total = sum(float(item['prix']) * int(item['quantite']) for item in panier)
    return render_template('panier.html', panier=panier, total=total)

@app.route('/supprimer_du_panier/<int:id>')
def supprimer_du_panier(id):
    if 'panier' in session:
        session['panier'] = [item for item in session['panier'] if item['id'] != id]
        flash('Article supprimé du panier.', 'success')
    return redirect(url_for('panier'))

@app.route('/paiement', methods=['GET', 'POST'])
def paiement():
    if 'user_id' not in session:
        flash('Veuillez vous connecter pour effectuer un paiement.', 'error')
        return redirect(url_for('login'))

    if request.method == 'POST':
        achat_key = str(uuid.uuid4())
        try:
            cnx = get_db_connection()
            cur = cnx.cursor()
            for item in session['panier']:
                cur.execute("UPDATE billets SET disponible = disponible - %s WHERE id = %s",
                            (item['quantite'], item['id']))
                cur.execute("INSERT INTO achats (billet_id, user_id, quantite, achat_key) VALUES (%s, %s, %s, %s)",
                            (item['id'], session['user_id'], item['quantite'], achat_key))
            cnx.commit()
            session.pop('panier', None)

            qr = qrcode.QRCode(version=1, box_size=10, border=5)
            qr.add_data(f"Achat: {achat_key}")
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")

            buffered = BytesIO()
            img.save(buffered, format="PNG")
            img_str = base64.b64encode(buffered.getvalue()).decode()

            flash('Paiement effectué avec succès!', 'success')
            return render_template('paiement_success.html', qr_code=img_str, achat_key=achat_key)
        except Exception as e:
            cnx.rollback()
            flash('Une erreur est survenue lors du paiement. Veuillez réessayer.', 'error')
            app.logger.error(f"Erreur de paiement : {str(e)}")
            return redirect(url_for('panier'))
        finally:
            cur.close()
            cnx.close()
    return render_template('paiement.html')

@app.route('/download_qr/<achat_key>')
def download_qr(achat_key):
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(f"Achat: {achat_key}")
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    buffered = BytesIO()
    img.save(buffered, format="PNG")
    buffered.seek(0)

    return send_file(buffered, mimetype='image/png', as_attachment=True, download_name=f'qr_code_{achat_key}.png')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        cnx = get_db_connection()
        cur = cnx.cursor()
        cur.execute("SELECT * FROM users WHERE email = %s", (email,))
        user = cur.fetchone()
        cur.close()
        cnx.close()
        
        if user and bcrypt.check_password_hash(user[4], password):
            session['user_id'] = user[0]  # Stocke l'ID de l'utilisateur dans la session
            flash('Connexion réussie !', 'success')
            return redirect(url_for('index'))
        else:
            flash('Email ou mot de passe incorrect.', 'error')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        firstname = request.form['firstname']
        secondname = request.form['secondname']
        email = request.form['email']
        password = request.form['password']

        # Vérifications de sécurité
        if len(password) < 8:
            flash('Le mot de passe doit avoir au moins 8 caractères.', 'error')
            return render_template('register.html')
        if not re.search(r"[$#@!%^&*()]", password):
            flash('Le mot de passe doit contenir au moins un caractère spécial.', 'error')
            return render_template('register.html')
        if not validators.email(email):
            flash('Adresse e-mail invalide.', 'error')
            return render_template('register.html')

        # Hachage du mot de passe
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        # Génération de la clé d'enregistrement
        registration_key = str(uuid.uuid4())

        # Insertion dans la base de données
        try:
            cnx = get_db_connection()
            cur = cnx.cursor()
            while True:
                try:
                    cur.execute("INSERT INTO users (firstname, secondname, email, password, registration_key) VALUES (%s, %s, %s, %s, %s)",
                                (firstname, secondname, email, hashed_password, registration_key))
                    cnx.commit()
                    break  # Sortie de la boucle si l'insertion réussit
                except mysql.connector.errors.IntegrityError as err:
                    if 'Duplicate entry' in str(err) and 'registration_key' in str(err):
                        registration_key = str(uuid.uuid4())  # Générer une nouvelle clé si elle est en double
                    else:
                        raise

            # Envoi de l'email de confirmation via API
            success, message = send_email_via_api(email, "Confirmation d'inscription",
                f"Merci de vous être inscrit ! Veuillez confirmer votre adresse email en cliquant sur ce lien : {url_for('confirm_email', email=email, _external=True)}")

            if success:
                flash('Inscription réussie ! Vérifiez vos emails pour la confirmation.', 'success')
            else:
                flash(f"L'inscription a réussi, mais l'envoi de l'email a échoué : {message}", 'error')

            return redirect(url_for('login'))
        except Error as e:
            cnx.rollback()
            flash(f"Une erreur s'est produite lors de l'inscription : {str(e)}", 'error')
            return render_template('register.html')
        finally:
            cur.close()
            cnx.close()

    return render_template('register.html')

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
    #app.run(debug=True)