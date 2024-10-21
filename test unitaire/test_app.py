import unittest
from run import app

class AppTestCase(unittest.TestCase):
    def setUp(self):
        self.app = app.test_client()
        self.app.testing = True
        
    def test_index(self):
            """Test de la route index."""
            response = self.app.get('/')
            self.assertEqual(response.status_code, 200)
            self.assertIn(b'Ouvrez grand les Jeux !', response.data)
            
            
    def test_login(self):
            """Test de la route login."""
            response = self.app.get('/login')
            self.assertEqual(response.status_code, 200)
            with self.app.session_transaction() as session:
                session['_flashes'] = {'success': ['Connexion réussie !']}  # Simule les flashes
            self.assertIn('Connexion réussie !', session['_flashes']['success'])  # Vérifie que le texte de connexion est affiché
    def test_logout(self):
        """Test de la route logout."""
        with self.app.session_transaction() as session:
            session['user_id'] = 1  # Simule un utilisateur connecté

        response = self.app.get('/logout')
        self.assertEqual(response.status_code, 302)  # Vérifie la redirection après déconnexion
        with self.app.session_transaction() as session:
            self.assertNotIn('user_id', session)  # Vérifie que l'utilisateur a été déconnecté

if __name__ == '__main__':
    unittest.main()
