import os
import json
import re
import urllib.parse
from typing import Dict, Any, Optional, Union
from PIL import Image
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

# Configure API Key
API_KEY = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")

if API_KEY:
    try:
        genai.configure(api_key=API_KEY)
    except Exception as e:
        print(f"Warning: Failed to configure Gemini API: {e}")

_cfg_model = os.getenv("GEMINI_MODEL", "gemini-1.5-pro")
PREFERRED_MODELS = [_cfg_model]
for _fallback in ["gemini-1.5-pro", "gemini-2.5-flash", "gemini-flash-latest"]:
    if _fallback not in PREFERRED_MODELS:
        PREFERRED_MODELS.append(_fallback)

def get_gemini_model():
    """Returns a configured Gemini GenerativeModel instance if available"""
    if not API_KEY:
        return None
    for model_name in PREFERRED_MODELS:
        try:
            return genai.GenerativeModel(model_name)
        except Exception:
            continue
    return None

def generate_ai_content(contents) -> Optional[str]:
    """
    Attempts content generation using Gemini models starting with Gemini 1.5 Pro.
    Automatically handles model fallback if a specific model version is unavailable.
    """
    if not API_KEY:
        return None
    for model_name in PREFERRED_MODELS:
        try:
            model = genai.GenerativeModel(model_name)
            resp = model.generate_content(contents)
            if resp and resp.text:
                return resp.text
        except Exception:
            continue
    return None

def extract_json_from_response(text: str) -> dict:
    """Extract and parse JSON object from Gemini response string"""
    try:
        # Check for markdown code blocks ```json ... ```
        json_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
        if json_match:
            clean_text = json_match.group(1).strip()
            return json.loads(clean_text)
        
        # Check for first { to last }
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            clean_text = text[start:end+1].strip()
            return json.loads(clean_text)
            
        return json.loads(text.strip())
    except Exception as e:
        print(f"JSON parsing error: {e}, raw text snippet: {text[:200]}")
        raise ValueError(f"Could not parse valid JSON from AI response: {str(e)}")

def usd_to_inr(amount_usd: float, exchange_rate: float = 83.0) -> float:
    """Convert USD amount to INR using standard conversion rate"""
    return amount_usd * exchange_rate

# ==================== HOME INTERIOR RECOMMENDATIONS ====================

def get_home_recommendations(budget_input) -> dict:
    """
    Generate home interior recommendations within budget in INR for Indian market.
    Supports Gemini Generative AI with resilient fallback budgeting.
    """
    total_budget = float(budget_input.total_budget)
    model = get_gemini_model()

    if model:
        try:
            prompt = f"""
I need interior design product recommendations for a home in India with a total budget of ₹{total_budget:.2f}.
Requirements:
- {budget_input.num_lights} lights/lighting fixtures
- {budget_input.num_fans} ceiling fans
- {budget_input.num_furniture} furniture pieces
- {budget_input.num_dining_tables} dining tables

Additional rooms to consider:
{("- Living room" if getattr(budget_input, 'has_living_room', False) else "")}
{("- Kitchen" if getattr(budget_input, 'has_kitchen', False) else "")}
{("- Bedroom" if getattr(budget_input, 'has_bedroom', False) else "")}

Additional requirements: {budget_input.additional_requirements or "None"}

Please provide a detailed budget breakdown with product recommendations available in India.
Use Indian brands (e.g., Philips, Havells, Godrej Interio, Wakefit, Nilkamal) and pricing in INR.
Ensure total costs stay within the total budget of ₹{total_budget:.2f}.
Include specific search terms suitable for Indian shopping websites like Flipkart, Amazon India, IKEA India, Myntra, and Ajio.

Format your response ONLY as JSON with the following structure:
{{
    "total_budget": {total_budget:.2f},
    "remaining_budget": 0.0,
    "budget_breakdown": [
        {{
            "category": "Lighting",
            "allocation": 0.0,
            "items": [
                {{
                    "name": "Philips LED Smart Bulb",
                    "description": "Energy efficient warm white light",
                    "estimated_price": 500.0,
                    "quantity": 2,
                    "search_terms": "Philips warm white led bulb"
                }}
            ]
        }}
    ],
    "additional_suggestions": [
        "Consider purchasing energy-efficient 5-star rated appliances",
        "Opt for modular furniture that offers multi-purpose storage"
    ]
}}
"""
            response_text = generate_ai_content(prompt)
            if not response_text:
                raise ValueError("Could not obtain response from Gemini models")
            result = extract_json_from_response(response_text)
            
            # Attach shopping links
            for category in result.get("budget_breakdown", []):
                for item in category.get("items", []):
                    search_terms = item.get("search_terms") or item.get("name", "")
                    if search_terms:
                        encoded = urllib.parse.quote_plus(search_terms)
                        item["shopping_links"] = {
                            "amazon": f"https://www.amazon.in/s?k={encoded}",
                            "flipkart": f"https://www.flipkart.com/search?q={encoded}",
                            "ikea": f"https://www.ikea.com/in/en/search/?q={encoded}",
                            "myntra": f"https://www.myntra.com/search?q={encoded}",
                            "ajio": f"https://www.ajio.com/search/?text={encoded}"
                        }
            result["engine"] = "gemini-live"
            return result
        except Exception as e:
            print(f"Gemini AI home generation notice (using smart fallback): {e}")

    # SMART BUDGET FALLBACK ENGINE (Matches documentation screenshots)
    return generate_fallback_home_recommendations(budget_input)

