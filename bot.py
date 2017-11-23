from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.sql import text
import telepot
import threading
from telepot.loop import MessageLoop
from flask import Flask, session, url_for, redirect, request, render_template, abort, send_file
from datetime import datetime, date, timedelta
import os
import time
import socket
import random
import subprocess
import json

app = Flask(__name__)
app.secret_key = "ciao"
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///db.sqlite'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
bot = telepot.Bot('')


class Legame(db.Model):
    uid = db.Column(db.Integer, db.ForeignKey('utenti.uid'), primary_key=True)
    sid = db.Column(db.Integer, db.ForeignKey('server.sid'), primary_key=True)
    nickname = db.Column(db.String, nullable=False)


class User(db.Model):
    __tablename__ = "utenti"
    uid = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String, nullable=False)
    telegram_chat_id = db.Column(db.String, nullable=False)
    server = db.relationship("Legame", backref="utenti", lazy='dynamic', cascade='delete')


class Server(db.Model):
    __tablename__ = "server"
    sid = db.Column(db.Integer, primary_key=True)
    ip = db.Column(db.String, nullable=False)
    porta = db.Column(db.Integer, nullable=False)
    utenti = db.relationship("Legame", backref="server", lazy='dynamic', cascade='delete')
    thread_name = db.Column(db.String)
    log = db.relationship("Log", back_populates="server")


class Log(db.Model):
    lid = db.Column(db.Integer, primary_key=True)
    sid = db.Column(db.Integer, db.ForeignKey('server.sid'))
    server = db.relationship("Server", back_populates="log")
    ora = db.Column(db.DateTime)
    tipo = db.Column(db.Integer)  # 0 tutto ok, 1 errore di invio ping


def handle(msg):
    content_type, chat_type, chat_id = telepot.glance(msg)
    # print(content_type, chat_type, chat_id)
    # print(msg)
    username = msg['from']['username']
    testo = msg['text']
    # print(username)
    if content_type == 'text':
        query1 = text(
            "SELECT utenti.* FROM utenti WHERE telegram_chat_id=:x;")
        utenti = db.session.execute(query1, {"x": chat_id}).fetchall()
        # print(utenti)
        if len(utenti) == 0:
            nuovoutente = User(username=username, telegram_chat_id=chat_id)
            bot.sendMessage(chat_id, 'Ciao! Grazie per esserti iscritto al Bot, utente {}'.format(username))
            db.session.add(nuovoutente)
            db.session.commit()
        else:
            user = User.query.filter_by(username=username).first()
            if testo == "/help":
                bot.sendMessage(chat_id,
                                'Lista dei comandi attualmente supportati:\n/aggiungi [IP] [NICK] [PORT] Aggiunge un server al tuo profilo\n/rimuovi[IP] [NICK] [PORT] Rimuove un server dal tuo profilo\n/status Visualizza lo stato dei tuoi server \n')
            elif testo == "/status":
                query1 = text(
                    "SELECT legame.*, server.* FROM legame JOIN server on legame.sid = server.sid WHERE legame.uid=:x;")
                server = db.session.execute(query1, {"x": user.uid}).fetchall()
                frase = "Lista server associati:\n"
                for macchine in server:
                    frase += macchine[2] + " " + macchine[4] + "\n"
                    # print(macchine)
                bot.sendMessage(chat_id, frase)
            else:
                comando, argomento = testo.split(" ", 1)
                if comando == "/aggiungi":
                    arg1, arg2, arg3 = argomento.split(" ", 2)
                    esistenti = Server.query.filter_by(ip=arg1, porta=arg3).all()
                    if len(esistenti) == 0:
                        tmp = str(len(Server.query.all()))
                        nuovoserver = Server(ip=arg1, thread_name=tmp, porta=int(arg3))
                        db.session.add(nuovoserver)
                        db.session.commit()
                        server = Server.query.filter_by(ip=arg1, porta=arg3).first()
                        nuovolegame = Legame(uid=user.uid, sid=server.sid, nickname=arg2)
                        db.session.add(nuovolegame)
                        db.session.commit()
                        scopia = server
                        t = threading.Thread(target=tennis_tavolo, name=server.thread_name, args=(scopia,))
                        t.start()
                        threads.append(t)
                        oggetto = {"IP": nuovoserver.ip, "PORTA": nuovoserver.porta, "SID": nuovoserver.ip,
                                   "PROPRIETARIO": user.username}
                        file = open("servers.json", "a")
                        file.write(json.dumps(oggetto))
                        file.close()
                    else:
                        nuovolegame = Legame(uid=user.uid, sid=esistenti[0].sid, nickname=arg2)
                        db.session.add(nuovolegame)
                        db.session.commit()
                else:
                    arg1, arg2, arg3 = argomento.split(" ", 2)
                    server = Server.query.filter_by(ip=arg1, porta=int(arg3)).first()
                    legami = Legame.query.filter_by(sid=server.sid).all()
                    legame = Legame.query.filter_by(sid=server.sid, uid=user.uid).first()
                    if len(legami) <= 1:
                        db.session.delete(legame)
                        db.session.delete(server)
                        db.session.commit()
                    else:
                        db.session.delete(legame[0])
                        db.session.commit()


