from datetime import datetime, timedelta
import io
import json
import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests
import yaml
from flask import Flask, make_response, redirect, render_template, request, send_file

from lib.filters import filters
from lib.location import location
from lib.proxy import *
from lib.settings import settings

app = Flask(__name__)

with open("/data/config.yml", "r", encoding="utf-8") as f:
    config_file = yaml.safe_load(f)
    f.close()

# Ajouter tous les blueprints
app.register_blueprint(location)
app.register_blueprint(settings)
app.register_blueprint(filters)

def api_link(location_cookie):

    latitude, longitude = json.loads(location_cookie)["location"]

    base_url = f"https://{config_file['api']}/v1/forecast?latitude={latitude}&longitude={longitude}&timezone=auto"
    basic = f"{base_url}&current=temperature_2m,relative_humidity_2m,apparent_temperature,is_day,precipitation,rain,surface_pressure,wind_speed_10m,wind_direction_10m&minutely_15=relative_humidity_2m,rain,wind_speed_10m&hourly=temperature_2m,relative_humidity_2m,apparent_temperature,precipitation_probability,rain,surface_pressure,cloud_cover_mid,wind_speed_10m,wind_direction_10m,uv_index,is_day,direct_radiation,snowfall&daily=temperature_2m_max,temperature_2m_min,apparent_temperature_max,apparent_temperature_min,sunrise,sunset,uv_index_max,precipitation_hours,precipitation_probability_max,precipitation_sum"
    past = f"{base_url}&hourly=temperature_2m,relative_humidity_2m,rain,direct_radiation&past_days=1&forecast_days=1"
    air_quality = f"https://air-quality-api.open-meteo.com/v1/air-quality?latitude={latitude}&longitude={longitude}&current=european_aqi&forecast_days=1"

    return basic, past, air_quality


@app.route("/")
def index():

    location_cookie = request.cookies.get("loc")


    if location_cookie == None:
        return redirect("/welcome")
    else:
        url_basic, url_past, url_air = api_link(location_cookie)
        
        data_basic = fetch_data(url_basic, config_file)
        data_past = fetch_data(url_past, config_file)
        data_air = fetch_data(url_air, config_file)

        date = data_basic["current"]["time"].replace("-", "/").split("T")[0].split("/")
        date = f"{date[2]}/{date[1]}/{date[0]}"

        data_basic["is_december"] = True if str(data_basic["current"]["time"].replace("-", "/").split("T")[0].split("/")[1]) == "12" else False

        time = int(data_basic["current"]["time"].replace("-", "/").split("T")[1].split(":")[0])

        for t in range(1,7):
            data_basic["daily"]["time"][t] = data_basic["daily"]["time"][t].replace("-", "/").split("T")[0].split("/")
            data_basic["daily"]["time"][t] = f"{data_basic['daily']['time'][t][2]}/{data_basic['daily']['time'][t][1]}/{data_basic['daily']['time'][t][0]}"

        tmp1 = []
        for i in range(time+25,time, -1):
            if i-25-time+1 < 0:
                tmp1.append(int(data_past["hourly"]["direct_radiation"][i]))

        tmp2 = []
        for i in range(time+25,time, -1):
            if i-25-time+1 < 0:
                tmp2.append(int(data_past["hourly"]["rain"][i]))

        tmp3 = []
        for i in range(time+25,time, -1):
            if i-25-time+1 < 0:
                tmp3.append(int(data_past["hourly"]["relative_humidity_2m"][i]))

        past_total = [
            sum(tmp1),
            sum(tmp2),
            round(np.mean(tmp3), 1)
        ]


        for i in range(0, len(data_basic["hourly"]["snowfall"])):
            data_basic["hourly"]["snowfall"][i] = int(data_basic["hourly"]["snowfall"][i]*10) # Convertir en mm

        for i in range(0, len(data_basic["hourly"]["direct_radiation"])):
            data_basic["hourly"]["direct_radiation"][i] = int(round(data_basic["hourly"]["direct_radiation"][i], 0))


        # Obtenir les phases lunaire et les stocker en local pour améliorer la vitesse de chargement
        moonphase = []

        with open(f"/data/moon.json", "r", encoding="utf-8") as f:
            moonDB = json.loads(f.read())
            f.close()

        if moonDB == []:
            for i in range(0, 8):
                day_timestamp = int((datetime.now() + timedelta(days=i)).timestamp())

                moon_api = fetch_data(f"https://api.farmsense.net/v1/moonphases/?d={day_timestamp}", config_file)[0]
                
                moonphase.append(["Nouvelle lune", "🌑"] if moon_api["Phase"] == "New Moon" else ["Premier croissant", "🌒"] if moon_api["Phase"] == "Waxing Crescent" else ["Premier quartier", "🌓"] if moon_api["Phase"] == "1st Quarter" else ["Lune gibbeuse croissante", "🌔"] if moon_api["Phase"] == "Waxing Gibbous" else ["Pleine lune", "🌕"] if moon_api["Phase"] == "Full Moon" else ["Lune gibbeuse décroissante", "🌖"] if moon_api["Phase"] == "Waning Gibbous" else ["Dernier quartier", "🌗"] if moon_api["Phase"] == "3rd Quarter" else ["Dernier croissant", "🌘"] if moon_api["Phase"] == "Waning Crescent" else ["Dernier croissant", "🌑"])


                moonphase[i].append(round(moon_api["Age"], 1))
                moonphase[i].append(moon_api["Illumination"]*100)
                moonphase[i].append(datetime.fromtimestamp(day_timestamp).strftime("%d/%m/%Y"))


                with open(f"/data/moon.json", "w", encoding="utf-8") as f:
                    json.dump(moonphase, f, indent=4)
                    f.close()     
        elif moonDB[0][4] != datetime.now().strftime("%d/%m/%Y"):
            moonDB.pop(0)

            # Automatiquement calculer le dernier jour
            day_timestamp = int((datetime.now() + timedelta(days=6)).timestamp())

            moon_api = fetch_data(f"https://api.farmsense.net/v1/moonphases/?d={day_timestamp}", config_file)[0]
            
            moonDB.append(["Nouvelle lune", "🌑"] if moon_api["Phase"] == "New Moon" else ["Premier croissant", "🌒"] if moon_api["Phase"] == "Waxing Crescent" else ["Premier quartier", "🌓"] if moon_api["Phase"] == "1st Quarter" else ["Lune gibbeuse croissante", "🌔"] if moon_api["Phase"] == "Waxing Gibbous" else ["Pleine lune", "🌕"] if moon_api["Phase"] == "Full Moon" else ["Lune gibbeuse décroissante", "🌖"] if moon_api["Phase"] == "Waning Gibbous" else ["Dernier quartier", "🌗"] if moon_api["Phase"] == "3rd Quarter" else ["Dernier croissant", "🌘"] if moon_api["Phase"] == "Waning Crescent" else ["Dernier croissant", "🌑"])

            moonDB[6].append(round(moon_api["Age"], 0))
            moonDB[6].append(round(moon_api["Illumination"]*100, 0))
            moonDB[6].append(datetime.fromtimestamp(day_timestamp).strftime("%d/%m/%Y"))

            moonphase = moonDB

            with open(f"/data/moon.json", "w", encoding="utf-8") as f:
                json.dump(moonDB, f, indent=4)
                f.close()
        else:
            moonphase = moonDB


            




    response = make_response(
        render_template(
            "app.html",
            date=date,
            raw=data_basic,
            time=time,
            loc=json.loads(request.cookies.get("loc")),
            config_file=config_file,
            raw_past=data_past,
            raw_air=data_air,
            past_total=past_total,
            moon_phase=moonphase,
        )
    )
    
    if not request.cookies.get("settings"):
        response.set_cookie("settings", json.dumps({"solar_radiation": True, "graphs": True}), httponly=True, secure=True, samesite='Strict')

    return response

