import streamlit as st
import folium
from streamlit_folium import st_folium
import openmeteo_requests
import requests_cache
from retry_requests import retry
import numpy as np

st.set_page_config(layout="wide")
st.title("Surf Suitability Map (Beginner Focus)")

# ------------------------
# API SETUP
# ------------------------
cache_session = requests_cache.CachedSession('.cache', expire_after=60)
retry_session = retry(cache_session, retries=5, backoff_factor=0.2)
openmeteo = openmeteo_requests.Client(session=retry_session)

# ------------------------
# SURFSPOTS + WEBCAMS
# ------------------------
locations = [
    ("Laredo Beach", 43.4189, -3.4362, 51.9, "https://www.youtube.com/watch?v=xdi4_E5zCKg"),
    ("El Puerto", 43.4152, -3.4203, 353.4, None),
    ("Berria Beach", 43.4663, -3.4657, 10.2, "https://www.watsaysurfschool.com/webcam/"),
    ("Somo Beach", 43.4594, -3.7325, 328.6, "https://www.escuelacantabradesurf.com/en/somo-web-cam/"),
    ("Langre", 43.4760, -3.6910, 358, None),
    ("El Sardinero", 43.4739, -3.7818, 47, "https://www.skylinewebcams.com/en/webcam/espana/cantabria/santander/playa-del-sardinero.html")
]

# ------------------------
# FUNCTIONS
# ------------------------
def local_wave_height(wave_height, wave_direction, optimal_wave_direction):
    diff = abs(wave_direction - optimal_wave_direction) % 360
    delta = min(diff, 360 - diff)
    base = (1 + np.cos(np.radians(delta))) / 2
    factor = 1.4 * (base ** 1.75)
    return wave_height * factor

def local_wind_speed_factor(wind_speed):
    return 1 if wind_speed <= 10 else (10 / wind_speed)

def local_wind_dir_factor(wind_direction, optimal_wave_direction):
    diff = abs(wind_direction - optimal_wave_direction) % 360
    delta = min(diff, 360 - diff)
    base = (1 - np.cos(np.radians(delta))) / 2
    return 0.1 + (0.9 * base)

def wave_height_factor(local_H):
    if local_H < 0.7:
        return max(0, local_H / 0.7)
    elif local_H <= 1.0:
        return 1.0
    else:
        return min(1, max(0, 1 - (local_H - 0.9) / 0.9))

def surf_score(local_H, wind_speed, wave_factor, ws_factor, wd_factor):
    if (wind_speed < 30) and (0.6 < local_H < 2.5):
        return (0.5 * wave_factor + 0.15 * ws_factor + 0.35 * wd_factor)
    return 0

def wetsuit(temp):
    if temp <= 7.5: return "6/5 mm"
    elif temp <= 11.5: return "5/4 mm"
    elif temp <= 15.5: return "4/3 mm"
    elif temp <= 17.5: return "3/2 mm"
    elif temp <= 20.5: return "2/1 mm"
    else: return "Shorty"

# 🎯 NEW COLOR SCALE (your exact specification)
def score_color(score):
    if score == 0:
        return "black"
    elif score <= 0.2:
        return "darkred"
    elif score <= 0.4:
        return "red"
    elif score <= 0.6:
        return "orange"
    elif score <= 0.8:
        return "lightgreen"
    else:
        return "green"

# ------------------------
# FETCH DATA
# ------------------------
locations_data = []

