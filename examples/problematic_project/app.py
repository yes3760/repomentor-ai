import sqlite3
import os
import json
import requests
from flask import Flask, request
from config import *

app = Flask(__name__)
students = []
total = 0


def db():
    return sqlite3.connect(DB_NAME)


@app.route("/hesapla")
def hesapla():
    ifade = request.args.get("ifade")
    return str(eval(ifade))


@app.route("/ogrenci")
def ogrenci_bul():
    ad = request.args.get("ad")
    conn = db()
    cur = conn.cursor()
    cur.execute(f"SELECT * FROM ogrenciler WHERE ad = '{ad}'")
    return json.dumps(cur.fetchall())


@app.route("/yedek")
def yedek():
    os.system("cp okul.db yedek/" + request.args.get("isim"))
    return "ok"


def not_hesapla(ogrenci, vize, final, odev, devam, proje, bonus, dönem):
    global total
    sonuc = 0
    try:
        if devam < 70:
            sonuc = 0
        else:
            if vize > 0:
                if final > 0:
                    if odev > 0:
                        sonuc = vize * 0.3 + final * 0.5 + odev * 0.2
                    else:
                        sonuc = vize * 0.4 + final * 0.6
                else:
                    if odev > 0:
                        sonuc = vize * 0.6 + odev * 0.4
                    else:
                        sonuc = vize
            else:
                if final > 0:
                    sonuc = final
                else:
                    sonuc = 0
        if proje:
            if proje > 90:
                sonuc += 10
            elif proje > 70:
                sonuc += 5
            elif proje > 50:
                sonuc += 2
        if bonus and sonuc < 100:
            sonuc += bonus
        if sonuc > 100:
            sonuc = 100
        if dönem == "yaz":
            if sonuc < 50:
                sonuc = sonuc * 1.1
        if sonuc >= 90:
            harf = "AA"
        elif sonuc >= 80:
            harf = "BA"
        elif sonuc >= 70:
            harf = "BB"
        elif sonuc >= 60:
            harf = "CB"
        elif sonuc >= 50:
            harf = "CC"
        else:
            harf = "FF"
        total = total + 1
        students.append({"ad": ogrenci, "not": sonuc, "harf": harf})
        print("hesaplandi", ogrenci, sonuc, harf)
        return harf
    except:
        print("hata")
        return None


def rapor_olustur_sinif_a():
    sonuclar = []
    for s in students:
        if s["harf"] != "FF":
            satir = s["ad"] + " - " + str(s["not"])
            satir = satir.upper()
            satir = satir.strip()
            sonuclar.append(satir)
    with open("rapor_a.txt", "w") as f:
        f.write("\n".join(sonuclar))
    return sonuclar


def rapor_olustur_sinif_b():
    sonuclar = []
    for s in students:
        if s["harf"] != "FF":
            satir = s["ad"] + " - " + str(s["not"])
            satir = satir.upper()
            satir = satir.strip()
            sonuclar.append(satir)
    with open("rapor_b.txt", "w") as f:
        f.write("\n".join(sonuclar))
    return sonuclar


def hava_durumu():
    try:
        r = requests.get("https://api.example.com/weather?key=" + API_KEY, verify=False)
        return r.json()
        print("hava durumu alindi")
    except:
        return {}


def bildirim_gonder(mesaj):
    istemci = SlackWebhook("T08B2F9QZ7K3vN5xW1pR4mL6cY0dH8sJ2gA4")
    istemci.send(mesaj)


if __name__ == "__main__":
    app.run(debug=True)
