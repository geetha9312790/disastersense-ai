# -*- coding: utf-8 -*-
"""
DisasterSense AI - Company Disaster Chatbot
Hyper-Local Warning System for India

HOW TO RUN:
  1. pip install flask requests
  2. python disastersense_ai.py
  3. Open browser: http://localhost:5000
  4. Share with team: http://YOUR_IP:5000
"""

from flask import Flask, request, jsonify, render_template_string
import requests
import threading
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import socket
import json

app = Flask(__name__)

# ------------------------------------------------------------------
#  REAL-TIME DATA CACHE
# ------------------------------------------------------------------
disaster_cache = {
    "earthquakes": [],
    "cyclones": [],
    "floods": [],
    "weather_alerts": [],
    "last_updated": None
}

INDIA_STATES = [
    "andhra pradesh", "arunachal pradesh", "assam", "bihar", "chhattisgarh",
    "goa", "gujarat", "haryana", "himachal pradesh", "jharkhand", "karnataka",
    "kerala", "madhya pradesh", "maharashtra", "manipur", "meghalaya", "mizoram",
    "nagaland", "odisha", "punjab", "rajasthan", "sikkim", "tamil nadu",
    "telangana", "tripura", "uttar pradesh", "uttarakhand", "west bengal",
    "delhi", "mumbai", "chennai", "kolkata", "bangalore", "hyderabad",
    "pune", "ahmedabad", "jaipur", "lucknow", "surat", "salem", "coimbatore",
    "madurai", "trichy", "vizag", "visakhapatnam", "bhopal", "indore",
    "nagpur", "patna", "ranchi", "bhubaneswar", "guwahati", "kochi"
]

# ------------------------------------------------------------------
#  DATA FETCH FUNCTIONS
# ------------------------------------------------------------------

def fetch_usgs_earthquakes():
    try:
        url = "https://earthquake.usgs.gov/fdsnws/event/1/query"
        params = {
            "format": "geojson",
            "starttime": (datetime.utcnow() - timedelta(days=7)).strftime("%Y-%m-%d"),
            "minmagnitude": "3.0",
            "minlatitude": "6", "maxlatitude": "37",
            "minlongitude": "68", "maxlongitude": "98",
            "orderby": "time",
            "limit": "10"
        }
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
        quakes = []
        for feature in data.get("features", []):
            props = feature["properties"]
            coords = feature["geometry"]["coordinates"]
            mag = props.get("mag", 0)
            quakes.append({
                "magnitude": mag,
                "place": props.get("place", "Unknown location"),
                "time": datetime.utcfromtimestamp(props["time"] / 1000).strftime("%d %b %Y, %H:%M UTC"),
                "depth": coords[2],
                "lat": coords[1],
                "lon": coords[0],
                "severity": "HIGH" if mag >= 6.0 else "MODERATE" if mag >= 4.5 else "LOW"
            })
        return quakes
    except Exception as e:
        print("[USGS] Error: " + str(e))
        return []


def fetch_gdacs_alerts():
    cyclones, floods = [], []
    try:
        url = "https://www.gdacs.org/xml/rss.xml"
        resp = requests.get(url, timeout=10)
        root = ET.fromstring(resp.content)
        ns = {"gdacs": "http://www.gdacs.org"}
        for item in root.findall(".//item"):
            title = item.findtext("title", "")
            desc = item.findtext("description", "")
            pub_date = item.findtext("pubDate", "")
            country_elem = item.find("gdacs:country", ns)
            country = country_elem.text if country_elem is not None else ""
            alert_elem = item.find("gdacs:alertlevel", ns)
            alert_level = alert_elem.text if alert_elem is not None else "Green"
            event_elem = item.find("gdacs:eventtype", ns)
            event_type = event_elem.text if event_elem is not None else ""
            entry = {
                "title": title,
                "description": desc[:200] if desc else "",
                "date": pub_date,
                "country": country,
                "alert_level": alert_level
            }
            if event_type == "TC":
                cyclones.append(entry)
            elif event_type == "FL":
                floods.append(entry)
        return cyclones[:5], floods[:5]
    except Exception as e:
        print("[GDACS] Error: " + str(e))
        return [], []