@app.route("/welcome")
def welcome():
    """
    Page d'accueil.
    """

    if request.cookies.get("loc") != None:
        return redirect("/")

    response = make_response(
        render_template("welcome.html")
    )

    return response

@app.route("/graph")
def basic_graph():
    """
    Générer un graphique par rapport à une donnée précise.
    """
                        
    plt.switch_backend('Agg')

    location_cookie = request.cookies.get("loc")
    url_basic, url_past, url_air = api_link(location_cookie)
    data_weather = fetch_data(url_basic, config_file)

    setting_name = request.args.get("dtg")

    hours = []
    data = []

    for v in range(0, 97):
        data.append(data_weather["minutely_15"][setting_name][v])

    for h in range(0, 97):
        hours.append(data_weather["minutely_15"]["time"][h].split("T")[1])

    df = pd.DataFrame({'Temps': hours, f"{setting_name}": data})

    df = df.drop_duplicates(subset=['Temps'])
    df = df.sort_values(by='Temps')

    fig, ax = plt.subplots(figsize=(10, 6))

    ax.plot(df['Temps'], df[setting_name], marker='o', linestyle='-', color='b', label=setting_name)


    ax.legend()

    ax.set_xlabel('Temps (24h)')
    ax.set_ylabel(f"{setting_name} (Unité: {data_weather['hourly_units'][setting_name]})")

    
    plt.xticks(rotation=45)

    ax.set_xticks(ax.get_xticks()[::4])
    plt.tight_layout()

    img = io.BytesIO()
    fig.savefig(img, format='png')
    img.seek(0)

    plt.close(fig)

    return send_file(img, mimetype='image/png')

# Pages d'erreur
@app.errorhandler(404)
def not_found(error):
    return render_template("error.html", error_code=404), 404

@app.errorhandler(500)
def error(error):
    return render_template("error.html", error_code=500), 500


# Initialisation de l'application
def init():
    return app