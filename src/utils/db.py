import mysql.connector
import os
import json
from dotenv import load_dotenv
from mysql.connector import errorcode

load_dotenv() 
config = json.loads(os.getenv("DB_CONFIG")) 


def connexion() :
    try : 
        # Creating connection object
        cnx = mysql.connector.connect(**config)

    except mysql.connector.Error as err:
        if err.errno == errorcode.ER_ACCESS_DENIED_ERROR:
            print("Something is wrong with your user name or password")
        elif err.errno == errorcode.ER_BAD_DB_ERROR:
            print("Database does not exist")
        else:
            print(err)
    else:
        return cnx
    
def deconnexion(cnx):
    cnx.close()

def get_cursor(cnx):
    return cnx.cursor()

def close_cursor(cursor):
    cursor.close()