def fetch_imd_weather():
    alerts = []
    try:
        url = "https://sachet.ndma.gov.in/cap_public_website/FetchAlertDashboard"
        resp = requests.get(url, timeout=10)
        data = resp.json()
        for alert in data.get("data", [])[:10]:
            alerts.append({
                "state": alert.get("state_name", "India"),
                "event": alert.get("event", "Weather Alert"),
                "severity": alert.get("severity", "Moderate"),
                "description": alert.get("description", "")[:200],
                "effective": alert.get("effective", "")
            })
    except Exception:
        pass
    if not alerts:
        try:
            url2 = "https://mausam.imd.gov.in/backend/warning.php"
            resp2 = requests.get(url2, timeout=10)
            data2 = resp2.json()
            for w in data2[:5]:
                alerts.append({
                    "state": w.get("state", "India"),
                    "event": w.get("warning_type", "Weather Warning"),
                    "severity": w.get("severity", "Moderate"),
                    "description": w.get("warning_text", "")[:200],
                    "effective": w.get("date", "")
                })
        except Exception:
            pass
    return alerts


def refresh_all_data():
    global disaster_cache
    while True:
        print("[DisasterSense] Refreshing real-time data...")
        quakes = fetch_usgs_earthquakes()
        cyclones, floods = fetch_gdacs_alerts()
        weather = fetch_imd_weather()
        disaster_cache = {
            "earthquakes": quakes,
            "cyclones": cyclones,
            "floods": floods,
            "weather_alerts": weather,
            "last_updated": datetime.now().strftime("%d %b %Y, %H:%M IST")
        }
        print("[DisasterSense] Updated: %d quakes, %d cyclones, %d floods, %d weather" % (
            len(quakes), len(cyclones), len(floods), len(weather)))
        time.sleep(600)

# ------------------------------------------------------------------
#  KNOWLEDGE BASE
# ------------------------------------------------------------------

DISASTER_KNOWLEDGE = {
    "earthquake": {
        "during": [
            "DROP to the ground immediately",
            "Take COVER under a sturdy table or desk",
            "HOLD ON until shaking stops",
            "Stay away from windows, outside walls, and anything that could fall",
            "If outdoors, move away from buildings, trees, and power lines",
            "If in a vehicle, pull over away from bridges and overpasses"
        ],
        "after": [
            "Check yourself and others for injuries",
            "Expect aftershocks - stay prepared",
            "Check for gas leaks - if detected, evacuate immediately",
            "Do NOT use elevators",
            "Inspect your building for structural damage before re-entering",
            "Call 112 if someone is injured"
        ],
        "contacts": ["112 (National Emergency)", "1070 (NDRF)", "1078 (NDMA Helpline)"]
    },
    "flood": {
        "during": [
            "Move immediately to higher ground - do NOT wait",
            "Avoid walking in moving water (even 15cm can knock you down)",
            "Do NOT drive through flooded roads",
            "If trapped, go to highest floor or rooftop and signal for help",
            "Disconnect all electrical appliances",
            "Keep emergency kit ready: water, food, medicines, documents"
        ],
        "after": [
            "Do NOT return home until authorities declare it safe",
            "Avoid floodwater - it may be contaminated",
            "Boil drinking water or use purification tablets",
            "Document damage with photos for insurance claims",
            "Watch out for snakes and insects displaced by floods"
        ],
        "contacts": ["112", "1070 (NDRF)", "State Disaster Helplines"]
    },
    "cyclone": {
        "before": [
            "Board up windows or use storm shutters",
            "Stock 3 days of food, water, and medicines",
            "Charge all devices and keep power banks ready",
            "Know your nearest cyclone shelter location",
            "Secure or bring indoors all outdoor objects",
            "Keep important documents in waterproof bags"
        ],
        "during": [
            "Stay indoors away from windows",
            "Go to the strongest part of your building",
            "Do NOT go outside during the eye of the storm - it will resume",
            "Listen to All India Radio or DD News for updates"
        ],
        "contacts": ["1070 (NDRF)", "1078 (NDMA)", "IMD Cyclone: 1800-180-1717"]
    },
    "heatwave": {
        "tips": [
            "Stay indoors between 11 AM and 4 PM",
            "Drink water every 20 minutes even if not thirsty",
            "Wear loose, light-coloured cotton clothing",
            "Use ORS (Oral Rehydration Solution) if sweating heavily",
            "Never leave children or elderly in parked vehicles",
            "Check on neighbours, especially elderly and sick",
            "Cool your body with wet cloth on neck, wrists, armpits"
        ],
        "contacts": ["108 (Ambulance)", "104 (Health Helpline)"]
    },
    "landslide": {
        "warning_signs": [
            "Cracks appearing in walls or ground",
            "Unusual sounds like cracking trees or boulders",
            "Tilting of trees or utility poles",
            "Sudden change in water flow in nearby streams",
            "Doors and windows sticking suddenly"
        ],
        "action": [
            "Evacuate immediately if you see warning signs",
            "Move to higher, stable ground away from slopes",
            "Do NOT return until geologists declare area safe",
            "Alert neighbours and local authorities immediately"
        ],
        "contacts": ["112", "1070 (NDRF)"]
    },
    "tsunami": {
        "warning_signs": [
            "Strong earthquake felt near the coast",
            "Sudden withdrawal of sea water (sea receding far back)",
            "Loud roaring sound from the ocean",
            "Unusual wave activity on the beach"
        ],
        "action": [
            "Move immediately to high ground - at least 30 metres above sea level",
            "Do NOT wait for official warning if you feel a strong quake near coast",
            "Stay away from coast until all-clear is given",
            "A tsunami is a series of waves - the first may not be the largest"
        ],
        "contacts": ["INCOIS Tsunami Warning: 040-23895000", "112"]
    }
}

