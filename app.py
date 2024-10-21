from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file
from flask_bcrypt import Bcrypt
from io import BytesIO
import base64
import os
import mysql.connector
import re
import uuid
import qrcode
import logging
from dotenv import load_dotenv
from mysql.connector import errorcode
import requests
import forms

load_dotenv()
app = Flask(__name__, static_url_path='/static')
app.secret_key = os.environ.get('SECRET_KEY')
app.logger.setLevel(logging.INFO)
bcrypt = Bcrypt(app)

# Fonction de connexion à la base de données
def get_db_connection():
    connection = None  # Initialisation de la variable connection
    try:
        db_user = os.getenv('STACKHERO_MYSQL_ROOT_USER', os.getenv('DB_USER'))
        db_password = os.getenv('STACKHERO_MYSQL_ROOT_PASSWORD', os.getenv('DB_PASSWORD'))
        db_host = os.getenv('STACKHERO_MYSQL_HOST', os.getenv('DB_HOST'))
        db_port = os.getenv('STACKHERO_MYSQL_PORT', os.getenv('DB_PORT'))
        db_database = os.getenv('DB_DATABASE', 'billetterie')
        db_ssl_ca = os.getenv(os.getenv('DB_SSL_CA'))   # Assure-toi que la variable d'environnement est correcte

        # Vérification des variables d'environnement
        if not all([db_user, db_password, db_host, db_port, db_database]):
            missing_vars = [var for var, val in {
                'USER': db_user,
                'PASSWORD': db_password,
                'HOST': db_host,
                'PORT': db_port,
                'DATABASE': db_database,
            }.items() if not val]
            app.logger.error(f"Les variables d'environnement suivantes sont manquantes : {', '.join(missing_vars)}.")
            return None

        # Configuration de la connexion
        config = {
            'user': db_user,
            'password': db_password,
            'host': db_host,
            'port': db_port,
            'database': db_database,
            'ssl_ca': db_ssl_ca,  # Correction ici pour utiliser le bon certificat CA
            'ssl_disabled': False,  # SSL activé
        }

        app.logger.info("Tentative de connexion à la base de données avec SSL...")
        connection = mysql.connector.connect(**config)
        app.logger.info("Connexion à la base de données réussie.")
        return connection

    except mysql.connector.Error as err:
        if err.errno == errorcode.ER_ACCESS_DENIED_ERROR:
            app.logger.error("Le nom d'utilisateur ou le mot de passe est incorrect.")
        elif err.errno == errorcode.ER_BAD_DB_ERROR:
            app.logger.error("La base de données n'existe pas.")
        else:
            app.logger.error(f"Erreur de connexion à la base de données : {err}")
        return None


@app.route('/')
def index():
    app.logger.info('Page d\'accueil visitée')
    return render_template('index.html',
                        titre_hero="Ouvrez grand les Jeux !",
                        texte_hero="Réservez dès maintenant vos billets pour les Jeux Olympiques de Paris 2024.")

@app.route('/billets')
def billets():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 100, type=int)
    offset = (page - 1) * per_page

    billets = []
    cnx = get_db_connection()
    if cnx is None:
        app.logger.error("Erreur de connexion à la base de données")
        return render_template('error.html',
                            titre_hero="Erreur de connexion!",), 500

    try:
        with cnx.cursor() as cur:
            # Mise à jour de la requête pour inclure les nouvelles colonnes
            cur.execute("SELECT id, nom, prix, disponible, date, lieu, heure FROM billets LIMIT %s OFFSET %s", (per_page, offset))
            billets = cur.fetchall()
    except mysql.connector.Error as err:
        app.logger.error(f"Erreur lors de l'exécution de la requête: {err}")
        return render_template('error.html',
                            titre_hero="Erreur d'exécution !",), 500
    finally:
        cnx.close()

    # Passer les billets récupérés au template
    return render_template('billets.html', billets=billets, page=page, per_page=per_page)

@app.route('/ajouter_au_panier/<int:id>', methods=['POST'])
def ajouter_au_panier(id):
    if 'user_id' not in session:
        flash('Veuillez vous connecter pour ajouter au panier.', 'error')
        return redirect(url_for('login'))
    
    # Utilisez request.form.get pour éviter une KeyError
    quantite = request.form.get('quantite', type=int)
    if quantite is None or quantite <= 0:
        flash('La quantité doit être supérieure à zéro.', 'error')
        return redirect(url_for('billets'))
    
    try:
        cnx = get_db_connection()
        cur = cnx.cursor()
        cur.execute("SELECT id, nom, prix FROM billets WHERE id = %s and disponible >= %s", (id,quantite)) #ajout de la vérifiaction de quantité disponible
        billet = cur.fetchone()
        if not billet:
            flash('Aucun billet disponible', 'error')
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
    except Exception as e:
        flash('Une erreur est survenue lors de l\'ajout au panier.', 'error')
        app.logger.error(f"Erreur : {e}")
    finally:
        cur.close()
        cnx.close()

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

