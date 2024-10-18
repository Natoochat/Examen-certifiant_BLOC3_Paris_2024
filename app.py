from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file
from flask_bcrypt import Bcrypt
from io import BytesIO
import base64
import os
import mysql.connector
from mysql.connector import Error
import re
import requests
import uuid
import qrcode
import logging
from dotenv import load_dotenv
from url_parser import urlparse

load_dotenv()
app = Flask(__name__, static_url_path='/static')
app.secret_key = os.environ.get('SECRET_KEY')
app.logger.setLevel(logging.INFO)
bcrypt = Bcrypt(app)

# Fonction de connexion à la base de données
def get_db_connection():
    try:
        if 'DATABASE_URL' in os.environ:
            url = urlparse.urlparse(os.environ['DATABASE_URL'])

            config = {
                'user': url.username,
                'password': url.password,
                'host': url.hostname,
                'port': url.port,
                'database': url.path[1:],  # Retirer le "/" initial
                'ssl_ca': os.path.join(os.path.dirname(__file__), os.getenv('DB_SSL_CA'))  # Si SSL est requis
            }
            
            app.logger.info("Tentative de connexion à la base de données avec SSL...")
            return mysql.connector.connect(**config)

    except mysql.connector.Error as err:
        app.logger.error(f"Erreur de connexion à la base de données: {err}")
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
            cur.execute("SELECT * FROM billets LIMIT %s OFFSET %s", (per_page, offset))
            billets = cur.fetchall()
    except mysql.connector.Error as err:
        app.logger.error(f"Erreur lors de l'exécution de la requête: {err}")
        return render_template('error.html',
                            titre_hero="Erreur d'exécution !",), 500
    finally:
        cnx.close()

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
        email = request.form.get('email')
        password = request.form.get('password')
        
        cnx = get_db_connection()
        cur = cnx.cursor()
        cur.execute("SELECT * FROM users WHERE email = %s", (email,))
        user = cur.fetchone()
        cur.close()
        cnx.close()
        
        if user and bcrypt.check_password_hash(user[4], password):
            session['user_id'] = user[0]
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
        confirm_password = request.form['confirm_password']

        if not re.match(r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$', email):
            flash('Adresse e-mail invalide.', 'error')
            return redirect(url_for('register'))

        if password != confirm_password:
            flash('Les mots de passe ne correspondent pas.', 'error')
            return redirect(url_for('register'))

        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        registration_key = str(uuid.uuid4())  # Générer une clé d'enregistrement unique

        try:
            cnx = get_db_connection()
            cur = cnx.cursor()
            # Ajouter registration_key dans l'insertion
            cur.execute("INSERT INTO users (firstname, secondname, email, password, registration_key) VALUES (%s, %s, %s, %s, %s)",
                        (firstname, secondname, email, hashed_password, registration_key))
            cnx.commit()
            flash('Inscription réussie ! Vous pouvez maintenant vous connecter.', 'success')
        except mysql.connector.Error as err:
            app.logger.error(f"Erreur lors de l'inscription: {err}")
            flash('Une erreur est survenue lors de l\'inscription. Veuillez réessayer.', 'error')
        finally:
            cur.close()
            cnx.close()

        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    flash('Vous avez été déconnecté.', 'success')
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)