GREETINGS = ["hi", "hello", "hey", "namaste", "vanakkam", "good morning",
             "good afternoon", "good evening", "start", "help"]
THANKS = ["thank", "thanks", "thank you", "dhanyawad", "nandri"]

# ------------------------------------------------------------------
#  RESPONSE ENGINE
# ------------------------------------------------------------------

def detect_location(text):
    text_lower = text.lower()
    for state in INDIA_STATES:
        if state in text_lower:
            return state.title()
    return None


def detect_disaster_type(text):
    text_lower = text.lower()
    keywords = {
        "earthquake": ["earthquake", "quake", "tremor", "seismic", "bhookamp"],
        "flood": ["flood", "flooding", "inundation", "baarish", "heavy rain", "flash flood"],
        "cyclone": ["cyclone", "hurricane", "typhoon", "storm", "toofan"],
        "heatwave": ["heat", "heatwave", "hot weather", "garmi"],
        "landslide": ["landslide", "mudslide", "bhookhalan"],
        "tsunami": ["tsunami", "tidal wave", "sea wave"]
    }
    for disaster, words in keywords.items():
        if any(w in text_lower for w in words):
            return disaster
    return None


def get_current_alerts_text(location=None):
    cache = disaster_cache
    lines = []
    if cache["last_updated"]:
        lines.append("Live data as of " + cache["last_updated"] + "\n")
    if cache["earthquakes"]:
        lines.append("RECENT EARTHQUAKES near India:")
        for q in cache["earthquakes"][:3]:
            lines.append("  [%s] M%s - %s (%s)" % (
                q["severity"], q["magnitude"], q["place"], q["time"]))
        lines.append("")
    if cache["cyclones"]:
        lines.append("ACTIVE CYCLONE ALERTS:")
        for c in cache["cyclones"][:2]:
            lines.append("  %s [%s Alert]" % (c["title"], c["alert_level"]))
        lines.append("")
    if cache["floods"]:
        lines.append("FLOOD WARNINGS:")
        for f in cache["floods"][:2]:
            lines.append("  %s [%s Alert]" % (f["title"], f["alert_level"]))
        lines.append("")
    if cache["weather_alerts"]:
        relevant = cache["weather_alerts"]
        if location:
            filtered = [w for w in cache["weather_alerts"]
                        if location.lower() in w.get("state", "").lower()]
            relevant = filtered if filtered else cache["weather_alerts"][:3]
        lines.append("IMD WEATHER WARNINGS:")
        for w in relevant[:3]:
            lines.append("  %s: %s - Severity: %s" % (w["state"], w["event"], w["severity"]))
        lines.append("")
    if not any([cache["earthquakes"], cache["cyclones"], cache["floods"], cache["weather_alerts"]]):
        lines.append("No major active disaster alerts found right now for India. Stay prepared!")
    return "\n".join(lines)