def generate_fallback_home_recommendations(budget_input) -> dict:
    total = float(budget_input.total_budget)
    num_lights = max(1, budget_input.num_lights) if budget_input.num_lights > 0 else 4
    num_fans = max(1, budget_input.num_fans) if budget_input.num_fans > 0 else 2
    num_furniture = max(1, budget_input.num_furniture) if budget_input.num_furniture > 0 else 2
    num_dining = budget_input.num_dining_tables if budget_input.num_dining_tables > 0 else 0

    alloc_lighting = round(total * 0.25, 2)
    alloc_fans = round(total * 0.25, 2)
    alloc_furniture = round(total * 0.40, 2)
    spent = alloc_lighting + alloc_fans + alloc_furniture
    remaining = max(0.0, round(total - spent, 2))

    breakdown = [
        {
            "category": "Lighting",
            "allocation": alloc_lighting,
            "items": [
                {
                    "name": "Wipro / Philips LED Warm White Bulb Set",
                    "description": "Energy-efficient 9W LED bulbs with glare-free illumination for living spaces.",
                    "estimated_price": round(alloc_lighting / num_lights, 2),
                    "quantity": num_lights,
                    "search_terms": "Philips 9W warm white led bulb pack",
                    "shopping_links": {}
                }
            ]
        },
        {
            "category": "Ceiling_fans",
            "allocation": alloc_fans,
            "items": [
                {
                    "name": "Havells / Crompton High-Speed Ceiling Fan",
                    "description": "Energy-saving BLDC / high-airflow 1200mm ceiling fan with silent operation.",
                    "estimated_price": round(alloc_fans / num_fans, 2),
                    "quantity": num_fans,
                    "search_terms": "Havells 1200mm ceiling fan",
                    "shopping_links": {}
                }
            ]
        },
        {
            "category": "Furniture",
            "allocation": alloc_furniture,
            "items": [
                {
                    "name": "Nilkamal Ergonomic Accent Chair Set",
                    "description": "Durable, stylish stackable comfort chairs suitable for living or balcony decor.",
                    "estimated_price": round((alloc_furniture * 0.4) / num_furniture, 2),
                    "quantity": num_furniture,
                    "search_terms": "Nilkamal modern lounge chair",
                    "shopping_links": {}
                },
                {
                    "name": "Wakefit Engineered Wood Coffee & Dining Table",
                    "description": "Contemporary compact wooden table with clean finish for dining or multi-utility.",
                    "estimated_price": round(alloc_furniture * 0.6, 2),
                    "quantity": 1 if num_dining == 0 else num_dining,
                    "search_terms": "Wakefit compact dining table wooden",
                    "shopping_links": {}
                }
            ]
        }
    ]

    for cat in breakdown:
        for itm in cat["items"]:
            encoded = urllib.parse.quote_plus(itm["search_terms"])
            itm["shopping_links"] = {
                "amazon": f"https://www.amazon.in/s?k={encoded}",
                "flipkart": f"https://www.flipkart.com/search?q={encoded}",
                "ikea": f"https://www.ikea.com/in/en/search/?q={encoded}",
                "myntra": f"https://www.myntra.com/search?q={encoded}",
                "ajio": f"https://www.ajio.com/search/?text={encoded}"
            }

    return {
        "total_budget": total,
        "remaining_budget": remaining,
        "budget_breakdown": breakdown,
        "additional_suggestions": [
            "Consider purchasing energy-efficient BLDC fans for long-term power bill savings.",
            "Look for festive discounts and bundle deals on Amazon India and Flipkart.",
            "Prioritize foundational lighting fixtures before adding ambient accent lamps."
        ],
        "engine": "smart-budget-engine"
    }