for name, lat, lon, optimal_dir, webcam in locations:
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": ["wave_height", "wave_direction", "sea_surface_temperature"],
        "timezone": "Europe/Berlin",
        "forecast_days": 1,
    }

    params2 = {
        "latitude": lat,
        "longitude": lon,
        "hourly": ["wind_speed_10m", "wind_direction_10m"],
        "timezone": "Europe/Berlin",
        "forecast_days": 1,
    }

    response = openmeteo.weather_api("https://marine-api.open-meteo.com/v1/marine", params=params)[0]
    response2 = openmeteo.weather_api("https://api.open-meteo.com/v1/forecast", params=params2)[0]

    idx = 0

    wave_height = response.Hourly().Variables(0).ValuesAsNumpy()[idx]
    wave_direction = response.Hourly().Variables(1).ValuesAsNumpy()[idx]
    sst = response.Hourly().Variables(2).ValuesAsNumpy()[idx]

    wind_speed = response2.Hourly().Variables(0).ValuesAsNumpy()[idx]
    wind_direction = response2.Hourly().Variables(1).ValuesAsNumpy()[idx]

    local_H = local_wave_height(wave_height, wave_direction, optimal_dir)
    ws_factor = local_wind_speed_factor(wind_speed)
    wd_factor = local_wind_dir_factor(wind_direction, optimal_dir)
    wave_factor = wave_height_factor(local_H)
    score = surf_score(local_H, wind_speed, wave_factor, ws_factor, wd_factor)

    locations_data.append({
        "name": name,
        "lat": lat,
        "lon": lon,
        "score": score,
        "wave": local_H,
        "wind": wind_speed,
        "sst": sst,
        "wetsuit": wetsuit(sst),
        "webcam": webcam
    })

# ------------------------
# CREATE MAP (IMPROVED)
# ------------------------
m = folium.Map(
    max_bounds=True,
    location=[43.493198, -3.587073],
    zoom_start=8,
    min_zoom=6,
    max_zoom=16,
)
# Google Satellite Layer
folium.TileLayer(
    tiles='https://{s}.google.com/vt/lyrs=s&x={x}&y={y}&z={z}',
    attr='Google',
    name='Google Satellite',
    max_zoom=20,
    subdomains=['mt0', 'mt1', 'mt2', 'mt3']
).add_to(m)

# 🎨 Color mapping based on score
def score_label(score):
    if score == 0:
        return "unsurfable"
    elif score <= 0.2:
        return "very poor"
    elif score <= 0.4:
        return "poor"
    elif score <= 0.6:
        return "fair"
    elif score <= 0.8:
        return "good"
    else:
        return "excellent"

# For each location
for loc in locations_data:

    label = score_label(loc["score"])
    color = score_color(loc["score"])

    webcam_html = (
        f'<a href="{loc["webcam"]}" target="_blank" '
        'style="display:block;text-align:center;background-color:#3498db;'
        'color:white;padding:8px;text-decoration:none;border-radius:5px;'
        'font-weight:bold;font-size:12px;">📺 VIEW LIVE WEBCAM</a>'
        if loc["webcam"]
        else '<div style="text-align:center;font-size:12px;">No webcam available</div>'
    )

    popup_html = f"""
    <div style="font-family: Helvetica, sans-serif; width: 220px; padding: 5px;">
        <h4 style="margin:0 0 10px 0; color:#2c3e50; border-bottom:2px solid #3498db;">
            {loc['name']}
        </h4>

        <div style="background-color:#f8f9fa; padding:10px; border-radius:8px;
                    border-left:5px solid {color};">

            <b>Condition:</b> 
            <span style="color:{color}; text-transform:uppercase;">
                {label}
            </span><br>

            <b>Score:</b> {loc['score'] * 10:.1f}<br>
            <b>Wave:</b> {loc['wave']:.2f} m<br>
            <b>Wind:</b> {loc['wind']:.1f} m/s<br>
            <b>Sea Temp:</b> {loc['sst']:.1f} °C<br>
            <b>Wetsuit:</b> {loc['wetsuit']}
        </div>

        <br>
        {webcam_html}
    </div>
    """

    folium.Marker(
        location=[loc["lat"], loc["lon"]],
        popup=folium.Popup(popup_html, max_width=260),
        tooltip=f"{loc['name']} ({label})",
        icon=folium.Icon(color=color)
    ).add_to(m)

# ------------------------
# DISPLAY
# ------------------------
st_folium(m, width=900, height=600)

st.markdown("""
**Legend surf scores:**
- Black = 0 (unsurfable)
- Dark red = 0–0.2 (very poor)
- Red = 0.2–0.4 (poor)
- Orange = 0.4–0.6 (fair)
- Light green = 0.6–0.8 (good)
- Dark green = 0.8–1 (excellent)
""")