def generate_response(user_message, chat_history):
    text = user_message.strip()
    text_lower = text.lower()
    location = detect_location(text)
    disaster = detect_disaster_type(text)

    # Greeting
    if any(g in text_lower for g in GREETINGS) and len(text.split()) <= 4:
        return (
            "Welcome to DisasterSense AI\n"
            "India's Hyper-Local Disaster Warning Chatbot\n\n"
            "I provide real-time disaster alerts and safety guidance for:\n"
            "  Earthquakes | Floods | Cyclones | Heatwaves | Landslides | Tsunamis\n\n"
            "You can ask me:\n"
            "  - Are there any earthquakes near Tamil Nadu?\n"
            "  - What should I do during a flood?\n"
            "  - Show me latest disaster alerts\n"
            "  - Cyclone safety tips\n"
            "  - Emergency contacts for India\n\n"
            "Tip: Tell me your city or state for location-specific alerts!\n"
            "Data sources: USGS, GDACS, IMD, NDMA - Updated every 10 minutes"
        )

    # Thank you
    if any(t in text_lower for t in THANKS):
        return "You're welcome! Stay safe. Type 'alerts' anytime to see the latest disaster warnings."

    # Live alerts
    if any(w in text_lower for w in ["alert", "warning", "news", "update", "current",
                                      "latest", "now", "today", "live"]):
        return get_current_alerts_text(location)

    # Emergency contacts
    if any(w in text_lower for w in ["contact", "helpline", "number", "call",
                                      "phone", "emergency number"]):
        return (
            "INDIA DISASTER EMERGENCY CONTACTS\n\n"
            "  112            - National Emergency (Police/Fire/Ambulance)\n"
            "  108            - Ambulance\n"
            "  101            - Fire\n"
            "  100            - Police\n"
            "  1070           - NDRF (National Disaster Response Force)\n"
            "  1078           - NDMA Helpline\n"
            "  104            - Health Helpline\n"
            "  1800-180-1717  - IMD Cyclone Warning (Toll Free)\n"
            "  040-23895000   - INCOIS Tsunami Early Warning Centre\n\n"
            "STATE HELPLINES:\n"
            "  Tamil Nadu      : 1800-425-1213\n"
            "  Maharashtra     : 1800-22-3353\n"
            "  Kerala          : 1077\n"
            "  Odisha          : 1800-345-6789\n"
            "  Andhra Pradesh  : 1800-200-6677\n"
            "  Gujarat         : 1800-233-0222\n"
            "  Karnataka       : 1800-425-4747\n"
            "  West Bengal     : 1800-345-2999"
        )

    # Preparedness kit
    if any(w in text_lower for w in ["kit", "bag", "prepare", "pack", "stock",
                                      "ready", "checklist"]):
        return (
            "DISASTER PREPAREDNESS KIT\n\n"
            "Water and Food (3-day supply):\n"
            "  - 3 litres of water per person per day\n"
            "  - Non-perishable foods (biscuits, dry fruits, canned food)\n"
            "  - Manual can opener\n\n"
            "Medical:\n"
            "  - First aid kit with bandages and antiseptic\n"
            "  - 1-week supply of prescription medicines\n"
            "  - ORS (Oral Rehydration Salts) packets\n\n"
            "Documents (in waterproof bag):\n"
            "  - Aadhaar card, passport copies\n"
            "  - Insurance papers, bank account details\n\n"
            "Tools and Equipment:\n"
            "  - Torch with extra batteries\n"
            "  - Fully charged power bank\n"
            "  - Whistle (to signal for help)\n"
            "  - Multi-tool or Swiss knife\n\n"
            "Communication:\n"
            "  - Emergency contact list (written on paper)\n"
            "  - Battery-operated radio (for IMD/All India Radio)\n"
            "  - Charged mobile phone\n\n"
            "Review and refresh this kit every 6 months."
        )

    # Earthquake
    if disaster == "earthquake":
        info = DISASTER_KNOWLEDGE["earthquake"]
        lines = ["EARTHQUAKE SAFETY GUIDE\n"]
        quakes = disaster_cache["earthquakes"]
        if quakes:
            lines.append("Latest earthquakes near India:")
            for q in quakes[:3]:
                lines.append("  M%s - %s (%s)" % (q["magnitude"], q["place"], q["time"]))
            lines.append("")
        lines.append("During an earthquake - DROP, COVER, HOLD ON:")
        for tip in info["during"]:
            lines.append("  - " + tip)
        lines.append("\nAfter the shaking stops:")
        for tip in info["after"]:
            lines.append("  - " + tip)
        lines.append("\nEmergency: " + ", ".join(info["contacts"]))
        return "\n".join(lines)

    # Flood
    if disaster == "flood":
        info = DISASTER_KNOWLEDGE["flood"]
        lines = ["FLOOD SAFETY GUIDE\n"]
        floods = disaster_cache["floods"]
        if floods:
            lines.append("Active flood alerts:")
            for f in floods[:2]:
                lines.append("  - " + f["title"])
            lines.append("")
        lines.append("During a flood:")
        for tip in info["during"]:
            lines.append("  - " + tip)
        lines.append("\nAfter the flood:")
        for tip in info["after"]:
            lines.append("  - " + tip)
        lines.append("\nEmergency: " + ", ".join(info["contacts"]))
        return "\n".join(lines)

    # Cyclone
    if disaster == "cyclone":
        info = DISASTER_KNOWLEDGE["cyclone"]
        lines = ["CYCLONE SAFETY GUIDE\n"]
        cyclones = disaster_cache["cyclones"]
        if cyclones:
            lines.append("Active cyclone alerts:")
            for c in cyclones[:2]:
                lines.append("  - %s [%s Alert]" % (c["title"], c["alert_level"]))
            lines.append("")
        lines.append("Before the cyclone:")
        for tip in info["before"]:
            lines.append("  - " + tip)
        lines.append("\nDuring the cyclone:")
        for tip in info["during"]:
            lines.append("  - " + tip)
        lines.append("\nEmergency: " + ", ".join(info["contacts"]))
        return "\n".join(lines)

    # Heatwave
    if disaster == "heatwave":
        info = DISASTER_KNOWLEDGE["heatwave"]
        lines = ["HEATWAVE SAFETY GUIDE\n", "Stay safe in extreme heat:"]
        for tip in info["tips"]:
            lines.append("  - " + tip)
        lines.append("\nEmergency: " + ", ".join(info["contacts"]))
        return "\n".join(lines)

    # Landslide
    if disaster == "landslide":
        info = DISASTER_KNOWLEDGE["landslide"]
        lines = ["LANDSLIDE SAFETY GUIDE\n", "Warning signs - evacuate if you see these:"]
        for sign in info["warning_signs"]:
            lines.append("  - " + sign)
        lines.append("\nWhat to do:")
        for tip in info["action"]:
            lines.append("  - " + tip)
        lines.append("\nEmergency: " + ", ".join(info["contacts"]))
        return "\n".join(lines)

    # Tsunami
    if disaster == "tsunami":
        info = DISASTER_KNOWLEDGE["tsunami"]
        lines = ["TSUNAMI SAFETY GUIDE\n", "Warning signs:"]
        for sign in info["warning_signs"]:
            lines.append("  - " + sign)
        lines.append("\nImmediate actions:")
        for tip in info["action"]:
            lines.append("  - " + tip)
        lines.append("\nEmergency: " + ", ".join(info["contacts"]))
        return "\n".join(lines)

    # Location only
    if location and not disaster:
        return (
            "Disaster Status for " + location + ":\n\n" +
            get_current_alerts_text(location) +
            "\n\nAsk me: 'flood safety in " + location + "' or 'earthquake tips'"
        )

    # About
    if any(w in text_lower for w in ["what are you", "who are you", "about", "introduce"]):
        return (
            "About DisasterSense AI\n\n"
            "I am a Hyper-Local Disaster Warning Chatbot built for India.\n\n"
            "What I do:\n"
            "  - Monitor real-time feeds: USGS, GDACS, IMD, NDMA\n"
            "  - Location-specific alerts for any Indian city or state\n"
            "  - Step-by-step safety instructions for every disaster type\n"
            "  - Verified emergency helpline numbers\n"
            "  - Disaster preparedness guidance\n\n"
            "Data updated every 10 minutes. Coverage: All of India.\n"
            "Type 'alerts' to see current warnings!"
        )

    # Default
    return (
        "I'm here to help with disaster safety!\n\n"
        "Try asking:\n"
        "  'Show latest alerts'           - real-time disaster warnings\n"
        "  'Earthquake safety tips'       - what to do during earthquakes\n"
        "  'Flood warnings in Tamil Nadu' - location-specific alerts\n"
        "  'Cyclone preparedness'         - how to prepare for cyclones\n"
        "  'Emergency contacts'           - helpline numbers\n"
        "  'Preparedness kit'             - what to keep ready at home\n\n"
        "Or just type your city or state name for local alerts!"
    )