# ==================== PARTY BUDGET RECOMMENDATIONS ====================

def get_party_recommendations(budget_input) -> dict:
    """
    Generate party planning recommendations within budget in INR for Indian market.
    """
    total_budget = float(budget_input.total_budget)
    model = get_gemini_model()

    if model:
        try:
            prompt = f"""
I need party planning recommendations for India with a total budget of ₹{total_budget:.2f}.
Party details:
- Type: {budget_input.party_type}
- Number of guests: {budget_input.num_guests}
- Venue type: {budget_input.venue_type or "Not specified"}
- Catering needed: {"Yes" if budget_input.needs_catering else "No"}
- Decoration needed: {"Yes" if budget_input.needs_decoration else "No"}
- Entertainment needed: {"Yes" if budget_input.needs_entertainment else "No"}
Additional requirements: {budget_input.additional_requirements or "None"}

Please provide a detailed budget breakdown with specific recommendations available in India using INR prices.
Use Indian brands, services, catering styles, and typical cost expectations.
Ensure all costs are in INR and total does not exceed the given budget.
Provide search terms suitable for Indian websites such as BookMyShow, Swiggy, Zomato, OYORooms, MakeMyTrip, and Flipkart.

Format your response ONLY as JSON with the following structure:
{{
    "total_budget": {total_budget:.2f},
    "remaining_budget": 0.0,
    "budget_breakdown": [
        {{
            "category": "Venue",
            "allocation": 0.0,
            "items": [
                {{
                    "name": "Cozy Community Hall / Home Venue",
                    "description": "Spacious setup suitable for guests",
                    "estimated_price": 0.0,
                    "quantity": 1,
                    "search_terms": "party halls in my area"
                }}
            ]
        }},
        {{
            "category": "Catering",
            "allocation": 0.0,
            "items": [
                {{
                    "name": "Buffet & Snacks Catering",
                    "description": "Starters, main course, and dessert",
                    "estimated_price": 0.0,
                    "quantity": {budget_input.num_guests},
                    "search_terms": "party bulk catering orders"
                }}
            ]
        }}
    ],
    "venue_suggestions": [
        {{
            "name": "Local Banquet & Party Space",
            "type": "{budget_input.venue_type or 'Banquet'}",
            "capacity": {budget_input.num_guests},
            "estimated_cost": 0.0,
            "search_terms": "banquet party halls booking"
        }}
    ],
    "additional_suggestions": [
        "Order catering platters or party boxes through Swiggy/Zomato for discounted group rates.",
        "Use DIY balloon garlands and warm LED fairy lights for low-cost aesthetic decor."
    ]
}}
"""
            response_text = generate_ai_content(prompt)
            if not response_text:
                raise ValueError("Could not obtain response from Gemini models")
            result = extract_json_from_response(response_text)
            
            # Enrich venue suggestions with booking links
            venue_platforms = ["google", "booking", "makemytrip", "oyorooms", "nobroker"]
            for venue in result.get("venue_suggestions", []):
                st = venue.get("search_terms") or venue.get("name", "party venue")
                enc = urllib.parse.quote_plus(st)
                venue["search_links"] = {
                    "google": f"https://www.google.com/search?q={enc}",
                    "booking": f"https://www.booking.com/search.html?ss={enc}",
                    "makemytrip": f"https://www.makemytrip.com/hotels/hotel-listing/?searchText={enc}",
                    "oyorooms": f"https://www.oyorooms.com/search/?location={enc}",
                    "nobroker": f"https://www.nobroker.in/property/search?searchTerm={enc}"
                }
                
            # Add shopping links to items
            for cat in result.get("budget_breakdown", []):
                for item in cat.get("items", []):
                    st = item.get("search_terms") or item.get("name", "")
                    enc = urllib.parse.quote_plus(st)
                    cat_name = cat.get("category", "").lower()
                    if "cater" in cat_name or "food" in cat_name:
                        item["shopping_links"] = {
                            "swiggy": f"https://www.swiggy.com/search?query={enc}",
                            "zomato": f"https://www.zomato.com/search?q={enc}"
                        }
                    elif "venue" in cat_name:
                        item["shopping_links"] = {
                            "google": f"https://www.google.com/search?q={enc}",
                            "booking": f"https://www.booking.com/search.html?ss={enc}",
                            "makemytrip": f"https://www.makemytrip.com/hotels/hotel-listing/?searchText={enc}",
                            "oyorooms": f"https://www.oyorooms.com/search/?location={enc}",
                            "nobroker": f"https://www.nobroker.in/property/search?searchTerm={enc}"
                        }
                    else:
                        item["shopping_links"] = {
                            "amazon": f"https://www.amazon.in/s?k={enc}",
                            "flipkart": f"https://www.flipkart.com/search?q={enc}",
                            "bookmyshow": f"https://in.bookmyshow.com/explore/home?search={enc}"
                        }
            result["engine"] = "gemini-live"
            return result
        except Exception as e:
            print(f"Gemini AI party generation notice (using smart fallback): {e}")

    return generate_fallback_party_recommendations(budget_input)

