import mysql.connector
import os
import json
from dotenv import load_dotenv

load_dotenv() 
config = json.loads(os.getenv("DB_CONFIG")) 
# Creating connection object
mydb = mysql.connector.connect(**config)

cursor = mydb.cursor()

# Show database
cursor.execute("SHOW DATABASES")

for x in cursor:
    print(x)