# ------------------------------------------------------------------
#  HTML FRONTEND
# ------------------------------------------------------------------

HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>DisasterSense AI - India Disaster Warning</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
*{margin:0;padding:0;box-sizing:border-box;}
body{font-family:'Inter',sans-serif;background:#0d1117;color:#e6edf3;height:100vh;display:flex;flex-direction:column;}
.header{background:#161b22;border-bottom:1px solid #30363d;padding:14px 24px;display:flex;align-items:center;justify-content:space-between;flex-shrink:0;}
.header-left{display:flex;align-items:center;gap:12px;}
.logo-icon{width:38px;height:38px;background:linear-gradient(135deg,#ff4d1c,#ff8c00);border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:20px;}
.logo-title{font-size:18px;font-weight:700;}.logo-title span{color:#ff6b35;}
.logo-sub{font-size:11px;color:#8b949e;margin-top:1px;}
.status-badge{display:flex;align-items:center;gap:6px;background:rgba(0,230,160,0.1);border:1px solid rgba(0,230,160,0.3);padding:5px 12px;border-radius:20px;font-size:12px;color:#00e6a0;}
.dot{width:7px;height:7px;border-radius:50%;background:#00e6a0;animation:blink 2s infinite;}
@keyframes blink{0%,100%{opacity:1}50%{opacity:0.3}}
.ticker{background:#1a0a00;border-bottom:1px solid rgba(255,77,28,0.2);padding:7px 24px;font-size:12px;color:#ff9966;display:flex;align-items:center;gap:10px;flex-shrink:0;overflow:hidden;}
.ticker-label{background:#ff4d1c;color:#fff;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600;flex-shrink:0;}
.ticker-text{white-space:nowrap;animation:scroll 35s linear infinite;}
@keyframes scroll{0%{transform:translateX(100%)}100%{transform:translateX(-100%)}}
.chat-container{flex:1;overflow-y:auto;padding:20px 16px;display:flex;flex-direction:column;gap:16px;}
.chat-container::-webkit-scrollbar{width:6px;}
.chat-container::-webkit-scrollbar-track{background:#0d1117;}
.chat-container::-webkit-scrollbar-thumb{background:#30363d;border-radius:3px;}
.msg{display:flex;gap:10px;max-width:800px;animation:fadeIn 0.3s ease;}
@keyframes fadeIn{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}
.msg.user{align-self:flex-end;flex-direction:row-reverse;}
.msg-avatar{width:34px;height:34px;border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:16px;flex-shrink:0;}
.bot-avatar{background:linear-gradient(135deg,#ff4d1c,#ff8c00);}
.user-avatar{background:linear-gradient(135deg,#1f6feb,#388bfd);}
.msg-bubble{padding:12px 16px;border-radius:12px;font-size:14px;line-height:1.7;max-width:680px;white-space:pre-wrap;word-wrap:break-word;}
.bot-bubble{background:#161b22;border:1px solid #30363d;border-radius:4px 12px 12px 12px;}
.user-bubble{background:#1f6feb;border-radius:12px 4px 12px 12px;color:#fff;}
.typing{display:flex;align-items:center;gap:5px;padding:14px 16px;background:#161b22;border:1px solid #30363d;border-radius:4px 12px 12px 12px;width:fit-content;}
.typing span{width:7px;height:7px;background:#8b949e;border-radius:50%;animation:bounce 1.2s infinite;}
.typing span:nth-child(2){animation-delay:.2s;}.typing span:nth-child(3){animation-delay:.4s;}
@keyframes bounce{0%,60%,100%{transform:translateY(0)}30%{transform:translateY(-6px)}}
.quick-btns{display:flex;flex-wrap:wrap;gap:8px;padding:0 16px 8px;flex-shrink:0;}
.quick-btn{background:#161b22;border:1px solid #30363d;color:#8b949e;padding:6px 14px;border-radius:20px;font-size:12px;cursor:pointer;transition:all 0.2s;font-family:inherit;}
.quick-btn:hover{background:#21262d;border-color:#ff6b35;color:#ff9966;}
.input-area{background:#161b22;border-top:1px solid #30363d;padding:16px;display:flex;gap:10px;flex-shrink:0;align-items:flex-end;}
.input-wrap{flex:1;background:#0d1117;border:1px solid #30363d;border-radius:10px;display:flex;align-items:center;transition:border-color 0.2s;}
.input-wrap:focus-within{border-color:#ff6b35;}
#user-input{flex:1;background:transparent;border:none;outline:none;color:#e6edf3;padding:12px 16px;font-size:14px;font-family:inherit;resize:none;max-height:120px;}
#user-input::placeholder{color:#484f58;}
.send-btn{background:linear-gradient(135deg,#ff4d1c,#ff8c00);border:none;color:#fff;width:42px;height:42px;border-radius:8px;cursor:pointer;font-size:16px;display:flex;align-items:center;justify-content:center;transition:opacity 0.2s;flex-shrink:0;font-weight:bold;}
.send-btn:hover{opacity:0.85;}.send-btn:active{opacity:0.7;}
.footer{text-align:center;padding:6px;font-size:11px;color:#484f58;flex-shrink:0;}
</style>
</head>
<body>
<div class="header">
  <div class="header-left">
    <div class="logo-icon">&#128680;</div>
    <div>
      <div class="logo-title">Disaster<span>Sense</span> AI</div>
      <div class="logo-sub">India Hyper-Local Disaster Warning System</div>
    </div>
  </div>
  <div class="status-badge"><div class="dot"></div>Live Monitoring</div>
</div>
<div class="ticker">
  <span class="ticker-label">LIVE</span>
  <span class="ticker-text" id="ticker-text">Loading real-time disaster data from USGS, GDACS, IMD, NDMA...</span>
</div>
<div class="chat-container" id="chat">
  <div class="msg">
    <div class="msg-avatar bot-avatar">&#128680;</div>
    <div class="msg-bubble bot-bubble">Welcome to DisasterSense AI &#127470;&#127475;

I monitor real-time disaster data across India and provide instant safety guidance.

Data Sources: USGS Earthquakes | GDACS | IMD | NDMA
Updated every 10 minutes automatically

Ask me about current alerts, safety tips, or tell me your city for local warnings!</div>
  </div>
</div>
<div class="quick-btns">
  <button class="quick-btn" onclick="sendQuick('Show latest disaster alerts')">&#128225; Live Alerts</button>
  <button class="quick-btn" onclick="sendQuick('Earthquake safety tips')">&#128308; Earthquake</button>
  <button class="quick-btn" onclick="sendQuick('Flood safety guide')">&#127754; Flood</button>
  <button class="quick-btn" onclick="sendQuick('Cyclone preparedness')">&#127744; Cyclone</button>
  <button class="quick-btn" onclick="sendQuick('Heatwave safety')">&#127777; Heatwave</button>
  <button class="quick-btn" onclick="sendQuick('Emergency contacts India')">&#128222; Helplines</button>
  <button class="quick-btn" onclick="sendQuick('Preparedness kit checklist')">&#127890; Kit</button>
</div>
<div class="input-area">
  <div class="input-wrap">
    <textarea id="user-input" placeholder="Ask about disasters, safety tips, or type your city..." rows="1"
      onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();sendMsg();}"
      oninput="this.style.height='auto';this.style.height=this.scrollHeight+'px';"></textarea>
  </div>
  <button class="send-btn" onclick="sendMsg()">Send</button>
</div>
<div class="footer">DisasterSense AI | Real-time: USGS, GDACS, IMD, NDMA | Emergency: 112</div>
<script>
var chat=document.getElementById('chat');
var chatHistory=[];
function addMsg(text,role){
  var wrap=document.createElement('div');
  wrap.className='msg'+(role==='user'?' user':'');
  var av=document.createElement('div');
  av.className='msg-avatar '+(role==='user'?'user-avatar':'bot-avatar');
  av.innerHTML=(role==='user'?'&#128100;':'&#128680;');
  var bubble=document.createElement('div');
  bubble.className='msg-bubble '+(role==='user'?'user-bubble':'bot-bubble');
  bubble.textContent=text;
  wrap.appendChild(av);
  wrap.appendChild(bubble);
  chat.appendChild(wrap);
  chat.scrollTop=chat.scrollHeight;
}
function showTyping(){
  var wrap=document.createElement('div');
  wrap.className='msg';wrap.id='typing';
  wrap.innerHTML='<div class="msg-avatar bot-avatar">&#128680;</div><div class="typing"><span></span><span></span><span></span></div>';
  chat.appendChild(wrap);chat.scrollTop=chat.scrollHeight;
}
function removeTyping(){var t=document.getElementById('typing');if(t)t.remove();}
async function sendMsg(){
  var input=document.getElementById('user-input');
  var text=input.value.trim();if(!text)return;
  input.value='';input.style.height='auto';
  addMsg(text,'user');
  chatHistory.push({role:'user',content:text});
  showTyping();
  try{
    var resp=await fetch('/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:text,history:chatHistory})});
    var data=await resp.json();
    removeTyping();addMsg(data.reply,'bot');
    chatHistory.push({role:'assistant',content:data.reply});
  }catch(e){
    removeTyping();addMsg('Connection error. Please check your internet and try again.','bot');
  }
}
function sendQuick(text){document.getElementById('user-input').value=text;sendMsg();}
async function loadTicker(){
  try{
    var resp=await fetch('/alerts_summary');
    var data=await resp.json();
    document.getElementById('ticker-text').textContent=data.summary;
  }catch(e){}
}
loadTicker();setInterval(loadTicker,300000);
</script>
</body>
</html>"""

# ------------------------------------------------------------------
#  FLASK ROUTES
# ------------------------------------------------------------------

@app.route("/")
def index():
    return render_template_string(HTML_PAGE)


@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    user_msg = data.get("message", "")
    history = data.get("history", [])
    reply = generate_response(user_msg, history)
    return jsonify({"reply": reply})


@app.route("/alerts_summary")
def alerts_summary():
    cache = disaster_cache
    parts = []
    if cache["earthquakes"]:
        q = cache["earthquakes"][0]
        parts.append("M%s Earthquake: %s" % (q["magnitude"], q["place"]))
    if cache["cyclones"]:
        parts.append("Cyclone Alert: " + cache["cyclones"][0]["title"])
    if cache["floods"]:
        parts.append("Flood Alert: " + cache["floods"][0]["title"])
    if cache["weather_alerts"]:
        w = cache["weather_alerts"][0]
        parts.append("IMD: %s - %s" % (w["state"], w["event"]))
    if not parts:
        parts = ["No major active alerts right now - Stay Prepared"]
    parts.append("Last updated: " + (cache["last_updated"] or "Loading..."))
    return jsonify({"summary": "  |  ".join(parts)})


@app.route("/health")
def health():
    return jsonify({
        "status": "running",
        "last_updated": disaster_cache["last_updated"],
        "earthquakes": len(disaster_cache["earthquakes"]),
        "cyclones": len(disaster_cache["cyclones"]),
        "floods": len(disaster_cache["floods"]),
        "weather_alerts": len(disaster_cache["weather_alerts"])
    })

# ------------------------------------------------------------------
#  STARTUP
# ------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("  DisasterSense AI - Starting Up")
    print("=" * 60)
    print("  Fetching initial real-time data...")

    quakes = fetch_usgs_earthquakes()
    cyclones, floods = fetch_gdacs_alerts()
    weather = fetch_imd_weather()
    disaster_cache.update({
        "earthquakes": quakes,
        "cyclones": cyclones,
        "floods": floods,
        "weather_alerts": weather,
        "last_updated": datetime.now().strftime("%d %b %Y, %H:%M IST")
    })
    print("  Loaded: %d earthquakes, %d cyclones, %d floods, %d weather alerts" % (
        len(quakes), len(cyclones), len(floods), len(weather)))

    bg = threading.Thread(target=refresh_all_data, daemon=True)
    bg.start()
    print("  Background refresh started (every 10 minutes)")
    print()
    print("  Open your browser:")
    print("  -->  http://localhost:5000")
    print()
    try:
        local_ip = socket.gethostbyname(socket.gethostname())
        print("  Share with your team (same network):")
        print("  -->  http://" + local_ip + ":5000")
    except Exception:
        pass
    print()
    print("  Press CTRL+C to stop the server")
    print("=" * 60)

    app.run(host="0.0.0.0", port=5000, debug=False)