def generate_fallback_party_recommendations(budget_input) -> dict:
    total = float(budget_input.total_budget)
    guests = max(1, budget_input.num_guests)
    party_type = budget_input.party_type or "Celebration"
    venue_type = budget_input.venue_type or "Home"

    # Allocations
    venue_cost = 0.0 if venue_type.lower() == "home" else round(total * 0.20, 2)
    catering_cost = round(total * 0.40, 2) if budget_input.needs_catering else 0.0
    decor_cost = round(total * 0.15, 2) if budget_input.needs_decoration else 0.0
    entertainment_cost = round(total * 0.15, 2) if budget_input.needs_entertainment else 0.0
    contingency = max(0.0, round(total * 0.10, 2))
    
    total_spent = venue_cost + catering_cost + decor_cost + entertainment_cost + contingency
    remaining = max(0.0, round(total - total_spent, 2))

    breakdown = []
    
    # Venue Category
    breakdown.append({
        "category": "Venue",
        "allocation": venue_cost,
        "items": [
            {
                "name": f"{venue_type} Venue Setup",
                "description": f"Utilizing {venue_type} space with clean arrangement for {guests} guests.",
                "estimated_price": venue_cost,
                "quantity": 1,
                "search_terms": f"event venue hall booking for {guests} people",
                "shopping_links": {
                    "google": f"https://www.google.com/search?q={urllib.parse.quote_plus(f'{venue_type} event booking')}",
                    "booking": f"https://www.booking.com/search.html?ss={urllib.parse.quote_plus('party banquet hall')}",
                    "makemytrip": f"https://www.makemytrip.com/hotels/hotel-listing/?searchText={urllib.parse.quote_plus('event hotel')}",
                    "oyorooms": f"https://www.oyorooms.com/search/?location={urllib.parse.quote_plus('party rooms')}",
                    "nobroker": f"https://www.nobroker.in/property/search?searchTerm={urllib.parse.quote_plus('community hall')}"
                }
            }
        ]
    })

    # Catering Category
    if budget_input.needs_catering:
        breakdown.append({
            "category": "Catering",
            "allocation": catering_cost,
            "items": [
                {
                    "name": "Party Platters, Snacks & Beverages",
                    "description": f"Curated appetizers, main dishes, and cool refreshments for {guests} guests.",
                    "estimated_price": catering_cost,
                    "quantity": guests,
                    "search_terms": f"{party_type} party bulk meal platters",
                    "shopping_links": {
                        "swiggy": f"https://www.swiggy.com/search?query={urllib.parse.quote_plus('party bulk food catering')}",
                        "zomato": f"https://www.zomato.com/search?q={urllib.parse.quote_plus('party bulk food catering')}"
                    }
                }
            ]
        })

    # Entertainment Category
    if budget_input.needs_entertainment:
        breakdown.append({
            "category": "Entertainment",
            "allocation": entertainment_cost,
            "items": [
                {
                    "name": "Party Games & Premium Audio Playlist",
                    "description": "Party board games, karaoke setup, and interactive celebration activities.",
                    "estimated_price": entertainment_cost,
                    "quantity": 1,
                    "search_terms": "party board games and music soundbox",
                    "shopping_links": {
                        "amazon": f"https://www.amazon.in/s?k={urllib.parse.quote_plus('party board games')}",
                        "flipkart": f"https://www.flipkart.com/search?q={urllib.parse.quote_plus('party soundbox bluetooth')}",
                        "bookmyshow": f"https://in.bookmyshow.com/explore/home?search={urllib.parse.quote_plus('events activities')}"
                    }
                }
            ]
        })

    # Contingency
    breakdown.append({
        "category": "Contingency",
        "allocation": contingency,
        "items": [
            {
                "name": "Unexpected & Miscellaneous Expenses",
                "description": "Buffer reserve for last-minute supplies, extra ice, or emergency items.",
                "estimated_price": contingency,
                "quantity": 1,
                "search_terms": "party emergency disposable tableware kit",
                "shopping_links": {
                    "amazon": f"https://www.amazon.in/s?k={urllib.parse.quote_plus('party disposable tableware kit')}",
                    "flipkart": f"https://www.flipkart.com/search?q={urllib.parse.quote_plus('party supplies kit')}",
                    "google": f"https://www.google.com/search?q={urllib.parse.quote_plus('party supplies near me')}"
                }
            }
        ]
    })

    venue_sugg = [
        {
            "name": f"{venue_type} Event Space",
            "type": venue_type,
            "capacity": guests,
            "estimated_cost": venue_cost,
            "search_terms": f"{venue_type} party venue",
            "search_links": {
                "google": f"https://www.google.com/search?q={urllib.parse.quote_plus(f'{venue_type} party hall')}",
                "booking": f"https://www.booking.com/search.html?ss={urllib.parse.quote_plus('party banquet hall')}",
                "makemytrip": f"https://www.makemytrip.com/hotels/hotel-listing/?searchText={urllib.parse.quote_plus('party hotels')}",
                "oyorooms": f"https://www.oyorooms.com/search/?location={urllib.parse.quote_plus('party rooms')}",
                "nobroker": f"https://www.nobroker.in/property/search?searchTerm={urllib.parse.quote_plus('party space rental')}"
            }
        }
    ]

    return {
        "total_budget": total,
        "remaining_budget": remaining,
        "budget_breakdown": breakdown,
        "venue_suggestions": venue_sugg,
        "additional_suggestions": [
            "Consider making the meal a potluck style if comfortable with guests to reduce catering costs.",
            "Look for party bundle discounts or combo deals on food delivery platforms.",
            "Homemade decorations with paper crafts and fairy lights can be highly cost-effective and charming."
        ],
        "engine": "smart-budget-engine"
    }