def ping(server):
    # Questo codice è stato concesso da Stefano Pigozzi
    s = socket.socket()
    s.setblocking(False)
    s.settimeout(5)
    if server.ip != 0:
        try:
            s.connect((server.ip, server.porta))
        except socket.timeout:
            return 1
        except ConnectionError:
            return 1
        else:
            return 0
    else:  # ATTENZIONE: questa cosa non va su windows
        spazzatura = ""
        p = subprocess.call('ping {}'.format(server.ip), stdout=spazzatura)
        p.wait()
        return p.poll()


def tennis_tavolo(server):
    vecchiolog = Log(sid=server.sid, tipo=3, ora=datetime.now)
    while 1:
        p = ping(server)
        # print(p)
        query1 = text(
            "SELECT server.*, utenti.telegram_chat_id FROM server JOIN legame ON server.sid = legame.sid JOIN utenti ON legame.uid=utenti.uid WHERE server.sid=:x;")
        utente = db.session.execute(query1, {"x": server.sid}).fetchall()
        # print(utente)
        if p == 0:
            nuovolog = Log(sid=server.sid, tipo=0, ora=datetime.now())
        else:
            nuovolog = Log(sid=server.sid, tipo=1, ora=datetime.now())
        if vecchiolog.tipo != nuovolog.tipo:
            db.session.add(nuovolog)
            db.session.commit()
            vecchiolog = nuovolog
            if vecchiolog.tipo == 3:
                vecchiolog = nuovolog
            elif nuovolog.tipo == 0:
                for utenti in utente:
                    bot.sendMessage(utenti[4], 'Il tuo server {} è tornato online.'.format(server.ip))
                    print(utenti[4], 'Il tuo server {} è tornato online.'.format(server.ip))
            else:
                for utenti in utente:
                    bot.sendMessage(utenti[4], 'Il tuo server {} è andato offline.'.format(server.ip))
                    print(utenti[4], 'Il tuo server {} è andato offline.'.format(server.ip))
        time.sleep(10)


threads = []
threadsLock = threading.Lock()


@app.route('/')
def page_root():
    if 'username' not in session:
        return redirect(url_for('page_accedi'))
    else:
        session.pop('username')
        return redirect(url_for('page_accedi'))


@app.route('/accedi', methods=['GET', 'POST'])
def page_accedi():
    if request.method == "GET":
        return render_template("accedi.htm")
    else:
        utente = User.query.filter_by(username=request.form['username']).first()
        if utente:
            session['username'] = request.form['username']
            return redirect(url_for('page_dashboard'))
        else:
            abort(403)


@app.route('/dashboard')
def page_dashboard():
    if 'username' not in session or 'username' is None:
        abort(403)
    else:
        user = User.query.filter_by(username=session['username']).first()
        query1 = text(
            "SELECT legame.*, server.* FROM legame JOIN server on legame.sid = server.sid WHERE legame.uid=:x;")
        server = db.session.execute(query1, {"x": user.uid}).fetchall()
        return render_template("dashboard.htm", servers=server, utente=user)


@app.route("/serverDelete/<int:sid>")
def page_delete(sid):
    if 'username' not in session or 'username' is None:
        abort(403)
    server = Server.query.filter_by(sid=sid).first()
    legami = Legame.query.filter_by(sid=server.sid).all()
    user = User.query.filter_by(username=session['username']).first()
    legame = Legame.query.filter_by(sid=server.sid, uid=user.uid).first()
    if len(legami) <= 1:
        db.session.delete(server)
        db.session.delete(legame)
        db.session.commit()
        with threadsLock:
            for th in threads:
                th.join()
    else:
        db.session.delete(legame[0])
        db.session.commit()
    return redirect(url_for('page_dashboard'))


@app.route("/serverLog/<int:sid>")
def page_log(sid):
    if 'username' not in session or 'username' is None:
        abort(403)
    else:
        user = User.query.filter_by(username=session['username']).first()
        logs = Log.query.filter_by(sid=sid).all()
        return render_template("logs.htm", logs=logs, utente=user, sid=sid)


@app.route("/obtainLog/<int:sid>")
def page_download(sid):
    if 'username' not in session or 'username' is None:
        abort(403)
    else:
        query1 = text(
            "SELECT log.*, server.*, legame.* FROM log JOIN server on log.sid = server.sid JOIN legame on server.sid = legame.sid WHERE log.sid=:x;")
        logs = db.session.execute(query1, {"x": sid}).fetchall()
        testo = ""
        testo += logs[0][2] + " startlog\n"
        for log in logs:
            if log[3] == "1":
                stato = "dead"
            else:
                stato = "alive"
            testo += str(log[2]) + " " + str(log[10]) + " " + str(log[5]) + ":" + str(log[6]) + " " + str(stato) + "\n"
        testo += str(datetime.now()) + " endlog"
        output = open("{}.log".format(str(logs[0][5])), "w")
        output.write(testo)
        output.close()
        return send_file("{}.log".format(str(logs[0][5])), attachment_filename="filedilog.log")


if __name__ == "__main__":
    if not os.path.isfile("db.sqlite"):
        db.create_all()
    MessageLoop(bot, handle).run_as_thread()
    print("Avvio del bot...")
    time.sleep(2)
    print("Avvio dei thread...")
    servers = Server.query.all()
    for server in servers:
        scopia = server
        t = threading.Thread(target=tennis_tavolo, name=server.thread_name, args=(scopia,))
        t.daemon = True
        t.start()
        threads.append(t)
        print("     Avviato controllo su ", server.ip)
    app.run(host='0.0.0.0', port=5678)
    while 1:
        a = 1
        # Oh qualcosa dovrà pur fare, no?