def luhn_check(card_number):
    """Vérifie si le numéro de carte est valide selon l'algorithme de Luhn."""
    total = 0
    reverse_digits = card_number[::-1]
    for i, digit in enumerate(reverse_digits):
        n = int(digit)
        if i % 2 == 1:  # Double le chiffre tous les deux
            n *= 2
            if n > 9:  # Soustraire 9 si le résultat est supérieur à 9
                n -= 9
        total += n
    return total % 10 == 0

def simulate_payment(card_number, total):
    # Vérifier si card_number est None ou non valide
    if card_number is None or not card_number.isdigit() or len(card_number) != 16:
        return False  # La carte est invalide

    # Vérifier avec l'algorithme de Luhn
    if not luhn_check(card_number):
        return False  # La carte échoue à la vérification de Luhn

    # Simuler un traitement de paiement
    if card_number == "4111111111111111":  # Numéro de carte valide pour les paiements < 100
        return True
    elif card_number == "1234567890123456":  # Numéro de carte invalide
        return False

    return False

def is_valid_expiration_date(expiration_date):
    from datetime import datetime
    
    # Vérifier le format MM/AA
    try:
        month, year = map(int, expiration_date.split('/'))
        # Vérifier que le mois est entre 1 et 12
        if month < 1 or month > 12:
            return False
        # Vérifier si la date d'expiration est dans le futur
        current_year = datetime.now().year % 100  # Obtenir l'année actuelle sur 2 chiffres
        current_month = datetime.now().month
        return (year > current_year) or (year == current_year and month >= current_month)
    except (ValueError, IndexError):
        return False

@app.route('/paiement', methods=['GET', 'POST'])
def paiement():
    if 'user_id' not in session:
        flash('Veuillez vous connecter pour effectuer un paiement.', 'error')
        return redirect(url_for('login'))

    form = forms.PaymentForm()

    if request.method == 'POST':
        # Récupérer les informations de paiement
        card_number = request.form.get('card_number')
        expiration_date = request.form.get('expiration')
        cvv = request.form.get('cvv')

        # Vérification si le numéro de carte n'est pas None et s'il est valide
        if not card_number or not card_number.isdigit() or len(card_number) != 16:
            flash('Numéro de carte invalide.', 'error')
            return redirect(url_for('paiement'))

        # Vérification de la validité du numéro de carte via l'algorithme de Luhn
        if not luhn_check(card_number):
            flash('Numéro de carte invalide (algorithme de Luhn).', 'error')
            return redirect(url_for('paiement'))

        # Vérification si le CVV n'est pas None et s'il est valide
        if not cvv or not cvv.isdigit() or len(cvv) not in [3, 4]:
            flash('Code de sécurité (CVV) invalide.', 'error')
            return redirect(url_for('paiement'))

        # Validation de la date d'expiration
        if not is_valid_expiration_date(expiration_date):
            flash('Date d\'expiration invalide.', 'error')
            return redirect(url_for('paiement'))

        # Simuler le paiement (ou appeler une fonction réelle de traitement de paiement)
        if not simulate_payment(card_number, total=0):  # Mettre à jour avec le montant réel
            flash('Détails de paiement invalides. Veuillez réessayer.', 'error')
            return redirect(url_for('panier'))

        achat_key = str(uuid.uuid4())
        total_payer = 0

        try:
            cnx = get_db_connection()
            cur = cnx.cursor()

            # Récupérer la clé d'enregistrement de l'utilisateur
            cur.execute("SELECT registration_key FROM users WHERE id = %s", (session['user_id'],))
            registration_key = cur.fetchone()
            if registration_key:
                registration_key = registration_key[0]
            else:
                flash('Erreur lors de la récupération de la clé d\'enregistrement.', 'error')
                return redirect(url_for('panier'))

            for item in session['panier']:
                id_billet = item['id']
                quantite = item['quantite']

                cur.execute("SELECT disponible, prix FROM billets WHERE id = %s", (id_billet,))
                billet = cur.fetchone()

                if billet and billet[0] >= quantite:
                    total_payer += billet[1] * quantite

                    cur.execute("UPDATE billets SET disponible = disponible - %s WHERE id = %s", (quantite, id_billet))
                    cur.execute("INSERT INTO achats (user_id, billet_id, quantite, montant, achat_key) VALUES (%s, %s, %s, %s, %s)",
                               (session['user_id'], id_billet, quantite, billet[1] * quantite, achat_key))
                else:
                    flash(f'Pas assez de billets disponibles pour {item["nom"]}.', 'error')
                    cnx.rollback()
                    return redirect(url_for('panier'))

            cnx.commit()

            # Génération du QR Code
            qr_data = f"Achat clé: {achat_key}, Clé d'enregistrement: {registration_key}, Total payé: {total_payer}"
            qr = qrcode.make(qr_data)

            img_byte_arr = BytesIO()
            qr.save(img_byte_arr, format='PNG')
            img_byte_arr.seek(0)

            img_base64 = base64.b64encode(img_byte_arr.getvalue()).decode('utf-8')
            img_str = f"data:image/png;base64,{img_base64}"

            flash('Paiement effectué avec succès!', 'success')
            session.pop('panier', None)  # Vider le panier après le paiement

            return render_template('paiement_success.html', qr_code=img_str, achat_key=achat_key)

        except Exception as e:
            cnx.rollback()
            flash('Une erreur est survenue lors du paiement. Veuillez réessayer.', 'error')
            app.logger.error(f"Erreur de paiement : {str(e)}")
            return redirect(url_for('panier'))

        finally:
            cur.close()
            cnx.close()

    return render_template('paiement.html', form=form)

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
    form = forms.LoginForm()
    if form.validate_on_submit():
        email = form.email.data
        password = form.password.data
        
        cnx = get_db_connection()
        cur = cnx.cursor()
        cur.execute("SELECT id, password FROM users WHERE email = %s", (email,))
        user = cur.fetchone()
        cur.close()
        cnx.close()
        
        if user and bcrypt.check_password_hash(user[1], password):
            session['user_id'] = user[0]
            flash('Connexion réussie !', 'success')
            return redirect(url_for('index'))
        else:
            flash('Email ou mot de passe incorrect.', 'error')
    return render_template('login.html', form=form)