# ==================== JEWELRY BUDGET RECOMMENDATIONS ====================

def get_jewelry_recommendations(budget_input, image_path: Optional[str] = None) -> dict:
    """
    Generate jewelry recommendations based on optional uploaded dress image and budget in INR.
    """
    total_budget = float(budget_input.total_budget)
    model = get_gemini_model()

    if model:
        try:
            base_prompt = f"""
I need jewelry recommendations for India with a total budget of ₹{total_budget:.2f}.
Occasion: {budget_input.occasion}
Preferences: {budget_input.style_preferences or getattr(budget_input, 'preferences', None) or "Not specified"}
Provide only India-relevant styles, availability, and price ranges in INR.
"""
            if image_path and os.path.exists(image_path):
                img = Image.open(image_path)
                prompt = base_prompt + f"""
An image of the outfit is uploaded. Carefully analyze the outfit's colors, neckline, styling, and formality.
Suggest jewelry that complements it perfectly.

Format the output strictly as JSON with this schema:
{{
    "outfit_analysis": {{
        "colors": ["royal blue", "gold embroidery"],
        "style": "Traditional Festive",
        "formality": "Formal"
    }},
    "total_budget": {total_budget:.2f},
    "remaining_budget": 0.0,
    "jewelry_recommendations": [
        {{
            "item_type": "Necklace / Choker",
            "description": "Kundan antique choker set matching the neckline",
            "style": "Traditional",
            "estimated_price": 0.0,
            "search_terms": "kundan choker necklace set"
        }}
    ],
    "styling_tips": [
        "Pair with matching jhumkas to elevate the traditional appeal",
        "Keep bangles subtle if the necklace is heavily detailed"
    ]
}}
"""
                response_text = generate_ai_content([prompt, img])
            else:
                prompt = base_prompt + f"""
Format the output strictly as JSON with this schema:
{{
    "outfit_analysis": {{
        "colors": ["classic neutral"],
        "style": "Contemporary",
        "formality": "Semi-formal"
    }},
    "total_budget": {total_budget:.2f},
    "remaining_budget": 0.0,
    "jewelry_recommendations": [
        {{
            "item_type": "Bracelet / Bangle",
            "description": "Minimalist silver or rose gold sleek bracelet",
            "style": "Contemporary",
            "estimated_price": 0.0,
            "search_terms": "rose gold cuff bracelet"
        }}
    ],
    "styling_tips": [
        "Balance statement pieces with clean subtle accents"
    ]
}}
"""
                response_text = generate_ai_content(prompt)
                
            if not response_text:
                raise ValueError("Could not obtain response from Gemini models")
            result = extract_json_from_response(response_text)
            
            # Attach Indian jewelry brand shopping links
            for item in result.get("jewelry_recommendations", []):
                st = item.get("search_terms") or f"{item.get('style', '')} {item.get('item_type', '')}"
                enc = urllib.parse.quote_plus(st.strip())
                item["shopping_links"] = {
                    "amazon": f"https://www.amazon.in/s?k={enc}",
                    "flipkart": f"https://www.flipkart.com/search?q={enc}",
                    "bluestone": f"https://www.bluestone.com/search.html?query={enc}",
                    "tanishq": f"https://www.tanishq.co.in/search?q={enc}",
                    "caratlane": f"https://www.caratlane.com/search?q={enc}",
                    "melorra": f"https://www.melorra.com/search?q={enc}",
                    "meesho": f"https://www.meesho.com/search?q={enc}"
                }
            result["engine"] = "gemini-live"
            return result
        except Exception as e:
            print(f"Gemini AI jewelry generation notice (using smart fallback): {e}")

    return generate_fallback_jewelry_recommendations(budget_input, image_path)

