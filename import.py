import csv
import os

from sqlalchemy import create_engine, text
from sqlalchemy.orm import scoped_session, sessionmaker
from werkzeug.security import generate_password_hash

engine = create_engine(os.getenv("DATABASE_URL")) #Engine to retrieve the database URL
db = scoped_session(sessionmaker(bind=engine)) #Session to link to the database

#def create_account():
# INSERT INTO accounts (username, password)
# VALUES ('{input username}', '{input password}')
# ON CONFLICT (username) {PRINT ACCOUNT ALREADY EXISTS};

def create_tables():
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS books (
            isbn VARCHAR PRIMARY KEY UNIQUE NOT NULL,
            title VARCHAR NOT NULL,
            author VARCHAR NOT NULL,
            year INTEGER NOT NULL
        );
    """))
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS accounts (
            id SERIAL PRIMARY KEY NOT NULL,
            username VARCHAR NOT NULL UNIQUE,
            password VARCHAR NOT NULL
        );
    """))
    db.execute(text("""
            CREATE TABLE IF NOT EXISTS ratings (
            userid INTEGER NOT NULL,
            isbn VARCHAR NOT NULL,
            rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
            comment TEXT,
            PRIMARY KEY (userid, isbn),
            FOREIGN KEY (userid) REFERENCES accounts(id) ON DELETE CASCADE,
            FOREIGN KEY (isbn) REFERENCES books(isbn) ON DELETE CASCADE
        );
    """))

def my_username():
    db.execute(
        text("INSERT INTO accounts (username, password) VALUES (:username, :password)"),
        {
            "username": "titus",
            "password": generate_password_hash("titus123")
        }
    )
    db.commit()

def drop_tables():
    db.execute(text("DROP TABLE IF EXISTS books CASCADE;"))
    db.commit()
    db.execute(text("DROP TABLE IF EXISTS accounts CASCADE;"))
    db.commit()
    db.execute(text("DROP TABLE IF EXISTS ratings CASCADE;"))
    db.commit()

def import_csv():
    file = open("books.csv")
    reader = csv.reader(file) # csv reading file
    next(reader)
    for isbn, title, author, year in reader:
        db.execute(
            text("""
                 INSERT INTO books (isbn, title, author, year)
                 VALUES (:isbn, :title, :author, :year) ON CONFLICT (isbn) DO NOTHING;
                 """),
            {"isbn": isbn, "title": title, "author": author, "year": int(year)}
        )
        db.commit() # save the changes


def main():
    drop_tables()
    create_tables()
    my_username()
    import_csv()

if __name__ == "__main__":
    main()