@app.route('/register', methods=['GET', 'POST'])
def register():
    form = forms.RegistrationForm()
    if form.validate_on_submit():
        firstname = form.firstname.data
        secondname = form.secondname.data
        email = form.email.data
        password = form.password.data
        confirm_password = form.confirm_password.data  # Utiliser le champ du formulaire

        # Vérification de l'unicité de l'email
        cnx = get_db_connection()
        cur = cnx.cursor()
        cur.execute("SELECT id FROM users WHERE email = %s", (email,))
        if cur.fetchone():
            flash('Cette adresse email est déjà utilisée.', 'error')
            return redirect(url_for('register'))

        # Hachage du mot de passe
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        registration_key = str(uuid.uuid4())  # Générer une clé d'enregistrement unique
        
        try:
            cur.execute("""
                INSERT INTO users (firstname, secondname, email, password, registration_key) 
                VALUES (%s, %s, %s, %s, %s)
            """, (firstname, secondname, email, hashed_password, registration_key))
            cnx.commit()

            # Préparer l'e-mail de validation
            validation_link = f'https://jo-2024-7880c127844d.herokuapp.com/{registration_key}'
            send_validation_email(email, validation_link)

            flash('Inscription réussie ! Un e-mail de validation a été envoyé.', 'success')
        except mysql.connector.Error as err:
            app.logger.error(f"Erreur lors de l'inscription: {err}")
            flash('Une erreur est survenue lors de l\'inscription. Veuillez réessayer.', 'error')
        finally:
            cur.close()
            cnx.close()

        return redirect(url_for('login'))
    
    return render_template('register.html', form=form)

def send_validation_email(to_email, validation_link):
    # Préparer l'envoi de l'e-mail via l'API Mailgun
    response = requests.post(
        f'https://api.mailgun.net/v3/{os.getenv("MAILGUN_DOMAIN")}/messages',
        auth=('api', os.getenv('MAILGUN_API_KEY')),
        data={
            'from': os.getenv('MAILGUN_USERNAME'),
            'to': to_email,
            'subject': 'Validation de votre inscription',
            'text': f'Bienvenue ! Veuillez valider votre e-mail en cliquant sur ce lien : {validation_link}'
        }
    )
    
    if response.status_code != 200:
        app.logger.error(f"Erreur lors de l'envoi de l'e-mail : {response.text}")
    else:
        app.logger.info("E-mail de validation envoyé avec succès.")

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    flash('Vous avez été déconnecté.', 'success')
    return redirect(url_for('index'))

@app.route('/mes_achats')
def mes_achats():
    if 'user_id' not in session:
        flash('Veuillez vous connecter pour voir vos achats.', 'error')
        return redirect(url_for('login'))

    cnx = get_db_connection()
    cur = cnx.cursor()
    cur.execute("SELECT id, montant, achat_key, date_achat FROM achats WHERE user_id = %s", (session['user_id'],))
    achats = cur.fetchall()
    cur.close()
    cnx.close()

    return render_template('mes_achats.html', achats=achats)

if __name__ == '__main__':
    app.run(debug=True)