def generate_fallback_jewelry_recommendations(budget_input, image_path: Optional[str] = None) -> dict:
    total = float(budget_input.total_budget)
    occasion = budget_input.occasion or "Special Event"
    prefs = budget_input.style_preferences or getattr(budget_input, 'preferences', '') or "Elegant & Minimal"

    # Analyze outfit image if available (using simple image metrics)
    outfit_colors = ["blue", "white"]
    outfit_style = "Casual Chic"
    outfit_formality = "Semi-formal"
    
    if image_path and os.path.exists(image_path):
        try:
            with Image.open(image_path) as im:
                im_small = im.resize((50, 50))
                colors = im_small.getcolors(maxcolors=2500)
                if colors:
                    top_color = sorted(colors, key=lambda c: c[0], reverse=True)[0][1]
                    if len(top_color) >= 3:
                        r, g, b = top_color[0], top_color[1], top_color[2]
                        if r > 180 and g > 180 and b > 180:
                            outfit_colors = ["pure white", "silver tones"]
                        elif r > 150 and g < 100:
                            outfit_colors = ["ruby red", "warm gold"]
                        elif b > 150:
                            outfit_colors = ["royal blue", "cool silver"]
                        elif g > 150:
                            outfit_colors = ["emerald green", "antique gold"]
                        else:
                            outfit_colors = ["classic neutral", "charcoal"]
            outfit_style = f"Curated for {occasion}"
            outfit_formality = "Festive" if "fest" in occasion.lower() or "wed" in occasion.lower() else "Smart Casual"
        except Exception:
            pass

    price_bracelet = round(total * 0.15, 2)
    price_ring = round(total * 0.20, 2)
    price_watch = round(total * 0.45, 2)
    spent = price_bracelet + price_ring + price_watch
    remaining = max(0.0, round(total - spent, 2))

    items = [
        {
            "item_type": "Bracelet",
            "description": f"A sleek, braided leather or silver-accented bracelet matching {prefs} aesthetics.",
            "style": "Casual",
            "estimated_price": price_bracelet,
            "search_terms": f"minimalist {prefs} bracelet for {occasion}",
            "shopping_links": {}
        },
        {
            "item_type": "Ring",
            "description": "A polished silver or platinum-finish band ring with a subtle minimalist design.",
            "style": "Minimalist",
            "estimated_price": price_ring,
            "search_terms": f"elegant band ring {prefs}",
            "shopping_links": {}
        },
        {
            "item_type": "Watch / Statement Piece",
            "description": "A classic analog wrist timepiece with metallic accents complementing your outfit tones.",
            "style": "Classic",
            "estimated_price": price_watch,
            "search_terms": f"classic wrist watch {occasion}",
            "shopping_links": {}
        }
    ]

    for itm in items:
        enc = urllib.parse.quote_plus(itm["search_terms"])
        itm["shopping_links"] = {
            "amazon": f"https://www.amazon.in/s?k={enc}",
            "flipkart": f"https://www.flipkart.com/search?q={enc}",
            "bluestone": f"https://www.bluestone.com/search.html?query={enc}",
            "tanishq": f"https://www.tanishq.co.in/search?q={enc}",
            "caratlane": f"https://www.caratlane.com/search?q={enc}",
            "melorra": f"https://www.melorra.com/search?q={enc}",
            "meesho": f"https://www.meesho.com/search?q={enc}"
        }

    return {
        "total_budget": total,
        "remaining_budget": remaining,
        "outfit_analysis": {
            "colors": outfit_colors,
            "style": outfit_style,
            "formality": outfit_formality
        },
        "jewelry_recommendations": items,
        "styling_tips": [
            "Keep jewelry subtle to ensure comfortable wear throughout the occasion.",
            "Consider the watch or pendant as a statement centerpiece reflecting personal style.",
            "Ensure the metal tones of the ring and bracelet complement each other seamlessly."
        ],
        "engine": "smart-budget-engine"
    }
