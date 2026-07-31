import mysql.connector

def get_connection():
    return mysql.connector.connect(
        host="localhost",
        user="llm_user",
        password="1234",
        database="llm_config"
    )