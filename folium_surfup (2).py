import streamlit as st
import folium
from streamlit_folium import st_folium
import openmeteo_requests
import requests_cache
from retry_requests import retry
import numpy as np

st.set_page_config(layout="wide")
st.title("Surf’s up… or down? A surf forecast map for novice surfers")
# API SETUP
cache_session = requests_cache.CachedSession('.cache', expire_after=60)
retry_session = retry(cache_session, retries=5, backoff_factor=0.2)
openmeteo = openmeteo_requests.Client(session=retry_session)

# Surfspot locations + Webcam links
locations = [
    ("Laredo Beach", 43.4189, -3.4362, 51.9, "https://www.youtube.com/watch?v=xdi4_E5zCKg"),
    ("El Puerto", 43.4152, -3.4203, 353.4, None),
    ("Berria Beach", 43.4663, -3.4657, 10.2, "https://www.watsaysurfschool.com/webcam/"),
    ("Somo Beach", 43.4594, -3.7325, 328.6, "https://www.escuelacantabradesurf.com/en/somo-web-cam/"),
    ("Langre", 43.4760, -3.6910, 358, None),
    ("El Sardinero", 43.4739, -3.7818, 47, "https://www.skylinewebcams.com/en/webcam/espana/cantabria/santander/playa-del-sardinero.html")
]
# Wave + wind formulas

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
    if (wind_speed < 49) and (0.6 < local_H < 2.5):
        return (0.5 * wave_factor + 0.15 * ws_factor + 0.35 * wd_factor)
    return 0

def wetsuit(temp):
    if temp <= 7.5: return "6/5 mm"
    elif temp <= 11.5: return "5/4 mm"
    elif temp <= 15.5: return "4/3 mm"
    elif temp <= 17.5: return "3/2 mm"
    elif temp <= 20.5: return "2/1 mm"
    else: return "Shorty"

# Colour scale
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

# Fetch data
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

# Create map + beach navigator

st.sidebar.title("Beach Navigator")
beach_names = [loc["name"] for loc in locations_data]
selected_beach_name = st.sidebar.selectbox("Jump to a Beach:", ["Overview"] + beach_names)

if selected_beach_name == "Overview":
    map_center = [43.49633036878374, -3.603513119090905]
    start_zoom = 10
else:
    selected_loc = next(item for item in locations_data if item["name"] == selected_beach_name)
    map_center = [selected_loc["lat"], selected_loc["lon"]]
    start_zoom = 13
    
# Define the boundaries 

map_bounds = [[43.30, -4.2], [43.60, -1.5]]

m = folium.Map(
    location=map_center,    
    zoom_start=start_zoom,  
    min_zoom=10,
    max_zoom=15,
    max_bounds=True,
    tiles=None,
    min_lat=43.30, max_lat=43.90, min_lon=-4.2, max_lon=-1.5
)

# 1. Add a toggle in the sidebar
st.sidebar.subheader("Map Settings")
map_style = st.sidebar.radio("Map Style:", ["Standard Map", "Satellite View"])

# 2. Add layers based on the sidebar selection
if map_style == "Standard Map":
    folium.TileLayer('openstreetmap', name='Standard Map').add_to(m)
else:
    folium.TileLayer(
        tiles='https://{s}.google.com/vt/lyrs=s&x={x}&y={y}&z={z}',
        attr='Google',
        name='Google Satellite',
        subdomains=['mt0', 'mt1', 'mt2', 'mt3']
    ).add_to(m)
    
# Colour mapping based on score
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

            <b>Score:</b> {loc['score']:.2f}<br>
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
# Sleek Horizontal Legend
st_folium(m, width=900, height=500)

st.markdown("""
<style>
    .mini-legend {
        background-color: white;
        padding: 10px;
        border-radius: 8px;
        border: 1px solid #ddd;
        max-width: 350px; /* This makes it smaller */
        margin-top: 5px;
        font-family: sans-serif;
    }
    .legend-title {
        font-size: 14px;
        font-weight: bold;
        margin-bottom: 8px;
        color: #333;
        text-align: center;
    }
    .bar-container {
        display: flex;
        height: 12px;
        border-radius: 6px;
        overflow: hidden;
    }
    .bar-segment { flex: 1; }
    .label-container {
        display: flex;
        justify-content: space-between;
        margin-top: 5px;
        font-size: 10px;
        color: #666;
    }
</style>

<div class="mini-legend">
    <div class="legend-title">Surf Score Legend</div>
    <div class="bar-container">
        <div class="bar-segment" style="background-color: black;"></div>
        <div class="bar-segment" style="background-color: #8B0000;"></div>
        <div class="bar-segment" style="background-color: red;"></div>
        <div class="bar-segment" style="background-color: orange;"></div>
        <div class="bar-segment" style="background-color: #90EE90;"></div>
        <div class="bar-segment" style="background-color: green;"></div>
    </div>
    <div class="label-container">
        <span>Unsurfable</span>
        <span>Very poor</span>
        <span>Poor</span>
        <span>Fair</span>
        <span>Good</span>
        <span>Excellent</span>
    </div>
</div>
""", unsafe_allow_html=True)

