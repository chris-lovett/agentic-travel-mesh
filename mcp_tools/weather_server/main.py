"""
Weather Server (MCP Tool + Envoy Sidecar)
Provides destination weather forecast and climate conditions for the Weather Agent.
"""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, List
import random

app = FastAPI(title="Weather MCP Server", version="1.0.0")

class WeatherQuery(BaseModel):
    destination: str
    days: int = 4

WEATHER_DATABASE = {
    "san francisco": {"temp_c": 18, "condition": "Partly Cloudy / Coastal Fog", "precipitation_chance": 15, "packing": "Light layers, light jacket, walking shoes"},
    "new york": {"temp_c": 22, "condition": "Sunny", "precipitation_chance": 5, "packing": "Comfortable summer/fall attire, umbrella just in case"},
    "london": {"temp_c": 15, "condition": "Light Rain / Overcast", "precipitation_chance": 65, "packing": "Waterproof jacket, umbrella, warm layers"},
    "tokyo": {"temp_c": 24, "condition": "Clear & Mild", "precipitation_chance": 10, "packing": "Breathable clothing, comfortable sneakers"},
    "paris": {"temp_c": 20, "condition": "Breezy & Sunny", "precipitation_chance": 20, "packing": "Smart casual, cardigan or light coat"},
}

@app.post("/mcp/weather/forecast")
async def get_weather_forecast(query: WeatherQuery):
    city_key = query.destination.strip().lower()
    data = WEATHER_DATABASE.get(city_key, {
        "temp_c": 21,
        "condition": "Mild & Clear",
        "precipitation_chance": 20,
        "packing": "Standard seasonal attire and a light jacket",
    })

    forecast = []
    base_temp = data["temp_c"]
    for day in range(1, query.days + 1):
        forecast.append({
            "day": f"Day {day}",
            "high_c": base_temp + random.randint(1, 4),
            "low_c": base_temp - random.randint(2, 5),
            "condition": data["condition"],
            "precipitation": f"{data['precipitation_chance']}%",
        })

    return {
        "mcp_tool": "weather_server",
        "destination": query.destination,
        "summary": f"{data['condition']}, averaging {base_temp}°C ({int(base_temp * 9/5 + 32)}°F)",
        "packing_recommendation": data["packing"],
        "daily_forecast": forecast,
    }

@app.get("/healthz")
async def health():
    return {"status": "healthy", "service": "weather-mcp-server"}
