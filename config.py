import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'cambia-esta-clave')

    MYSQL_HOST = os.environ.get('MYSQL_HOST', 'localhost')
    MYSQL_USER = os.environ.get('MYSQL_USER', 'root')
    MYSQL_PASSWORD = os.environ.get('MYSQL_PASSWORD', '')
    MYSQL_DB = os.environ.get('MYSQL_DB', 'encuestas_db')
    MYSQL_PORT = int(os.environ.get('MYSQL_PORT', 3306))
