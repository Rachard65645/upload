from flask_sqlalchemy import SQLAlchemy
from flask import Flask
import mysql.connector
from mysql.connector import errorcode


app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "mysql://root:@localhost:3306/alchemy"
db = SQLAlchemy(app)


def createTable():
    try:
        with app.app_context():
            db.create_all()  
            print("Tables crées avec success")
    except Exception as err:
        print(f"Error: {err}")

def create_database_if_not_exists(db_name , host, user, password):
    try:
        # Établir la connexion au serveur MySQL
        conn = mysql.connector.connect(
            host=host,
            user=user,
            password=password
        )
        cursor = conn.cursor()

        # Créer la base de données si elle n'existe pas
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {db_name};")
        print(f"Base de données '{db_name}' créée ou déjà existante.")

    except mysql.connector.Error as err:
        if err.errno == errorcode.ER_ACCESS_DENIED_ERROR:
            print("Erreur d'accès : Vérifiez votre nom d'utilisateur ou mot de passe.")
        elif err.errno == errorcode.ER_BAD_DB_ERROR:
            print("Base de données introuvable.")
        else: 
            print(f"Erreur : {err}")
    finally:
        cursor.close()
        conn.close()




class VideoFiles(db.Model):
    __tablename__ = 'video_files'
    id = db.Column(db.String(26), primary_key=True)
    filename = db.Column(db.String(255), nullable = False)
    folder_path = db.Column(db.String(255), nullable = False)
    format = db.relationship('Formats', backref='video_files', lazy=True) 
    

class Formats(db.Model):
    __tablename__ = 'formats'
    id = db.Column(db.String(26), primary_key=True)
    video_files_id = db.Column(db.String(26), db.ForeignKey('video_files.id'))
    resolution = db.Column(db.JSON)
    isOriginal = db.Column(db.Boolean)
    extension = db.Column(db.String(10))
    size = db.Column(db.String(50))
    path = db.Column(db.String(255))